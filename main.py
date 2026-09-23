"""Bocpaste entry point."""
from __future__ import annotations

import ctypes
import os
import sys


def enable_dpi_awareness() -> None:
    """Per-Monitor v2 before Qt/Win32 create windows."""
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(-4):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def ensure_single_instance() -> tuple | None:
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    name = "bocpaste-single-instance"
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(200):
        # another instance is running
        sock.close()
        return None
    server = QLocalServer()
    QLocalServer.removeServer(name)
    server.listen(name)
    return server


def main() -> int:
    enable_dpi_awareness()

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

    from PySide6.QtWidgets import QApplication
    from app import config
    from app.application import AppController

    qapp = QApplication(sys.argv)
    qapp.setApplicationName(config.APP_NAME)
    qapp.setApplicationDisplayName(config.APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)

    server = ensure_single_instance()
    if server is None:
        return 0

    config.init_defaults()
    controller = AppController(qapp)
    controller.tray.show_welcome()

    # command-line action: main.py [snip|paste]
    from PySide6.QtCore import QTimer
    action = next((a for a in sys.argv[1:] if a in ("snip", "paste")), None)
    if action == "snip":
        QTimer.singleShot(150, controller.start_snip)
    elif action == "paste":
        QTimer.singleShot(150, controller.paste_from_clipboard)

    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
