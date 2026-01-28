#!/usr/bin/env python3
"""NapisyTWON - PDF Number Annotation Tool

A modern PDF annotation tool for adding numbered labels to PDF documents.
"""

import sys
import os

# Handle PyInstaller bundled paths
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Add src to path for imports
sys.path.insert(0, BASE_DIR)

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
    app.setApplicationName("NapisyTWON")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("NapisyTWON")

    # Set style
    app.setStyle("Fusion")

    # Set application icon
    icon_path = os.path.join(BASE_DIR, "resources", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

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
