"""Configuration settings for the STM32F407 HPPC Monitor.

Edit this file to change the target device, graph behaviour, logging
paths, telemetry format, and reconnect policy.  The rest of the
application reads values from here; no other file needs to change for
a protocol or hardware update.
"""

import os

# ----------------------------------------------------------------- J-Link ---

# SEGGER device name string used in JLink.connect().
TARGET_DEVICE = "STM32F407VG"

# RTT buffer indices.  0 / 0 is the default SEGGER choice.
RTT_UP_BUFFER   = 0   # host reads from this buffer (target → host)
RTT_DOWN_BUFFER = 0   # host writes to this buffer  (host → target)

# Max bytes the worker reads from the up-buffer in one call.
READ_CHUNK = 2048

# Max bytes the worker writes to the down-buffer in one call.
RTT_DOWN_CHUNK = 128

# SEGGER RTT control-block search range: "<start_hex> <length_hex>".
# For STM32F407 the internal SRAM starts at 0x20000000 (128 kB).
RTT_SEARCH_RANGES = "0x20000000 0x20000"

# Seconds to wait for the RTT control block to appear after connect.
# Must be longer than the firmware's startup time.
RTT_CHECK_TIMEOUT = 5.0

# ----------------------------------------------------------------- Timing ---

# Milliseconds between worker poll iterations (sleep at bottom of loop).
POLL_INTERVAL_MS = 10

# Minimum gap between successive commands sent to the target (ms).
COMMAND_INTERVAL_MS = 40

# Seconds to wait for a local echo before discarding it.
ECHO_TIMEOUT_S = 1.5

# --------------------------------------------------------------- Reconnect ---

# Attempt to reconnect automatically after a link failure.
AUTO_RECONNECT = True

# Initial delay before the first reconnect attempt (ms).
RECONNECT_DELAY_MS = 1000

# Upper bound on the exponential back-off delay (ms).
MAX_RECONNECT_DELAY_MS = 15000

# 0 = unlimited reconnect attempts.
MAX_RECONNECT_ATTEMPTS = 0

# --------------------------------------------------------------- Telemetry ---

# ---- Expected message format from the firmware (via RTT) ----
#
# Each line is:  PREFIX<value>\n
#
#   CURRENT:<integer_milliamperes>
#   VOLTAGE:<integer_millivolts>
#
# Examples (matching the INA226 firmware output):
#   CURRENT:1250      → 1.250 A
#   VOLTAGE:16320     → 16.320 V
#
# Change the PREFIX constants below if the firmware uses different names.
# Change the scale factors if the firmware sends different units.

CURRENT_PREFIX = "CURRENT:"   # line prefix for current readings
VOLTAGE_PREFIX = "VOLTAGE:"   # line prefix for voltage readings

# Scaling from the raw integer value the firmware sends to the display unit.
#   raw = integer in the RTT line
#   displayed = raw * SCALE
CURRENT_RAW_SCALE = 1e-3      # firmware sends mA, display in A
VOLTAGE_RAW_SCALE = 1e-3      # firmware sends mV, display in V

# Units shown on the graphs and value cards.  Change to "mA" / "mV" if you
# set the SCALE factors to 1.0 and want to keep raw units.
CURRENT_UNIT = "A"
VOLTAGE_UNIT = "V"

# Host-side throttle: forward at most one line per prefix per N seconds.
# 0 = forward every line (recommended for high-rate streams like current/voltage).
TELEMETRY_MIN_INTERVAL_S: dict[str, float] = {
    CURRENT_PREFIX: 0,
    VOLTAGE_PREFIX: 0,
}

# ------------------------------------------------------------------ Graphs ---

# Number of samples kept per channel in the rolling deque.
# At 100 Hz, 3000 samples ≈ 30 s of history.
GRAPH_HISTORY_SAMPLES = 3000

# Graph redraw period in milliseconds (~20 fps).  Decoupled from data rate.
GRAPH_REDRAW_MS = 50

# Default moving-average window (samples).
MOVING_AVERAGE_WINDOW = 5

# Whether moving-average smoothing is enabled on startup.
MOVING_AVERAGE_ENABLED = True

# Colours and labels for current channels.
# Add more entries (and update the firmware) to plot multiple channels.
CURRENT_CH_COLORS  = ["#22D3EE"]
CURRENT_CH_LABELS  = ["Current"]

# Colours and labels for voltage channels.
VOLTAGE_CH_COLORS  = ["#A78BFA"]
VOLTAGE_CH_LABELS  = ["Voltage"]

# ----------------------------------------------------------------- Logging ---

# Root folder for all CSV session logs.
# Default: a  logs/  subfolder right next to this config file, so the files
# are easy to find in the project directory.
# Change to any absolute path, e.g.:
#   LOG_ROOT = r"C:\Users\user\Desktop\HPPC_Logs"
_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_ROOT        = os.path.join(_HERE, "logs")
LOG_DIR_CURRENT = os.path.join(LOG_ROOT, "current")
LOG_DIR_VOLTAGE = os.path.join(LOG_ROOT, "voltage")

# Open a new CSV file every time the GUI connects (True) or keep one file
# for the entire application run (False).
LOG_ROTATE_ON_CONNECT = True

# Flush the CSV to disk every N rows.  Smaller = safer; larger = faster.
LOG_FLUSH_EVERY = 20

# ---------------------------------------------------------------- Commands ---
# RTT command strings sent to the target over the down-buffer.
# The firmware must implement a line-based command parser that reads '\n'-
# terminated ASCII commands and acts on them.

CMD_RESET_ALL      = "RESET_ALL"
CMD_CHARGE         = "CHARGE"
CMD_DISCHARGE_HIGH = "DISCHARGE_HIGH"
CMD_DISCHARGE_LOW  = "DISCHARGE_LOW"
CMD_START_HPPC     = "START_HPPC"
CMD_STOP_HPPC      = "STOP_HPPC"

