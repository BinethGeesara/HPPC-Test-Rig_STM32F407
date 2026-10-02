"""Main application window.

Layout
------
* Top navigation bar  – "Monitoring" | "Manual Test" | "HPPC Test" | "Console"
* Connection header   – status indicator + connect/disconnect button + CSV controls
* Main stacked area
    - Monitoring page : left value cards + right dual live graph
    - Manual Test page: Reset All / Charge / Discharge High / Discharge Low
    - HPPC Test page  : Start HPPC / Stop HPPC
    - Console page    : RTT log + command entry

Connection startup sequence (explicit, not automatic):
    link       = RTTLink(TARGET_DEVICE)
    controller = STM32Controller(link)
    link.start()        # spawns the worker process
    # User clicks Connect ↓
    link.request_connect()
"""

import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from config import (
    CURRENT_CH_COLORS,
    CURRENT_CH_LABELS,
    CURRENT_UNIT,
    LOG_DIR_CURRENT,
    LOG_DIR_VOLTAGE,
    LOG_ROTATE_ON_CONNECT,
    TARGET_DEVICE,
    VOLTAGE_CH_COLORS,
    VOLTAGE_CH_LABELS,
    VOLTAGE_UNIT,
)
from csv_logger import CSVLogger
from monitoring_widget import MonitoringWidget
from rtt_connection import RTTLink
from rtt_controller import STM32Controller
from theme import (
    ACCENT,
    BORDER,
    BG,
    ERROR,
    FONT_MONO,
    INNER_DARK,
    PANEL,
    PANEL_GLASS,
    SUCCESS,
    TEXT,
    TEXT_DIM,
    TEXT_MUTED,
    WARNING,
    app_stylesheet,
)


# ============================================================= ConnectionBar

class ConnectionBar(QFrame):
    """Top status strip: indicator dot · message · connect button · CSV toggle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setFixedHeight(60)

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(14)

        # Status indicator (coloured dot)
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {TEXT_DIM}; font-size: 18px;")
        row.addWidget(self._dot)

        # Status text
        self._msg = QLabel("Not connected")
        self._msg.setObjectName("Body")
        self._msg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(self._msg, 1)

        # Pending-commands badge
        self._pending = QLabel("")
        self._pending.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px;"
            f"font-family: {FONT_MONO}; background: transparent;"
        )
        row.addWidget(self._pending)

        # CSV logging button
        self._csv_btn = QPushButton("CSV: OFF")
        self._csv_btn.setObjectName("Pill")
        self._csv_btn.setCheckable(True)
        self._csv_btn.setCursor(Qt.PointingHandCursor)
        self._csv_btn.setToolTip("Toggle CSV logging to disk")
        row.addWidget(self._csv_btn)

        # Connect / Disconnect
        self._conn_btn = QPushButton("Connect")
        self._conn_btn.setObjectName("Pill")
        self._conn_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self._conn_btn)

    # ---------------------------------------------------------------- API

    @property
    def connect_button(self) -> QPushButton:
        return self._conn_btn

    @property
    def csv_button(self) -> QPushButton:
        return self._csv_btn

    def set_connected(self, connected: bool, message: str):
        color = SUCCESS if connected else (WARNING if "retry" in message.lower() else ERROR)
        self._dot.setStyleSheet(f"color: {color}; font-size: 18px;")
        self._msg.setText(message)
        self._conn_btn.setText("Disconnect" if connected else "Connect")

    def set_pending(self, n: int):
        self._pending.setText(f"⬆ {n}" if n > 0 else "")

    def set_csv_active(self, on: bool):
        self._csv_btn.blockSignals(True)
        self._csv_btn.setChecked(on)
        self._csv_btn.setText(f"CSV: {'ON' if on else 'OFF'}")
        self._csv_btn.blockSignals(False)


# ============================================================== ConsoleWidget

class ConsoleWidget(QFrame):
    """Scrolling RTT log + manual command entry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        heading = QLabel("RTT CONSOLE")
        heading.setObjectName("Heading")
        layout.addWidget(heading)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        self._log.setStyleSheet(
            f"QPlainTextEdit {{ background: {INNER_DARK}; color: {TEXT};"
            f"border: 1px solid {BORDER}; border-radius: 8px;"
            f"font-family: {FONT_MONO}; font-size: 12px; padding: 8px; }}"
        )
        layout.addWidget(self._log, 1)

        # Command entry row
        entry_row = QHBoxLayout()
        entry_row.setSpacing(8)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText("Type a raw RTT command and press Enter…")
        self._entry.returnPressed.connect(self._on_send)
        entry_row.addWidget(self._entry, 1)

        send_btn = QPushButton("Send")
        send_btn.setObjectName("Pill")
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.clicked.connect(self._on_send)
        entry_row.addWidget(send_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("Pill")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._log.clear)
        entry_row.addWidget(clear_btn)

        layout.addLayout(entry_row)

        self._input_enabled = False
        self._on_send_cb = None   # set by dashboard after construction

    # ---------------------------------------------------------------- API

    def set_input_enabled(self, on: bool):
        self._input_enabled = on
        self._entry.setEnabled(on)

    def set_send_callback(self, cb):
        self._on_send_cb = cb

    def append_rx(self, line: str):
        """Received line from target."""
        self._log.appendPlainText(f"← {line}")
        self._scroll_to_bottom()

    def append_tx(self, command: str):
        """Command written to target."""
        self._log.appendPlainText(f"→ {command}")
        self._scroll_to_bottom()

    def append_note(self, text: str):
        self._log.appendPlainText(f"  {text}")
        self._scroll_to_bottom()

    def append_error(self, text: str):
        self._log.appendPlainText(f"✖ {text}")
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_send(self):
        text = self._entry.text().strip()
        if not text:
            return
        self._entry.clear()
        if self._on_send_cb:
            self._on_send_cb(text)


