"""Entry point for Nova Terminal — unified Bloomberg-style desktop."""

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from terminal.main_window import NovaTerminal


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Nova Terminal")
    app.setApplicationDisplayName("Nova Terminal — Indian Market Intelligence")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    window = NovaTerminal()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
