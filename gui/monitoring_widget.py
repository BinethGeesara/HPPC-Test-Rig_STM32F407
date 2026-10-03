"""Shared live-graph widget used by both the current and voltage panels.

Architecture
------------
* :class:`RollingAverage` – O(1)-per-sample ring-buffer moving average.
* :class:`LiveChart`      – Generic PyQtGraph live-plot with controls.
* :class:`ValueCard`      – Compact badge showing the latest scalar value.

``LiveChart`` is intentionally channel-agnostic:
    - pass ``colors`` and ``labels`` at construction time;
    - call :meth:`push` with a list of floats (one per channel);
    - set ``y_label`` and ``y_unit`` to whatever fits.

``MonitoringWidget`` (dashboard right column) simply instantiates two
``LiveChart`` objects, one for current and one for voltage, and stacks them
vertically.

Chart interaction
-----------------
* Mouse wheel over the plot  → zoom both axes (over an axis: that axis only)
* Left-drag                  → pan
* Right-drag                 → stretch / squash an axis
* Double-click               → reset view (Live + Autoscale + 10 s span)
* Span combo                 → 5 s / 10 s / 30 s / 60 s / All history
* Y + / Y −                  → zoom Y axis
* X + / X −                  → shorten / lengthen time window
* Live button                → X axis follows the newest sample
* Autoscale button           → Y axis fits the visible data
* Pause button               → freeze the picture (data keeps buffering)
"""

import time
from collections import deque

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from config import (
    GRAPH_HISTORY_SAMPLES,
    GRAPH_REDRAW_MS,
    MOVING_AVERAGE_ENABLED,
    MOVING_AVERAGE_WINDOW,
)
from theme import ACCENT, BORDER, BORDER_HOVER, INNER_DARK, PANEL, TEXT, TEXT_MUTED

pg.setConfigOptions(antialias=False, background=INNER_DARK, foreground=TEXT_MUTED)

_DEFAULT_SPAN_S = 10.0
_MIN_Y_SPAN     = 1e-6        # prevent a zero-height view box
_SPAN_PRESETS   = [
    ("5 s",  5.0),
    ("10 s", 10.0),
    ("30 s", 30.0),
    ("60 s", 60.0),
    ("All",  None),
]

# ------------------------------------------------------------------ stylesheet

_BTN_QSS = f"""
    QPushButton {{
        background: {PANEL}; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 12px;
        padding: 4px 11px; font-size: 12px; font-weight: 600;
    }}
    QPushButton:hover    {{ border-color: {BORDER_HOVER}; }}
    QPushButton:checked  {{ background: {ACCENT}; color: #05080B;
                            border-color: {ACCENT}; }}
    QPushButton:disabled {{ color: #5C6470; }}
"""
_COMBO_QSS = f"""
    QComboBox {{
        background: {INNER_DARK}; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 8px;
        padding: 3px 8px; font-size: 12px;
    }}
"""


# ============================================================ RollingAverage

class RollingAverage:
    """O(1)-per-sample ring-buffer moving average for one channel.

    This is purely a display-smoothing aid on the host side and is
    independent of anything the firmware does.
    """

    def __init__(self, window: int = 10):
        self.window = max(1, int(window))
        self.buf    = deque(maxlen=self.window)
        self.sum    = 0.0

    def update(self, value: float) -> float:
        if len(self.buf) == self.buf.maxlen:
            self.sum -= self.buf[0]
        self.buf.append(value)
        self.sum += value
        return self.sum / len(self.buf)

    def reset(self, window: int):
        self.window = max(1, int(window))
        self.buf    = deque(maxlen=self.window)
        self.sum    = 0.0


# ================================================================= ValueCard

class ValueCard(QFrame):
    """Compact value display badge: coloured dot · label · numeric value."""

    def __init__(self, label: str, color: str, unit: str, parent=None):
        super().__init__(parent)
        self._unit = unit
        self.setStyleSheet(
            f"QFrame {{ background: {PANEL}; border: 1px solid {BORDER};"
            f"border-radius: 12px; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 12px;")
        row.addWidget(dot)

        name = QLabel(label.upper())
        name.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px;"
            f"font-weight: 700; letter-spacing: 1.5px;"
        )
        row.addWidget(name)

        self._val_lbl = QLabel("----")
        self._val_lbl.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: 700;"
            f"font-family: 'JetBrains Mono', 'Consolas', monospace;"
        )
        self._val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self._val_lbl, 1)

        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;"
        )
        row.addWidget(unit_lbl)

    def set_value(self, value: float):
        """Update the displayed numeric value."""
        self._val_lbl.setText(f"{value:.4g}")


