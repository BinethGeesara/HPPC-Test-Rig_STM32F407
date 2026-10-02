"""RTT link – worker process + GUI-side shim.

Every pylink call happens inside a *separate process*, not a thread.

Why: if a J-Link / USB call ever wedges – which does happen right after the
target hard-resets mid-transaction – a blocked native call can hold the GIL,
and nothing else in that interpreter can run until it returns.  When that
code lived on a QThread, a wedge there froze the whole GUI with no safe way
to recover: Python cannot forcibly interrupt a thread stuck inside a blocking
C call.

A separate OS process doesn't have this problem.  The GUI process's GIL is
completely independent of the worker's, so the GUI stays responsive no matter
what the worker is stuck doing, and a watchdog can straight-up kill the worker
process (always safe, unlike QThread.terminate() on a thread holding native
resources) and spin up a fresh one.
"""

import multiprocessing as mp
import queue
import time

import pylink
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from config import (
    AUTO_RECONNECT,
    COMMAND_INTERVAL_MS,
    ECHO_TIMEOUT_S,
    MAX_RECONNECT_ATTEMPTS,
    MAX_RECONNECT_DELAY_MS,
    POLL_INTERVAL_MS,
    READ_CHUNK,
    RECONNECT_DELAY_MS,
    RTT_CHECK_TIMEOUT,
    RTT_DOWN_BUFFER,
    RTT_DOWN_CHUNK,
    RTT_SEARCH_RANGES,
    RTT_UP_BUFFER,
    TARGET_DEVICE,
    TELEMETRY_MIN_INTERVAL_S,
)

# Markers used as fallback echo stripping when an exact echo match fails.
REPLY_MARKERS = ("OK:", "ERR:", "STATE:")

HEARTBEAT_INTERVAL_S = 1.0
# Max time spent draining events per GUI poll tick so a burst can never
# monopolise the GUI thread.
POLL_BUDGET_S = 0.008
# Must be longer than RTT_CHECK_TIMEOUT (the legitimate long block in the
# worker) so a normal reconnect attempt never triggers the watchdog.
WATCHDOG_TIMEOUT_S = max(RTT_CHECK_TIMEOUT + 3.0, 6.0)


# ============================================================= worker process

