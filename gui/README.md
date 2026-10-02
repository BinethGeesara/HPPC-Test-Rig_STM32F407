# STM32F407 HPPC Monitor

A Python desktop GUI for real-time monitoring of an STM32F407 microcontroller
over a SEGGER J-Link probe using SEGGER RTT (Real-Time Transfer).

The application connects through SWD, reads live current and voltage telemetry
printed by the firmware over RTT channel 0, and displays them as scrolling
live graphs.  Manual relay control commands (Charge, Discharge High/Low,
Reset All) and an HPPC test launcher are included.

---

## Requirements

### Python

Python **3.10 or newer** is required (uses `list[str]`, `float | None`, and
similar modern type hints that are syntax-errors on older versions).

### Python packages

Install with pip:

```bash
pip install -r requirements.txt
```

Or with uv (creates an isolated `.venv` automatically):

```bash
uv sync
```

The packages are:

| Package | Purpose |
|---------|---------|
| `PyQt5` | GUI framework |
| `pyqtgraph` | Live scrolling graphs |
| `numpy` | Array maths for graph rendering |
| `pylink-square` | Python bindings for the SEGGER J-Link SDK |
| `psutil` | Optional: process monitoring (imported by pylink) |

### SEGGER J-Link

1. Download and install the **J-Link Software and Documentation Pack** from
   <https://www.segger.com/downloads/jlink/>.
2. The installer registers `JLinkARM.dll` (Windows) / `libjlinkarm.so` (Linux)
   globally.  `pylink-square` finds it automatically.
3. No additional PATH changes are needed.

### J-Link USB connection

* Connect the J-Link probe to your PC via USB.
* Connect the J-Link **SWD** connector (SWDIO, SWDCLK, GND, 3.3 V) to the
  STM32F407 debug port.
* The PC should enumerate the J-Link as a USB device before launching the GUI.

---

## STM32F407 Target Setup

The firmware must:

1. Call `SEGGER_RTT_Init()` **before** the main loop.
2. Print telemetry lines to **RTT channel 0** (the default `_SEGGER_RTT.aUp[0]`
   buffer) using `SEGGER_RTT_printf(0, …)` or equivalent.
3. Implement a command parser that reads newline-terminated ASCII commands from
   **RTT channel 0 down-buffer** (`_SEGGER_RTT.aDown[0]`) if you want the
   manual control and HPPC buttons to work.

### RTT buffer numbers

| Direction | Buffer index | Purpose |
|-----------|-------------|---------|
| Up (target → host) | 0 | Telemetry + log output |
| Down (host → target) | 0 | Control commands |

These are the SEGGER defaults and match the values in `config.py`:
`RTT_UP_BUFFER = 0` and `RTT_DOWN_BUFFER = 0`.

### Expected telemetry message format

Each telemetry line is a **PREFIX:VALUE** pair terminated with `\n`:

```
CURRENT:<integer_milliamperes>
VOLTAGE:<integer_millivolts>
```

Examples (from the INA226 driver in this project):

```
CURRENT:1250
VOLTAGE:16320
```

The host converts these using the scale factors in `config.py`:

```python
CURRENT_RAW_SCALE = 1e-3   # mA → A
VOLTAGE_RAW_SCALE = 1e-3   # mV → V
```

The displayed value is `raw_integer × SCALE`.

### Expected control commands (down-buffer)

The GUI sends these newline-terminated ASCII strings when buttons are pressed:

| Button | Command sent |
|--------|-------------|
| Reset All | `RESET_ALL\n` |
| Charge | `CHARGE\n` |
| Discharge High | `DISCHARGE_HIGH\n` |
| Discharge Low | `DISCHARGE_LOW\n` |
| Start HPPC | `START_HPPC\n` |
| Stop HPPC | `STOP_HPPC\n` |

You can change these strings in `config.py` under the `# Commands` section
without touching any other file.

---

## How to run

```bash
cd e:\FYP\STM32\HPPC\gui
python main.py
```

The window opens with **no active connection**.  Click the **Connect** button
in the top bar to initiate the SWD link.  The application will:

