"""Application entry point.

Usage
-----
    python main.py

The worker process is spawned lazily when the user clicks Connect.  Nothing
talks to J-Link on startup.
"""

import multiprocessing
import sys

from PyQt5.QtWidgets import QApplication

from dashboard import MainWindow
from theme import app_stylesheet


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(app_stylesheet())

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    # Required on Windows when the application is frozen with PyInstaller.
    # Harmless on other platforms.
    multiprocessing.freeze_support()
    main()

