#!/usr/bin/env python3
"""Napisy-TWON v2 - PDF Number Annotation Tool

A modern PDF annotation tool for adding numbered labels to PDF documents.
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from src.main_window import MainWindow


def main():
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Napisy-TWON")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("NapisyTWON")

    # Set style
    app.setStyle("Fusion")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Open file from command line if provided
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
            window._do_open_file(file_path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
