"""Top-level controller wiring hotkeys, capture, pasters, tray and settings."""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor

from . import config
from .hotkey_manager import HotkeyManager
from .paste.paster_manager import PasterManager
from .settings_dialog import SettingsDialog
from .snip.capture import capture_virtual_desktop
from .snip.snipper import Snipper
from .tray import TrayIcon


class AppController(QObject):
    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp

        self.paster_manager = PasterManager()

        self.hotkeys = HotkeyManager()
        self._bind_hotkeys()
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkeys.start()

        self.tray = TrayIcon(self)
        self.tray.show()

        self.snipper: Snipper | None = None

    # ------------------------------------------------------------------ #
    @staticmethod
    def fg_color() -> QColor:
        return QColor("#2f3338")

    def _bind_hotkeys(self):
        self.hotkeys.bind("snip", str(config.get(config.HK.SNIP)))
        self.hotkeys.bind("paste", str(config.get(config.HK.PASTE)))
        self.hotkeys.bind("toggle", str(config.get(config.HK.TOGGLE_PASTERS)))

    def _on_hotkey(self, action_id: str):
        if action_id == "snip":
            self.start_snip()
        elif action_id == "paste":
            self.paste_from_clipboard()
        elif action_id == "toggle":
            self.toggle_pasters()

    # ------------------------------------------------------------------ #
    # snipping
    # ------------------------------------------------------------------ #
    def start_snip(self):
        if self.snipper is not None:
            self.snipper.raise_()
            self.snipper.activateWindow()
            return
        capture = capture_virtual_desktop()
        self.snipper = Snipper(capture, self._pin_from_snip)
        self.snipper.closed.connect(self._snipper_closed)
        self.snipper.start_snip()

    def _snipper_closed(self):
        if self.snipper is not None:
            # deterministic teardown: a hidden Qt.Tool overlay must not linger
            # (it keeps a 16 MB capture alive and can receive stray events)
            self.snipper.deleteLater()
        self.snipper = None

    def _pin_from_snip(self, pixmap, global_topleft, display_scale=1.0):
        self.paster_manager.add_pixmap(pixmap, anchor=global_topleft,
                                       display_scale=display_scale)

    # ------------------------------------------------------------------ #
    def paste_from_clipboard(self):
        self.paster_manager.add_from_clipboard()

    def toggle_pasters(self):
        self.paster_manager.toggle_all_visibility()

    def open_settings(self):
        dlg = SettingsDialog()
        if dlg.exec():
            self._bind_hotkeys()

    # ------------------------------------------------------------------ #
    def quit(self):
        self.hotkeys.stop()
        self.paster_manager.close_all()
        self.tray.hide()
        self.qapp.quit()