def _worker_main(cmd_q: "mp.Queue", evt_q: "mp.Queue", device_name: str):
    """Runs entirely in the child process.  Communicates with the GUI only
    via multiprocessing queues – never via shared memory or signals."""

    link = None
    connected = False
    want_connected = False
    stop = False

    tx_pending = b""
    last_write = 0.0
    rx_text = ""
    echo = []           # list of [expected_text, timestamp]
    out_queue = []      # commands waiting to be transmitted

    attempts = 0
    next_attempt_at = 0.0
    last_heartbeat = 0.0
    last_forwarded: dict[str, float] = {}

    # ---------------------------------------------------------------- helpers

    def emit(kind, *args):
        try:
            evt_q.put_nowait((kind, args))
        except Exception:
            pass

    def close(message: str):
        nonlocal connected, link, tx_pending, echo, rx_text, out_queue
        connected = False
        if link is not None:
            try:
                link.rtt_stop()
            except Exception:
                pass
            try:
                link.close()
            except Exception:
                pass
        link = None
        out_queue = []
        tx_pending = b""
        echo = []
        rx_text = ""
        emit("status", False, message)

    def schedule_retry(reason: str):
        nonlocal attempts, next_attempt_at, want_connected
        if not (AUTO_RECONNECT and want_connected):
            want_connected = False
            emit("status", False, reason)
            return
        if 0 < MAX_RECONNECT_ATTEMPTS <= attempts:
            want_connected = False
            emit("status", False, "Max reconnect attempts reached")
            return
        attempts += 1
        delay_ms = min(
            RECONNECT_DELAY_MS * (1.5 ** (attempts - 1)), MAX_RECONNECT_DELAY_MS
        )
        next_attempt_at = time.monotonic() + delay_ms / 1000.0
        emit("reconnect_attempt", attempts)
        emit("status", False, f"{reason} – retry #{attempts} in {delay_ms / 1000:.1f} s")

    def open_link():
        nonlocal link, connected, attempts, rx_text, echo, tx_pending, last_write
        emit("status", False, f"Connecting to {device_name}…")
        l = None
        try:
            l = pylink.JLink()
            l.open()
            l.set_tif(pylink.enums.JLinkInterfaces.SWD)
            l.connect(device_name)

            try:
                l.exec_command(f"SetRTTSearchRanges {RTT_SEARCH_RANGES}")
            except Exception:
                pass

            l.rtt_start()

            deadline = time.monotonic() + RTT_CHECK_TIMEOUT
            found = False
            while time.monotonic() < deadline:
                # Keep the heartbeat alive inside the potentially-long wait so
                # the GUI watchdog does not mistake this for a wedge.
                emit("heartbeat", len(out_queue))
                try:
                    if l.rtt_get_num_up_buffers() > 0:
                        found = True
                        break
                except Exception:
                    pass
                time.sleep(0.25)

            if not found:
                raise RuntimeError(
                    "RTT control block not found.  "
                    "Check that the firmware calls SEGGER_RTT_Init() and "
                    "the target is running."
                )

            link = l
            connected = True
            attempts = 0
            rx_text = ""
            echo = []
            tx_pending = b""
            last_write = 0.0
            emit("status", True, f"Connected to {device_name}")

        except Exception as exc:
            if l is not None:
                try:
                    l.close()
                except Exception:
                    pass
            link = None
            connected = False
            schedule_retry(str(exc))

    def consume_echo():
        nonlocal rx_text
        while echo:
            expected, stamp = echo[0]
            if rx_text.startswith(expected):
                rx_text = rx_text[len(expected):]
                echo.pop(0)
                continue
            if expected.startswith(rx_text):
                if time.monotonic() - stamp > ECHO_TIMEOUT_S:
                    echo.pop(0)
                    continue
                return
            if time.monotonic() - stamp > ECHO_TIMEOUT_S:
                echo.pop(0)
                continue
            return

    def clean(line: str) -> str:
        """Strip any leading noise up to the first known reply marker."""
        cut = -1
        for marker in REPLY_MARKERS:
            idx = line.find(marker)
            if idx > 0 and (cut < 0 or idx < cut):
                cut = idx
        if cut > 0:
            line = line[cut:]
        return line.strip()

    def throttled(line: str) -> bool:
        for prefix, gap in TELEMETRY_MIN_INTERVAL_S.items():
            if gap > 0 and line.startswith(prefix):
                now = time.monotonic()
                if now - last_forwarded.get(prefix, 0.0) < gap:
                    return True
                last_forwarded[prefix] = now
                return False
        return False

    def fail(message: str):
        nonlocal connected
        was_connected = connected
        close(message)
        if was_connected and want_connected:
            schedule_retry(message)

    def service_tx():
        nonlocal tx_pending, last_write, out_queue
        now = time.monotonic()
        if not tx_pending:
            if (now - last_write) * 1000.0 < COMMAND_INTERVAL_MS:
                return
            if not out_queue:
                return
            command = out_queue.pop(0)
            tx_pending = (command + "\n").encode("ascii", "ignore")
            echo.append([command, now])
            emit("written", command)

        chunk = tx_pending[:RTT_DOWN_CHUNK]
        try:
            written = link.rtt_write(RTT_DOWN_BUFFER, list(chunk))
        except Exception as exc:
            fail(f"Write failed: {exc}")
            return

        if not written:
            return
        tx_pending = tx_pending[written:]
        if not tx_pending:
            last_write = time.monotonic()

    def service_rx():
        nonlocal rx_text
        try:
            raw = link.rtt_read(RTT_UP_BUFFER, READ_CHUNK)
        except Exception as exc:
            fail(f"Read failed: {exc}")
            return

        if not raw:
            return

        text = bytes(raw).decode("utf-8", errors="replace")
        rx_text += text.replace("\r\n", "\n").replace("\r", "\n")
        consume_echo()

        while "\n" in rx_text:
            line, rx_text = rx_text.split("\n", 1)
            line = clean(line)
            if line and not throttled(line):
                emit("line", line)
            consume_echo()

    # ------------------------------------------------------------------ loop

    while not stop:
        # Drain the command queue first.
        try:
            while True:
                cmd = cmd_q.get_nowait()
                kind = cmd[0]
                if kind == "connect":
                    want_connected = True
                    attempts = 0
                    next_attempt_at = 0.0
                elif kind == "disconnect":
                    want_connected = False
                elif kind == "send":
                    if connected and len(out_queue) <= 64:
                        out_queue.append(cmd[1])
                elif kind == "clear":
                    out_queue = []
                elif kind == "shutdown":
                    want_connected = False
                    stop = True
        except queue.Empty:
            pass

        # Manage the link.
        try:
            if want_connected and not connected:
                if time.monotonic() >= next_attempt_at:
                    open_link()
            elif connected and not want_connected:
                close("Disconnected")

            if connected:
                service_tx()
                service_rx()
        except Exception as exc:
            fail(f"Link error: {exc}")

        # Periodic heartbeat so the GUI watchdog knows we are alive.
        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL_S:
            last_heartbeat = now
            emit("heartbeat", len(out_queue))

        time.sleep(POLL_INTERVAL_MS / 1000.0)

    close("Stopped")


