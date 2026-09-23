"""Persistent settings backed by a portable config.ini next to the program."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor

APP_NAME = "Bocpaste"
APP_VERSION = "1.0.0"
ORG_NAME = "Bocpaste"


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


_SETTINGS: QSettings | None = None


def settings() -> QSettings:
    global _SETTINGS
    if _SETTINGS is None:
        path = os.path.join(app_dir(), "config.ini")
        _SETTINGS = QSettings(path, QSettings.IniFormat)
        _SETTINGS.setFallbacksEnabled(False)
    return _SETTINGS


# --- keys & defaults -------------------------------------------------------
class HK:
    SNIP = "hotkey/snip"
    PASTE = "hotkey/paste"
    TOGGLE_PASTERS = "hotkey/toggle_pasters"


class K:
    # General
    TRAY_SHOW_HINT = "general/tray_hint_shown"
    HISTORY_LIMIT = "general/history_limit"
    # Snip
    MASK_COLOR = "snip/mask_color"
    MASK_ALPHA = "snip/mask_alpha"
    BORDER_COLOR = "snip/border_color"
    MAGNIFIER = "snip/magnifier"
    MAGNIFIER_ZOOM = "snip/magnifier_zoom"
    SHOW_PIXEL_GRID = "snip/pixel_grid"
    SHOW_SIZE = "snip/show_size"
    AUTO_COPY_ON_CLOSE = "snip/auto_copy"
    QUICK_SAVE_DIR = "snip/quick_save_dir"
    SOUND = "snip/sound"
    SET_CLIPBOARD_AFTER_SNIP = "snip/clipboard_after_snip"
    # annotation defaults
    PEN_COLOR = "annot/pen_color"
    PEN_WIDTH = "annot/pen_width"
    # Paste
    PASTE_SHADOW = "paste/shadow"
    PASTE_OPACITY = "paste/opacity"
    PASTE_ZOOM_STEP = "paste/zoom_step"
    PASTE_ESC_CLOSES = "paste/esc_closes"
    PASTE_SNAP = "paste/snap"


_DEFAULTS = {
    HK.SNIP: "F1",
    HK.PASTE: "Ctrl+F1",
    HK.TOGGLE_PASTERS: "Ctrl+Shift+`",
    K.TRAY_SHOW_HINT: False,
    K.HISTORY_LIMIT: 10,
    K.MASK_COLOR: "#000000",
    K.MASK_ALPHA: 110,            # 0-255
    K.BORDER_COLOR: "#169fe6",
    K.MAGNIFIER: True,
    K.MAGNIFIER_ZOOM: 8,
    K.SHOW_PIXEL_GRID: True,
    K.SHOW_SIZE: True,
    K.AUTO_COPY_ON_CLOSE: False,
    K.QUICK_SAVE_DIR: "",
    K.SOUND: False,
    K.SET_CLIPBOARD_AFTER_SNIP: False,
    K.PEN_COLOR: "#FF0000",
    K.PEN_WIDTH: 2,
    K.PASTE_SHADOW: True,
    K.PASTE_OPACITY: 255,
    K.PASTE_ZOOM_STEP: 10,
    K.PASTE_ESC_CLOSES: True,
    K.PASTE_SNAP: True,
}


def init_defaults() -> None:
    s = settings()
    for key, val in _DEFAULTS.items():
        if not s.contains(key):
            s.setValue(key, val)


def get(key: str, default=None):
    s = settings()
    val = s.value(key, _DEFAULTS.get(key, default))
    return val


def set_value(key: str, value) -> None:
    settings().setValue(key, value)


def get_int(key: str) -> int:
    try:
        return int(get(key))
    except (TypeError, ValueError):
        return int(_DEFAULTS.get(key, 0))


def get_bool(key: str) -> bool:
    val = get(key)
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("1", "true", "yes", "on")


def get_color(key: str) -> QColor:
    return QColor(str(get(key)))


def history_dir() -> str:
    d = os.path.join(app_dir(), "history")
    os.makedirs(d, exist_ok=True)
    return d
