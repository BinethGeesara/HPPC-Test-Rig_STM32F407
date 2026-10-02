"""Protocol controller – parses HPPC telemetry lines and emits typed signals.

The firmware sends lines like:
    CURRENT:1250      (integer milliamperes)
    VOLTAGE:16320     (integer millivolts)

This module converts those raw integers to display units (A / V by default)
and emits separate Qt signals that the GUI connects to.

To add new telemetry fields:
    1. Add a PREFIX constant in config.py.
    2. Add a compiled re.Pattern here.
    3. Add a pyqtSignal here.
    4. Handle the pattern in handle_line().
    5. Connect the new signal in dashboard.py.
"""

import re

from PyQt5.QtCore import QObject, pyqtSignal

from config import (
    CMD_CHARGE,
    CMD_DISCHARGE_HIGH,
    CMD_DISCHARGE_LOW,
    CMD_RESET_ALL,
    CMD_START_HPPC,
    CMD_STOP_HPPC,
    CURRENT_PREFIX,
    CURRENT_RAW_SCALE,
    VOLTAGE_PREFIX,
    VOLTAGE_RAW_SCALE,
)

# ------------------------------------------------------------------ patterns

# Matches:  CURRENT:<integer>
# The integer can be negative (e.g. charging current shown as negative).
_CURRENT_RE = re.compile(
    rf"^{re.escape(CURRENT_PREFIX)}\s*(-?\d+(?:\.\d+)?)"
)

# Matches:  VOLTAGE:<integer>
_VOLTAGE_RE = re.compile(
    rf"^{re.escape(VOLTAGE_PREFIX)}\s*(-?\d+(?:\.\d+)?)"
)

# Matches firmware acknowledgement:  OK:<command_name>
_OK_RE = re.compile(r"^OK:(.+)")

# Matches firmware state report:  STATE:<state_name>
_STATE_RE = re.compile(r"^STATE:(.+)")

# Catch-all error prefix from the firmware.
_ERR_RE = re.compile(r"^ERR[:\s]")


class STM32Controller(QObject):
    """High-level protocol layer over an :class:`RTTLink`.

    Receives raw RTT text lines, parses them, and emits strongly-typed
    PyQt5 signals.  All command methods return ``True`` if the command was
    accepted by the underlying link (not necessarily acknowledged by the
    target).
    """

    # ---- live telemetry signals ----------------------------------------
    # Each signal carries a list so multi-channel extension is trivial:
    # connect the same slot, iterate the list.

    current_changed = pyqtSignal(list)   # list[float] in display units (A)
    voltage_changed = pyqtSignal(list)   # list[float] in display units (V)
    error_reported  = pyqtSignal(str)    # error string from firmware or parser
    state_changed   = pyqtSignal(str)    # firmware state string (e.g. "HPPC_RUNNING")

    def __init__(self, link):
        super().__init__()
        self.link = link
        self.link.line_received.connect(self.handle_line)

    # ------------------------------------------------------------ commands

    def reset_all(self) -> bool:
        """Send RESET_ALL to the target."""
        return self.link.send_command(CMD_RESET_ALL)

    def charge(self) -> bool:
        """Send CHARGE to the target."""
        return self.link.send_command(CMD_CHARGE)

    def discharge_high(self) -> bool:
        """Send DISCHARGE_HIGH to the target."""
        return self.link.send_command(CMD_DISCHARGE_HIGH)

    def discharge_low(self) -> bool:
        """Send DISCHARGE_LOW to the target."""
        return self.link.send_command(CMD_DISCHARGE_LOW)

    def start_hppc(self) -> bool:
        """Send START_HPPC to the target."""
        return self.link.send_command(CMD_START_HPPC)

    def stop_hppc(self) -> bool:
        """Send STOP_HPPC to the target."""
        return self.link.send_command(CMD_STOP_HPPC)

    def send_raw(self, command: str) -> bool:
        """Forward an arbitrary raw command string."""
        return self.link.send_command(command)

    def is_connected(self) -> bool:
        return self.link.is_connected()

    # ------------------------------------------------------------- parsing

    def handle_line(self, line: str):
        """Called for every clean RTT line received from the target.

        Tries each known pattern in priority order.  Unknown lines that do
        not match any pattern are silently dropped (they appear in the
        console log via the direct link.line_received → console connection
        in dashboard.py).
        """
        try:
            self._parse(line)
        except Exception as exc:
            # Malformed telemetry must never crash the GUI.
            self.error_reported.emit(f"Parse error ({exc}): {line!r}")

    def _parse(self, line: str):
        # ---- current --------------------------------------------------
        m = _CURRENT_RE.match(line)
        if m:
            raw = float(m.group(1))
            value = raw * CURRENT_RAW_SCALE
            self.current_changed.emit([value])
            return

        # ---- voltage --------------------------------------------------
        m = _VOLTAGE_RE.match(line)
        if m:
            raw = float(m.group(1))
            value = raw * VOLTAGE_RAW_SCALE
            self.voltage_changed.emit([value])
            return

        # ---- firmware command acknowledgement  OK:<cmd> ---------------
        # The raw line still appears in the console via line_received.
        # We also emit state_changed so the dashboard can update labels.
        m = _OK_RE.match(line)
        if m:
            self.state_changed.emit(f"OK:{m.group(1).strip()}")
            return

        # ---- firmware state report  STATE:<state> ---------------------
        m = _STATE_RE.match(line)
        if m:
            self.state_changed.emit(m.group(1).strip())
            return

        # ---- firmware errors ------------------------------------------
        if _ERR_RE.match(line) or line.startswith("ERR"):
            self.error_reported.emit(line)
            return

