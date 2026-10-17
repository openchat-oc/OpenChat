#!/usr/bin/env python3
"""Punto de entrada de OpenChat: ``python -m app.main``."""
import sys

from . import APP_NAME, config


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from .ui.main_window import MainWindow
    from .ui.theme import QSS

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(QSS)
    config.setup_logging()
    win = MainWindow(config.Settings())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