# ================================================================== LiveChart

class LiveChart(QFrame):
    """Generic multi-channel PyQtGraph live plot.

    Parameters
    ----------
    title:    Short title shown above the chart (e.g. ``"CURRENT"``).
    y_label:  Y-axis label text (e.g. ``"Current"``).
    y_unit:   Unit string appended to the Y label (e.g. ``"A"``).
    colors:   List of hex colour strings, one per channel.
    labels:   List of channel name strings shown in the legend.
    """

    # Emitted whenever the X (time) axis range changes — live scroll or user
    # pan/zoom.  Connect two charts through this signal via MonitoringWidget
    # to keep their time axes in sync.
    x_range_changed = pyqtSignal(float, float)   # (x_lo, x_hi) seconds-ago

    def __init__(
        self,
        title:   str,
        y_label: str,
        y_unit:  str,
        colors:  list[str],
        labels:  list[str],
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setMinimumHeight(340)

        # Reconcile lengths: use the longer of the two as the channel count,
        # padding whichever list is shorter with generated defaults.
        n = max(len(colors), len(labels))
        colors = list(colors) + ["#AAAAAA"] * (n - len(colors))
        labels = list(labels) + [f"Ch{i}" for i in range(len(labels), n)]

        self._n_ch   = n
        self._colors = colors
        self._labels = labels
        self._y_unit = y_unit

        # Rolling data buffers
        self._t               = deque(maxlen=GRAPH_HISTORY_SAMPLES)
        self._raw_series      = [deque(maxlen=GRAPH_HISTORY_SAMPLES)
                                 for _ in range(self._n_ch)]
        self._smoothed_series = [deque(maxlen=GRAPH_HISTORY_SAMPLES)
                                 for _ in range(self._n_ch)]

        self._ma_enabled = MOVING_AVERAGE_ENABLED
        self._ma_window  = MOVING_AVERAGE_WINDOW
        self._ma         = [RollingAverage(self._ma_window)
                            for _ in range(self._n_ch)]

        self._autoscale = True
        self._live      = True
        self._span      = _DEFAULT_SPAN_S
        self._paused    = False
        self._t_ref     = None   # frozen timestamp while paused
        self._dirty     = False

        # X-axis sync: prevents feedback loops when the peer chart applies
        # our emitted x_range_changed back to us.
        self._syncing   = False

        self._build(title, y_label, y_unit)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(GRAPH_REDRAW_MS)

    # --------------------------------------------------------------- UI build

    @staticmethod
    def _btn(text, tip, checkable=False, checked=False):
        b = QPushButton(text)
        b.setStyleSheet(_BTN_QSS)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.setCheckable(checkable)
        if checkable:
            b.setChecked(checked)
        return b

    @staticmethod
    def _muted(text):
        lbl = QLabel(text)
        lbl.setObjectName("Muted")
        lbl.setStyleSheet("background: transparent;")
        return lbl

    def _build(self, title: str, y_label: str, y_unit: str):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        # ---- heading ---------------------------------------------------
        heading = QLabel(title.upper() + "  ·  LIVE")
        heading.setObjectName("Heading")
        outer.addWidget(heading)

        # ---- row 1: data options ----------------------------------------
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._autoscale_btn = self._btn(
            "Autoscale: ON", "Fit Y axis to visible data",
            checkable=True, checked=True)
        self._autoscale_btn.toggled.connect(self._on_autoscale_toggled)
        row1.addWidget(self._autoscale_btn)

        self._ma_btn = self._btn(
            "Avg: ON", "Moving-average display smoothing (host side)",
            checkable=True, checked=self._ma_enabled)
        self._ma_btn.toggled.connect(self._on_ma_toggled)
        row1.addWidget(self._ma_btn)

        row1.addWidget(self._muted("Window"))
        self._ma_spin = QSpinBox()
        self._ma_spin.setRange(1, 200)
        self._ma_spin.setValue(self._ma_window)
        self._ma_spin.setFixedWidth(65)
        self._ma_spin.setEnabled(self._ma_enabled)
        self._ma_spin.valueChanged.connect(self._on_ma_window_changed)
        row1.addWidget(self._ma_spin)

        row1.addStretch()

        self._clear_btn = self._btn("Clear", "Erase all buffered data")
        self._clear_btn.clicked.connect(self.clear)
        row1.addWidget(self._clear_btn)

        self._pause_btn = self._btn(
            "Pause", "Freeze the picture (data keeps buffering)",
            checkable=True)
        self._pause_btn.toggled.connect(self._on_pause_toggled)
        row1.addWidget(self._pause_btn)

        self._reset_btn = self._btn(
            "Reset view", "Live + Autoscale + 10 s  (or double-click the plot)")
        self._reset_btn.clicked.connect(self._reset_view)
        row1.addWidget(self._reset_btn)

        outer.addLayout(row1)

        # ---- row 2: zoom / span ----------------------------------------
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        row2.addWidget(self._muted("Y"))
        y_in = self._btn("+", "Zoom in (Y)")
        y_in.clicked.connect(lambda: self._zoom_y(0.5))
        row2.addWidget(y_in)
        y_out = self._btn("−", "Zoom out (Y)")
        y_out.clicked.connect(lambda: self._zoom_y(2.0))
        row2.addWidget(y_out)

        row2.addWidget(self._muted("X"))
        x_in = self._btn("+", "Shorter time window")
        x_in.clicked.connect(lambda: self._zoom_x(0.5))
        row2.addWidget(x_in)
        x_out = self._btn("−", "Longer time window")
        x_out.clicked.connect(lambda: self._zoom_x(2.0))
        row2.addWidget(x_out)

        row2.addWidget(self._muted("Span"))
        self._span_combo = QComboBox()
        self._span_combo.setStyleSheet(_COMBO_QSS)
        for lbl, _ in _SPAN_PRESETS:
            self._span_combo.addItem(lbl)
        self._sync_span_combo()
        self._span_combo.currentIndexChanged.connect(self._on_span_changed)
        row2.addWidget(self._span_combo)

        self._live_btn = self._btn(
            "Live", "X axis follows newest sample",
            checkable=True, checked=True)
        self._live_btn.toggled.connect(self._on_live_toggled)
        row2.addWidget(self._live_btn)

        row2.addStretch()

        row2.addWidget(self._muted("Y min"))
        self._ymin_spin = QDoubleSpinBox()
        self._ymin_spin.setRange(-1_000_000, 1_000_000)
        self._ymin_spin.setDecimals(4)
        self._ymin_spin.setSingleStep(0.1)
        self._ymin_spin.setKeyboardTracking(False)
        self._ymin_spin.setFixedWidth(96)
        self._ymin_spin.valueChanged.connect(self._on_spin_range)
        row2.addWidget(self._ymin_spin)

        row2.addWidget(self._muted("Y max"))
        self._ymax_spin = QDoubleSpinBox()
        self._ymax_spin.setRange(-1_000_000, 1_000_000)
        self._ymax_spin.setDecimals(4)
        self._ymax_spin.setSingleStep(0.1)
        self._ymax_spin.setKeyboardTracking(False)
        self._ymax_spin.setFixedWidth(96)
        self._ymax_spin.valueChanged.connect(self._on_spin_range)
        row2.addWidget(self._ymax_spin)

        outer.addLayout(row2)

        # ---- plot widget -----------------------------------------------
        self._plot = pg.PlotWidget()
        self._vb   = self._plot.getViewBox()
        self._vb.disableAutoRange()
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.setLabel("bottom", "Time (s ago)")
        self._plot.setLabel("left", f"{y_label} ({y_unit})")
        for axis in ("left", "bottom"):
            self._plot.getAxis(axis).enableAutoSIPrefix(False)
        self._plot.setMouseEnabled(x=True, y=True)
        self._plot.addLegend(offset=(10, 6))

        # Zero reference line
        self._plot.addItem(pg.InfiniteLine(
            pos=0, angle=0, movable=False,
            pen=pg.mkPen((255, 255, 255, 60), width=1, style=Qt.DashLine)))

        self._curves = []
        for i in range(self._n_ch):
            pen   = pg.mkPen(color=self._colors[i], width=2)
            curve = self._plot.plot([], [], pen=pen, name=self._labels[i])
            curve.setClipToView(True)
            self._curves.append(curve)

        self._vb.setXRange(-self._span, 0.0, padding=0)
        self._vb.setYRange(-1.0, 1.0, padding=0)
        self._snap = self._vb.viewRange()

        self._vb.sigRangeChangedManually.connect(self._on_manual_range)
        self._vb.sigYRangeChanged.connect(lambda *_: self._sync_spins())
        self._plot.scene().sigMouseClicked.connect(self._on_scene_clicked)
        self._plot.scene().sigMouseMoved.connect(self._on_mouse_moved)

        outer.addWidget(self._plot, 1)

        # ---- footer: hint + cursor readout ----------------------------
        foot = QHBoxLayout()
        hint = self._muted(
            "wheel = zoom  ·  drag = pan  ·  right-drag = stretch  ·  dbl-click = reset")
        foot.addWidget(hint)
        foot.addStretch()
        self._readout = QLabel("")
        self._readout.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; background: transparent;"
            f"font-family: 'JetBrains Mono', 'Consolas', monospace;")
        foot.addWidget(self._readout)
        outer.addLayout(foot)

    # --------------------------------------------------------------- data API

    def push(self, values: list[float]):
        """Append one sample (one value per channel).  Thread-safe: must be
        called from the GUI thread (Qt signal delivery is always on the GUI
        thread so this is guaranteed in normal use)."""
        if not values:
            return
        t = time.monotonic()
        self._t.append(t)
        for i, v in enumerate(values[:self._n_ch]):
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = 0.0
            self._raw_series[i].append(v)
            self._smoothed_series[i].append(self._ma[i].update(v))
        self._dirty = True

    def apply_linked_x(self, lo: float, hi: float):
        """Apply an X range received from the peer chart.

        Sets ``_syncing = True`` so ``_set_view`` will *not* re-emit
        ``x_range_changed``, breaking any feedback loop.  The live-follow
        mode is disabled because the user is now controlling the window.
        """
        self._syncing = True
        try:
            self._set_live(False)
            self._vb.setXRange(lo, hi, padding=0)
            self._snap = self._vb.viewRange()
        finally:
            self._syncing = False

    def clear(self):
        """Erase all buffered samples and reset the moving-average state."""
        self._t.clear()
        for i in range(self._n_ch):
            self._raw_series[i].clear()
            self._smoothed_series[i].clear()
            self._ma[i] = RollingAverage(self._ma_window)
        for curve in self._curves:
            curve.setData([], [])
        self._dirty = False

    # --------------------------------------------------------------- redraw

    def _tick(self):
        if self._dirty and not self._paused:
            self._dirty = False
            self._redraw()

    def _arrays(self):
        """Return (x_seconds_ago, [y_per_channel]) or None if no data."""
        n = len(self._t)
        if n == 0:
            return None
        t   = np.fromiter(self._t, dtype=float, count=n)
        src = self._smoothed_series if self._ma_enabled else self._raw_series
        ys  = [np.fromiter(s, dtype=float, count=n) for s in src]

        if self._paused and self._t_ref is not None:
            keep = t <= self._t_ref
            if not keep.any():
                return None
            t  = t[keep]
            ys = [y[keep] for y in ys]
            t_ref = self._t_ref
        else:
            t_ref = t[-1]

        return t - t_ref, ys

    def _redraw(self):
        data = self._arrays()
        if data is None:
            return
        x, ys = data

        for curve, y in zip(self._curves, ys):
            curve.setData(x, y)

        if self._live:
            x_lo = float(x[0]) if self._span is None else -self._span
            x_lo = min(x_lo, -0.5)
            self._set_view(x=(x_lo, 0.0))

        if self._autoscale:
            xlo = self._vb.viewRange()[0][0]
            sel  = x >= xlo
            if not sel.any():
                sel = np.ones_like(x, dtype=bool)
            lo = min(float(y[sel].min()) for y in ys)
            hi = max(float(y[sel].max()) for y in ys)
            span = hi - lo
            pad  = max(abs(span) * 0.08, 1e-3)
            self._set_view(y=(lo - pad, hi + pad))

    # ----------------------------------------------------- view bookkeeping

    def _set_view(self, x=None, y=None):
        if x is not None:
            self._vb.setXRange(x[0], x[1], padding=0)
        if y is not None:
            self._vb.setYRange(y[0], y[1], padding=0)
        self._snap = self._vb.viewRange()
        # Notify the peer chart (e.g. voltage ↔ current) to sync its X axis.
        # The _syncing guard breaks the feedback loop: when the peer calls
        # apply_linked_x() it sets _syncing=True first, so we don't re-emit.
        if x is not None and not self._syncing:
            self.x_range_changed.emit(float(x[0]), float(x[1]))

    def _sync_spins(self):
        y0, y1 = self._vb.viewRange()[1]
        for spin, v in ((self._ymin_spin, y0), (self._ymax_spin, y1)):
            if spin.hasFocus():
                continue
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)

    def _sync_span_combo(self):
        idx = -1
        for i, (_, v) in enumerate(_SPAN_PRESETS):
            if v == self._span:
                idx = i
                break
        self._span_combo.blockSignals(True)
        self._span_combo.setCurrentIndex(idx)
        self._span_combo.blockSignals(False)

    def _set_autoscale(self, on: bool):
        self._autoscale = on
        self._autoscale_btn.blockSignals(True)
        self._autoscale_btn.setChecked(on)
        self._autoscale_btn.blockSignals(False)
        self._autoscale_btn.setText(f"Autoscale: {'ON' if on else 'OFF'}")

    def _set_live(self, on: bool):
        self._live = on
        self._live_btn.blockSignals(True)
        self._live_btn.setChecked(on)
        self._live_btn.blockSignals(False)

    # ------------------------------------------------------- user interaction

    def _on_manual_range(self, _mask):
        (x0, x1), (y0, y1)    = self._vb.viewRange()
        (sx0, sx1), (sy0, sy1) = self._snap
        x_tol = 1e-6 * max(1.0, abs(sx1 - sx0))
        y_tol = 1e-6 * max(1.0, abs(sy1 - sy0))
        x_moved = abs(x0 - sx0) > x_tol or abs(x1 - sx1) > x_tol
        if x_moved:
            self._set_live(False)
        if abs(y0 - sy0) > y_tol or abs(y1 - sy1) > y_tol:
            self._set_autoscale(False)
        self._snap = self._vb.viewRange()
        self._sync_spins()
        # Propagate the new X window to the peer chart immediately on mouse
        # interaction (without waiting for the next _redraw tick).
        if x_moved and not self._syncing:
            self.x_range_changed.emit(float(x0), float(x1))

    def _on_scene_clicked(self, ev):
        if ev.double() and self._vb.sceneBoundingRect().contains(ev.scenePos()):
            self._reset_view()

    def _on_mouse_moved(self, pos):
        if self._vb.sceneBoundingRect().contains(pos):
            p = self._vb.mapSceneToView(pos)
            self._readout.setText(
                f"t {p.x():+8.2f} s    {self._y_unit} {p.y():+.4g}")
        else:
            self._readout.setText("")

    def _zoom_y(self, factor: float):
        y0, y1 = self._vb.viewRange()[1]
        c = 0.5 * (y0 + y1)
        h = max(0.5 * (y1 - y0) * factor, _MIN_Y_SPAN)
        self._set_autoscale(False)
        self._set_view(y=(c - h, c + h))

    def _zoom_x(self, factor: float):
        x0, x1 = self._vb.viewRange()[0]
        if self._live:
            cur = self._span if self._span is not None else -x0
            self._span = min(max(cur * factor, 0.5), 3600.0)
            self._sync_span_combo()
            self._redraw()
        else:
            c = 0.5 * (x0 + x1)
            h = max(0.5 * (x1 - x0) * factor, 0.25)
            self._set_view(x=(c - h, c + h))

    def _on_span_changed(self, idx: int):
        if idx < 0:
            return
        self._span = _SPAN_PRESETS[idx][1]
        self._set_live(True)
        self._redraw()

    def _on_live_toggled(self, on: bool):
        self._live = on
        if on:
            self._redraw()

    def _on_autoscale_toggled(self, on: bool):
        self._autoscale = on
        self._autoscale_btn.setText(f"Autoscale: {'ON' if on else 'OFF'}")
        if on:
            self._redraw()

    def _on_spin_range(self, _value):
        lo, hi = self._ymin_spin.value(), self._ymax_spin.value()
        if hi - lo < _MIN_Y_SPAN:
            return
        self._set_autoscale(False)
        self._set_view(y=(lo, hi))

    def _on_pause_toggled(self, on: bool):
        self._paused = on
        self._pause_btn.setText("Resume" if on else "Pause")
        if on:
            self._t_ref = self._t[-1] if self._t else None
        else:
            self._t_ref = None
            self._redraw()

    def _reset_view(self):
        self._span = _DEFAULT_SPAN_S
        self._sync_span_combo()
        self._set_autoscale(True)
        self._set_live(True)
        if self._t:
            self._redraw()
        else:
            self._set_view(x=(-self._span, 0.0), y=(-1.0, 1.0))

    # ------------------------------------------------ moving-average controls

    def _on_ma_toggled(self, on: bool):
        self._ma_enabled = on
        self._ma_btn.setText(f"Avg: {'ON' if on else 'OFF'}")
        self._ma_spin.setEnabled(on)
        self._redraw()

    def _on_ma_window_changed(self, value: int):
        window = max(1, int(value))
        self._ma_window = window
        for i in range(self._n_ch):
            ra       = RollingAverage(window)
            smoothed = deque(maxlen=GRAPH_HISTORY_SAMPLES)
            for v in self._raw_series[i]:
                smoothed.append(ra.update(v))
            self._ma[i]            = ra
            self._smoothed_series[i] = smoothed
        self._redraw()