# =========================================================== control helpers

def _pill(text: str, tip: str = "", danger: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("PillDanger" if danger else "Pill")
    btn.setCursor(Qt.PointingHandCursor)
    if tip:
        btn.setToolTip(tip)
    return btn


def _section(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setObjectName("Heading")
    return lbl


# ============================================================== ManualTestTab

class ManualTestTab(QFrame):
    """Manual relay / DAC control panel (Reset All, Charge, Discharge H/L)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)

        outer.addWidget(_section("MANUAL TEST CONTROLS"))

        desc = QLabel(
            "These commands are forwarded to the target over RTT down-buffer 0.\n"
            "Make sure the firmware implements the corresponding handlers."
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        grid = QHBoxLayout()
        grid.setSpacing(10)

        self.btn_reset   = _pill("Reset All",       "Send RESET_ALL",       danger=True)
        self.btn_charge  = _pill("Charge",           "Send CHARGE",          danger=False)
        self.btn_dis_hi  = _pill("Discharge High",   "Send DISCHARGE_HIGH",  danger=False)
        self.btn_dis_lo  = _pill("Discharge Low",    "Send DISCHARGE_LOW",   danger=False)

        for btn in (self.btn_reset, self.btn_charge, self.btn_dis_hi, self.btn_dis_lo):
            grid.addWidget(btn)

        outer.addLayout(grid)
        outer.addStretch()

        self._set_enabled(False)

    def set_enabled(self, on: bool):  # noqa: D102 (public API)
        self._set_enabled(on)

    def _set_enabled(self, on: bool):
        for btn in (self.btn_reset, self.btn_charge, self.btn_dis_hi, self.btn_dis_lo):
            btn.setEnabled(on)


# ============================================================== HPPCTestTab

class HPPCTestTab(QFrame):
    """HPPC test panel: Start / Stop buttons with status display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)

        outer.addWidget(_section("HPPC TEST"))

        desc = QLabel(
            "Hybrid Pulse Power Characterisation test sequence.\n"
            "Start sends START_HPPC; Stop sends STOP_HPPC.\n"
            "The firmware controls the test timing autonomously."
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_start = QPushButton("▶  Start HPPC")
        self.btn_start.setObjectName("PillSuccess")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setFixedHeight(42)
        btn_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("■  Stop HPPC")
        self.btn_stop.setObjectName("PillDanger")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setFixedHeight(42)
        btn_row.addWidget(self.btn_stop)

        outer.addLayout(btn_row)

        self._status_lbl = QLabel("—  idle")
        self._status_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        outer.addWidget(self._status_lbl)

        outer.addStretch()

        self._set_enabled(False)

    def set_enabled(self, on: bool):
        self._set_enabled(on)

    def _set_enabled(self, on: bool):
        self.btn_start.setEnabled(on)
        self.btn_stop.setEnabled(on)

    def set_status(self, text: str, color: str = TEXT_MUTED):
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent;"
        )


# ================================================================ MainWindow

class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self):
        super().__init__()

        # ---- RTT link + protocol controller ---------------------------
        self.link   = RTTLink(TARGET_DEVICE)
        self.stm32  = STM32Controller(self.link)

        # ---- CSV loggers ----------------------------------------------
        self.log_current = CSVLogger(
            LOG_DIR_CURRENT,
            [f"ch{i}_{CURRENT_UNIT}" for i in range(len(CURRENT_CH_LABELS))],
            "current",
        )
        self.log_voltage = CSVLogger(
            LOG_DIR_VOLTAGE,
            [f"ch{i}_{VOLTAGE_UNIT}" for i in range(len(VOLTAGE_CH_LABELS))],
            "voltage",
        )
        self._session_t0  = time.monotonic()
        self._csv_logging = False

        # ---- pending-command refresh timer ----------------------------
        self._pending_timer = QTimer(self)
        self._pending_timer.timeout.connect(self._refresh_pending)
        self._pending_timer.start(500)

        # ---- window setup --------------------------------------------
        self.setWindowTitle(f"HPPC Monitor  ·  {TARGET_DEVICE}")
        self.setGeometry(80, 80, 1440, 900)
        self.setMinimumSize(1100, 700)

        self._build_ui()
        self._wire()

        # Disable controls until the link is up.
        self._set_controls_enabled(False)

        # Start the worker process.  Do NOT auto-connect; the user
        # must click Connect explicitly.
        self.link.start()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(12)

        # ---- connection bar ------------------------------------------
        self._conn_bar = ConnectionBar()
        root.addWidget(self._conn_bar)

        # ---- top navigation tabs -------------------------------------
        nav = QHBoxLayout()
        self._nav_tabs = QTabBar()
        self._nav_tabs.addTab("Monitoring")
        self._nav_tabs.addTab("Manual Test")
        self._nav_tabs.addTab("HPPC Test")
        self._nav_tabs.addTab("Console")
        self._nav_tabs.currentChanged.connect(self._on_nav_changed)
        nav.addWidget(self._nav_tabs)
        nav.addStretch()
        root.addLayout(nav)

        # ---- stacked pages -------------------------------------------
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_monitoring_page())
        self._stack.addWidget(self._build_manual_test_page())
        self._stack.addWidget(self._build_hppc_test_page())
        self._stack.addWidget(self._build_console_page())
        root.addWidget(self._stack, 1)

    def _build_monitoring_page(self) -> QWidget:
        page   = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._monitoring = MonitoringWidget(
            current_colors=CURRENT_CH_COLORS,
            current_labels=CURRENT_CH_LABELS,
            current_unit=CURRENT_UNIT,
            voltage_colors=VOLTAGE_CH_COLORS,
            voltage_labels=VOLTAGE_CH_LABELS,
            voltage_unit=VOLTAGE_UNIT,
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self._monitoring)
        layout.addWidget(scroll, 1)
        return page

    def _build_manual_test_page(self) -> QWidget:
        page   = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._manual_tab = ManualTestTab()
        layout.addWidget(self._manual_tab)
        layout.addStretch()
        return page

    def _build_hppc_test_page(self) -> QWidget:
        page   = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._hppc_tab = HPPCTestTab()
        layout.addWidget(self._hppc_tab)
        layout.addStretch()
        return page

    def _build_console_page(self) -> QWidget:
        page   = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._console = ConsoleWidget()
        self._console.set_send_callback(self._on_raw_command)
        layout.addWidget(self._console, 1)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setObjectName("Muted")
        self._status_lbl.setStyleSheet(
            f"background: rgba(255,255,255,0.03); padding: 10px 14px;"
            f"border-radius: 8px; color: {TEXT_MUTED};"
        )
        layout.addWidget(self._status_lbl)
        return page

    # --------------------------------------------------------------- wiring

    def _wire(self):
        # Connection bar
        self._conn_bar.connect_button.clicked.connect(self._toggle_connection)
        self._conn_bar.csv_button.toggled.connect(self._on_csv_toggled)

        # Link events
        self.link.connection_status.connect(self._on_connection_status)
        self.link.reconnect_attempt.connect(self._on_reconnect_attempt)
        self.link.line_received.connect(self._console.append_rx)
        self.link.command_written.connect(self._console.append_tx)

        # Controller signals → monitoring widget
        self.stm32.current_changed.connect(self._monitoring.push_current)
        self.stm32.voltage_changed.connect(self._monitoring.push_voltage)
        self.stm32.error_reported.connect(self._on_error)
        self.stm32.state_changed.connect(self._on_state_changed)

        # Controller signals → CSV loggers
        self.stm32.current_changed.connect(self._log_current)
        self.stm32.voltage_changed.connect(self._log_voltage)

        # Manual test buttons
        self._manual_tab.btn_reset.clicked.connect(
            lambda: self._send("reset_all"))
        self._manual_tab.btn_charge.clicked.connect(
            lambda: self._send("charge"))
        self._manual_tab.btn_dis_hi.clicked.connect(
            lambda: self._send("discharge_high"))
        self._manual_tab.btn_dis_lo.clicked.connect(
            lambda: self._send("discharge_low"))

        # HPPC test buttons
        self._hppc_tab.btn_start.clicked.connect(self._on_start_hppc)
        self._hppc_tab.btn_stop.clicked.connect(self._on_stop_hppc)

    # ----------------------------------------------------------- navigation

    def _on_nav_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)

    # ----------------------------------------------------------- connection

    def _toggle_connection(self):
        if self.link.is_connected():
            self.link.request_disconnect()
        else:
            self.link.request_connect()

    def _on_connection_status(self, connected: bool, message: str):
        self._conn_bar.set_connected(connected, message)
        self._set_controls_enabled(connected)
        color = SUCCESS if connected else (
            WARNING if "retry" in message.lower() else ERROR
        )
        self._status(message, color)

        if connected:
            self._session_t0 = time.monotonic()
            self._console.append_note(f"Connected  ·  {message}")
            if LOG_ROTATE_ON_CONNECT and self._csv_logging:
                self._open_logs()
        else:
            self._console.append_note(f"Disconnected  ·  {message}")
            if LOG_ROTATE_ON_CONNECT:
                self._close_logs()

    def _on_reconnect_attempt(self, attempt: int):
        self._status(f"Reconnect attempt #{attempt}…", WARNING)

    # ------------------------------------------------------------ commands

    def _send(self, method: str):
        """Call a named method on the STM32Controller."""
        fn = getattr(self.stm32, method, None)
        if fn and callable(fn):
            ok = fn()
            if not ok:
                self._console.append_note(f"Command '{method}' not sent (not connected)")

    def _on_raw_command(self, text: str):
        if not self.stm32.send_raw(text):
            self._console.append_note("Not connected – command dropped")

    def _on_start_hppc(self):
        if self.stm32.start_hppc():
            self._hppc_tab.set_status("▶  HPPC test running…", SUCCESS)
        else:
            self._hppc_tab.set_status("✖  Not connected", ERROR)

    def _on_stop_hppc(self):
        if self.stm32.stop_hppc():
            self._hppc_tab.set_status("■  Stop command sent", WARNING)
        else:
            self._hppc_tab.set_status("✖  Not connected", ERROR)

    def _on_error(self, line: str):
        self._console.append_error(line)
        self._status(f"Error: {line}", ERROR)

    def _on_state_changed(self, state: str):
        """Handle firmware OK: acknowledgements and STATE: reports."""
        # Command acknowledgements – update status bar and HPPC tab label.
        if state.startswith("OK:"):
            cmd = state[3:]
            self._status(f"✔  {cmd}", SUCCESS)
            # Update HPPC tab if relevant
            if cmd in ("START_HPPC",):
                self._hppc_tab.set_status("▶  HPPC running (confirmed by firmware)", SUCCESS)
            elif cmd in ("STOP_HPPC", "RESET_ALL"):
                self._hppc_tab.set_status("■  Stopped (confirmed by firmware)", TEXT_MUTED)
            return

        # Live state reports
        if state == "HPPC_RUNNING":
            self._hppc_tab.set_status("▶  HPPC running…", SUCCESS)
        else:
            # Unknown state - just log it
            self._console.append_note(f"STATE: {state}")

    # ------------------------------------------------------------ controls

    def _set_controls_enabled(self, on: bool):
        self._manual_tab.set_enabled(on)
        self._hppc_tab.set_enabled(on)
        self._console.set_input_enabled(on)

    def _status(self, text: str, color: str = TEXT_MUTED):
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f"background: rgba(255,255,255,0.03); padding: 10px 14px;"
            f"border-radius: 8px; color: {color}; font-size: 13px;"
        )

    def _refresh_pending(self):
        self._conn_bar.set_pending(self.link.pending_commands())

    # ------------------------------------------------------------ CSV logging

    def _on_csv_toggled(self, on: bool):
        self._csv_logging = on
        self._conn_bar.set_csv_active(on)
        if on:
            self._open_logs()
        else:
            self._close_logs()

    def _open_logs(self):
        self._session_t0 = time.monotonic()
        self.log_current.open()
        self.log_voltage.open()
        self._console.append_note(
            f"CSV logging started  ·  {self.log_current.path}"
        )
        self._console.append_note(
            f"CSV logging started  ·  {self.log_voltage.path}"
        )

    def _close_logs(self):
        self.log_current.close()
        self.log_voltage.close()

    def _log_current(self, values: list):
        if self._csv_logging:
            self.log_current.write(values, time.monotonic() - self._session_t0)

    def _log_voltage(self, values: list):
        if self._csv_logging:
            self.log_voltage.write(values, time.monotonic() - self._session_t0)

    # --------------------------------------------------------------- shutdown

    def closeEvent(self, event):
        self._close_logs()
        self.link.shutdown()
        if not self.link.wait(3000):
            self.link.terminate()
            self.link.wait(500)
        event.accept()