1. Open the J-Link DLL.
2. Set the interface to SWD.
3. Connect to `STM32F407VG`.
4. Search SRAM `0x20000000–0x2001FFFF` for the RTT control block.
5. Start streaming.

If the connection fails, automatic reconnect retries with exponential back-off
(configurable in `config.py`).

---

## Changing the target device or graph settings

All tuneable settings are in **`config.py`**.  No other file needs to change.

### Change the target MCU

```python
TARGET_DEVICE = "STM32F401VE"   # any device string J-Link accepts
```

### Change the RTT search range

```python
RTT_SEARCH_RANGES = "0x20000000 0x10000"   # start  length (both hex)
```

### Adjust graph history and refresh rate

```python
GRAPH_HISTORY_SAMPLES = 6000    # samples per channel (~2 min at 50 Hz)
GRAPH_REDRAW_MS       = 33      # ~30 fps
```

### Change graph units

If the firmware sends raw SI values (not milli-units):

```python
CURRENT_RAW_SCALE = 1.0     # firmware sends A directly
VOLTAGE_RAW_SCALE = 1.0     # firmware sends V directly
CURRENT_UNIT      = "A"
VOLTAGE_UNIT      = "V"
```

---

## Modifying the current / voltage protocol

The telemetry format is controlled by three settings in `config.py`:

```python
CURRENT_PREFIX = "CURRENT:"    # prefix that begins a current line
VOLTAGE_PREFIX = "VOLTAGE:"    # prefix that begins a voltage line

CURRENT_RAW_SCALE = 1e-3       # raw integer × scale = displayed value
VOLTAGE_RAW_SCALE = 1e-3
```

If the firmware changes its message format, update these three values and
restart the application.  No code changes are required.

To add a **new telemetry channel** (e.g. temperature):

1. Add a `TEMPERATURE_PREFIX` and `TEMPERATURE_RAW_SCALE` to `config.py`.
2. Add a regex pattern in `rtt_controller.py` and emit a new signal.
3. Connect the signal in `dashboard.py` and optionally add a card / graph
   in `monitoring_widget.py`.

---

## Project structure

```
gui/
├── main.py              Application entry point
├── config.py            All tuneable settings (edit this first)
├── rtt_connection.py    J-Link worker process + GUI-side shim (RTTLink)
├── rtt_controller.py    Protocol parser → typed Qt signals (STM32Controller)
├── monitoring_widget.py Live graph + value cards (shared current/voltage)
├── dashboard.py         Main window, tabs, connection bar, CSV logging
├── theme.py             Dark colour palette + Qt stylesheet
├── csv_logger.py        Thread-safe CSV file writer
├── requirements.txt     pip dependencies
└── pyproject.toml       uv / PEP 517 project file
```

---

## Architecture notes

### Why a separate process instead of a thread?

When a J-Link / USB call wedges (which can happen during a target hard-reset
mid-transaction), a blocked **native C call holds the Python GIL**.  No other
Python code in the same interpreter can run — including the Qt event loop —
until the call returns.  There is no safe way to interrupt a thread stuck in a
native call.

Putting J-Link calls in a **separate OS process** avoids this entirely.  The
GUI process's GIL is independent, so the GUI stays fully responsive.  If the
worker process wedges, the watchdog timer in `RTTLink` terminates and respawns
it (safe because killing a process is always clean, unlike killing a thread).

### Watchdog

`RTTLink` runs a 1-second QTimer that checks the age of the last heartbeat
from the worker.  If no heartbeat arrives within `WATCHDOG_TIMEOUT_S`
(currently `RTT_CHECK_TIMEOUT + 3 s`), the worker is terminated and a fresh
process is started.

### Data flow

```
Firmware (RTT) ──► worker process ──[mp.Queue]──► RTTLink._poll() (QTimer)
                                                      │
                                     line_received signal
                                                      │
                                         STM32Controller.handle_line()
                                          │                │
                               current_changed       voltage_changed
                                    │                      │
                        MonitoringWidget.push_current  push_voltage
                             │                               │
                        LiveChart (current)           LiveChart (voltage)
```