# ============================================================ MonitoringWidget

class MonitoringWidget(QFrame):
    """Right-column panel: value cards + current chart + voltage chart."""

    def __init__(
        self,
        current_colors: list[str],
        current_labels: list[str],
        current_unit:   str,
        voltage_colors: list[str],
        voltage_labels: list[str],
        voltage_unit:   str,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ---- value card row -------------------------------------------
        cards_frame = QFrame()
        cards_row   = QHBoxLayout(cards_frame)
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(10)

        self._current_cards = [
            ValueCard(lbl, col, current_unit)
            for lbl, col in zip(current_labels, current_colors)
        ]
        self._voltage_cards = [
            ValueCard(lbl, col, voltage_unit)
            for lbl, col in zip(voltage_labels, voltage_colors)
        ]
        for card in self._current_cards + self._voltage_cards:
            cards_row.addWidget(card, 1)

        layout.addWidget(cards_frame)

        # ---- charts ---------------------------------------------------
        self.current_chart = LiveChart(
            title="Current",
            y_label="Current",
            y_unit=current_unit,
            colors=current_colors,
            labels=current_labels,
        )
        layout.addWidget(self.current_chart, 1)

        self.voltage_chart = LiveChart(
            title="Voltage",
            y_label="Voltage",
            y_unit=voltage_unit,
            colors=voltage_colors,
            labels=voltage_labels,
        )
        layout.addWidget(self.voltage_chart, 1)

        # ---- Sync the time (X) axis between the two charts ------------
        # When the user pans or zooms one chart's time axis, the other
        # follows instantly.  apply_linked_x() is loop-safe (it sets
        # _syncing=True so x_range_changed is not re-emitted).
        self.current_chart.x_range_changed.connect(
            self.voltage_chart.apply_linked_x)
        self.voltage_chart.x_range_changed.connect(
            self.current_chart.apply_linked_x)

    # -------------------------------------------------------- public API

    def push_current(self, values: list[float]):
        """Update current value cards and chart."""
        for card, v in zip(self._current_cards, values):
            card.set_value(v)
        self.current_chart.push(values)

    def push_voltage(self, values: list[float]):
        """Update voltage value cards and chart."""
        for card, v in zip(self._voltage_cards, values):
            card.set_value(v)
        self.voltage_chart.push(values)

