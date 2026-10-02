"""Thread-safe CSV logger for live RTT streams.

One instance per data type (current / voltage).  The logger keeps its own
file handle and row buffer; all writes happen on the GUI thread (signals from
STM32Controller live on the GUI thread) so no locking is strictly required,
but a threading.Lock is included for safety if the caller moves to a worker.
"""

import csv
import os
from datetime import datetime
from threading import Lock

from config import LOG_FLUSH_EVERY


class CSVLogger:
    """Appends rows to a timestamped CSV file.

    One session = one file (rotated when :meth:`open` is called again).

    Columns written::

        timestamp   – session-relative seconds (float)
        host_time   – ISO-8601 wall-clock string (millisecond precision)
        <user cols> – one column per value in the ``values`` list
    """

    def __init__(self, folder: str, columns: list[str], prefix: str):
        """
        Args:
            folder:  Directory where CSV files are created (auto-created).
            columns: Header names for the data columns (e.g. ``["current_A"]``).
            prefix:  Short label prepended to the filename (e.g. ``"current"``).
        """
        self.folder  = folder
        self.columns = columns
        self.prefix  = prefix

        self._fh                  = None
        self._writer              = None
        self._rows_since_flush    = 0
        self._lock                = Lock()
        self._path                = ""
        self._enabled             = True

        os.makedirs(folder, exist_ok=True)

    # ---------------------------------------------------------------- public

    @property
    def path(self) -> str:
        """Absolute path of the currently open file, or ``""`` if closed."""
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool):
        self._enabled = on

    def open(self):
        """Open a fresh, timestamped CSV file.  Safe to call repeatedly;
        closes any previously open file first."""
        with self._lock:
            self._close_locked()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._path = os.path.join(self.folder, f"{self.prefix}_{ts}.csv")
            self._fh = open(self._path, "w", newline="", encoding="utf-8")
            self._writer = csv.writer(self._fh)
            self._writer.writerow(["timestamp", "host_time"] + self.columns)
            self._rows_since_flush = 0

    def write(self, values: list, timestamp: float | None = None):
        """Append one data row.

        Args:
            values:    List of numeric values (one per column).
            timestamp: Seconds since the session started, or ``None``.
        """
        if not self._enabled or self._writer is None:
            return
        with self._lock:
            host = datetime.now().isoformat(timespec="milliseconds")
            ts   = f"{timestamp:.4f}" if timestamp is not None else ""
            try:
                self._writer.writerow([ts, host] + [f"{v}" for v in values])
            except Exception:
                return
            self._rows_since_flush += 1
            if self._rows_since_flush >= LOG_FLUSH_EVERY:
                try:
                    self._fh.flush()
                except Exception:
                    pass
                self._rows_since_flush = 0

    def close(self):
        """Flush and close the current file."""
        with self._lock:
            self._close_locked()

    # --------------------------------------------------------------- private

    def _close_locked(self):
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
        self._fh     = None
        self._writer = None
        self._path   = ""