# ============================================================= GUI-side shim

class RTTLink(QObject):
    """GUI-facing object.  Owns a worker *process* (see _worker_main) and
    polls its event queue on a QTimer so the GUI thread is never blocked.

    Public API is deliberately identical to the old QThread version so the
    rest of the application needs no changes: start(), request_connect(),
    request_disconnect(), shutdown(), is_connected(), send_command(),
    clear_queue(), pending_commands(), wait(), terminate().
    """

    connection_status = pyqtSignal(bool, str)  # connected, message
    reconnect_attempt = pyqtSignal(int)         # attempt number
    line_received     = pyqtSignal(str)         # one clean line from target
    command_written   = pyqtSignal(str)         # command put on the wire

    def __init__(self, device: str = TARGET_DEVICE):
        super().__init__()
        self.device_name = device

        self._proc: mp.Process | None = None
        self._cmd_q: mp.Queue | None = None
        self._evt_q: mp.Queue | None = None

        self._connected = False
        self._pending = 0
        self._want_connected = False
        self._last_heartbeat = time.monotonic()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(POLL_INTERVAL_MS)

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.timeout.connect(self._check_watchdog)
        self._watchdog_timer.start(1000)

    # -------------------------------------------------------------- public API

    def start(self):
        self._spawn()

    def request_connect(self):
        self._want_connected = True
        self._last_heartbeat = time.monotonic()
        if self._proc is None:
            self._spawn()
        self._send_cmd(("connect",))

    def request_disconnect(self):
        self._want_connected = False
        self._send_cmd(("disconnect",))

    def shutdown(self):
        self._want_connected = False
        self._send_cmd(("shutdown",))

    def is_connected(self) -> bool:
        return self._connected

    def send_command(self, command: str) -> bool:
        command = command.strip()
        if not command or not self._connected:
            return False
        self._send_cmd(("send", command))
        return True

    def clear_queue(self):
        self._send_cmd(("clear",))

    def pending_commands(self) -> int:
        return self._pending

    def wait(self, timeout_ms: int = 3000) -> bool:
        if self._proc is None:
            return True
        self._proc.join(timeout_ms / 1000.0)
        return not self._proc.is_alive()

    def terminate(self):
        if self._proc is not None and self._proc.is_alive():
            self._proc.terminate()

    # ---------------------------------------------------------------- private

    def _spawn(self):
        self._cmd_q = mp.Queue()
        self._evt_q = mp.Queue()
        self._proc = mp.Process(
            target=_worker_main,
            args=(self._cmd_q, self._evt_q, self.device_name),
            daemon=True,
        )
        self._proc.start()
        self._last_heartbeat = time.monotonic()

    def _send_cmd(self, cmd: tuple):
        if self._cmd_q is not None:
            try:
                self._cmd_q.put_nowait(cmd)
            except Exception:
                pass

    def _poll(self):
        if self._evt_q is None:
            return
        deadline = time.monotonic() + POLL_BUDGET_S
        try:
            while time.monotonic() < deadline:
                kind, args = self._evt_q.get_nowait()
                if kind == "status":
                    self._connected = args[0]
                    self.connection_status.emit(*args)
                elif kind == "reconnect_attempt":
                    self.reconnect_attempt.emit(*args)
                elif kind == "line":
                    self.line_received.emit(*args)
                elif kind == "written":
                    self.command_written.emit(*args)
                elif kind == "heartbeat":
                    self._last_heartbeat = time.monotonic()
                    self._pending = args[0]
        except queue.Empty:
            pass

    def _check_watchdog(self):
        if not self._want_connected:
            return
        if self._proc is None or not self._proc.is_alive():
            return
        if time.monotonic() - self._last_heartbeat <= WATCHDOG_TIMEOUT_S:
            return

        # Worker is wedged inside a blocking J-Link / USB call.  Kill it
        # (safe: separate OS process) and start a fresh one.
        self.connection_status.emit(False, "Link process unresponsive – restarting")
        try:
            self._proc.terminate()
            self._proc.join(1.0)
        except Exception:
            pass
        self._connected = False
        self._spawn()
        if self._want_connected:
            self._send_cmd(("connect",))

