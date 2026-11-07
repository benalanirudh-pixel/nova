"""Entry point for Nova's main desktop assistant UI."""

import sys

from PySide6.QtWidgets import QApplication

from ui import NovaWindow
from ui.theme import apply_theme


def main():
    app = QApplication(sys.argv)

    app.setApplicationName("Nova")
    app.setApplicationDisplayName("Nova — Personal AI Command System")
    app.setStyle("Fusion")

    apply_theme(app)

    window = NovaWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
