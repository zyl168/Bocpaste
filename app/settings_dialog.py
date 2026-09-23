"""Preferences dialog: general, hotkeys, snip and paste pages."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget, QKeySequenceEdit,
                               QDialog, QDialogButtonBox)

from . import config

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = config.APP_NAME


# ---------------------------------------------------------------------- #
# autostart
# ---------------------------------------------------------------------- #
def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = sys.executable
    if pythonw.lower().endswith("python.exe"):
        pythonw = os.path.join(os.path.dirname(pythonw), "pythonw.exe")
    main_py = os.path.join(config.app_dir(), "main.py")
    return f'"{pythonw}" "{main_py}"'


def is_autostart() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _VALUE_NAME)
        return True
    except OSError:
        return False


def set_autostart(enable: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                        winreg.KEY_SET_VALUE | winreg.KEY_READ) as k:
        if enable:
            winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, _VALUE_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------- #
# small widgets
# ---------------------------------------------------------------------- #
class ColorButton(QPushButton):
    def __init__(self, color: QColor, title="选择颜色"):
        super().__init__()
        self._color = QColor(color)
        self._title = title
        self.setFixedWidth(70)
        self.clicked.connect(self._pick)
        self._show()

    def _show(self):
        self.setText(self._color.name())
        self.setStyleSheet(
            f"background:{self._color.name()};"
            f"color:{'#000' if self._color.lightness() > 150 else '#fff'};"
            "border-radius:4px; padding:4px;")

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, self._title)
        if c.isValid():
            self._color = c
            self._show()

    def color(self) -> QColor:
        return self._color


# ---------------------------------------------------------------------- #
# dialog
# ---------------------------------------------------------------------- #
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("首选项")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._general_tab(), "常规")
        self.tabs.addTab(self._hotkey_tab(), "快捷键")
        self.tabs.addTab(self._snip_tab(), "截图")
        self.tabs.addTab(self._paste_tab(), "贴图")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- general ------------------------------------------------------------
    def _general_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.chk_autostart = QCheckBox("开机时自动启动")
        self.chk_autostart.setChecked(is_autostart())
        form.addRow(self.chk_autostart)

        self.spin_history = QSpinBox()
        self.spin_history.setRange(1, 100)
        self.spin_history.setValue(config.get_int(config.K.HISTORY_LIMIT))
        form.addRow("历史记录数量", self.spin_history)

        self.chk_sound = QCheckBox("截图时播放提示音")
        self.chk_sound.setChecked(config.get_bool(config.K.SOUND))
        form.addRow(self.chk_sound)
        return w

    # -- hotkeys ------------------------------------------------------------
    def _hotkey_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.se_snip = QKeySequenceEdit(QKeySequence(
            str(config.get(config.HK.SNIP))))
        self.se_snip.setMaximumSequenceLength(1)
        form.addRow("截图", self.se_snip)
        self.se_paste = QKeySequenceEdit(QKeySequence(
            str(config.get(config.HK.PASTE))))
        self.se_paste.setMaximumSequenceLength(1)
        form.addRow("将剪贴板内容贴图", self.se_paste)
        self.se_toggle = QKeySequenceEdit(QKeySequence(
            str(config.get(config.HK.TOGGLE_PASTERS))))
        self.se_toggle.setMaximumSequenceLength(1)
        form.addRow("显示/隐藏所有贴图", self.se_toggle)

        hint = QLabel("支持单键（如 F1）和组合键。\n修改后立即生效。")
        hint.setStyleSheet("color:#888;")
        form.addRow(hint)
        return w

    # -- snip ---------------------------------------------------------------
    def _snip_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        form = QFormLayout()
        outer.addLayout(form)

        self.btn_mask = ColorButton(config.get_color(config.K.MASK_COLOR),
                                    "遮罩颜色")
        form.addRow("遮罩颜色", self.btn_mask)
        self.slider_mask = QSlider(Qt.Horizontal)
        self.slider_mask.setRange(0, 255)
        self.slider_mask.setValue(config.get_int(config.K.MASK_ALPHA))
        form.addRow("遮罩浓度", self._with_value(self.slider_mask))

        self.btn_border = ColorButton(config.get_color(config.K.BORDER_COLOR),
                                      "边框颜色")
        form.addRow("选区边框颜色", self.btn_border)

        self.chk_louvre = QCheckBox("显示放大镜")
        self.chk_louvre.setChecked(config.get_bool(config.K.MAGNIFIER))
        form.addRow(self.chk_louvre)

        self.spin_zoom = QSpinBox()
        self.spin_zoom.setRange(2, 20)
        self.spin_zoom.setValue(config.get_int(config.K.MAGNIFIER_ZOOM))
        form.addRow("放大镜倍数", self.spin_zoom)

        self.chk_grid = QCheckBox("放大镜中显示像素网格")
        self.chk_grid.setChecked(config.get_bool(config.K.SHOW_PIXEL_GRID))
        form.addRow(self.chk_grid)

        self.chk_size = QCheckBox("显示选区尺寸")
        self.chk_size.setChecked(config.get_bool(config.K.SHOW_SIZE))
        form.addRow(self.chk_size)
        return w

    # -- paste --------------------------------------------------------------
    def _paste_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.chk_shadow = QCheckBox("贴图显示阴影")
        self.chk_shadow.setChecked(config.get_bool(config.K.PASTE_SHADOW))
        form.addRow(self.chk_shadow)

        self.chk_snap = QCheckBox("移动时边缘自动吸附")
        self.chk_snap.setChecked(config.get_bool(config.K.PASTE_SNAP))
        form.addRow(self.chk_snap)

        self.chk_esc = QCheckBox("按 Esc 关闭贴图")
        self.chk_esc.setChecked(config.get_bool(config.K.PASTE_ESC_CLOSES))
        form.addRow(self.chk_esc)

        self.spin_zoom_step = QSpinBox()
        self.spin_zoom_step.setRange(1, 100)
        self.spin_zoom_step.setValue(config.get_int(config.K.PASTE_ZOOM_STEP))
        form.addRow("滚轮缩放步长 (%)", self.spin_zoom_step)
        return w

    # -- helpers ------------------------------------------------------------
    def _with_value(self, slider: QSlider):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        label = QLabel(str(slider.value()))
        slider.valueChanged.connect(label.setNum if hasattr(
            label, "setNum") else (lambda v: label.setText(str(v))))
        h.addWidget(slider)
        h.addWidget(label)
        return box

    # -- save ---------------------------------------------------------------
    def _save(self):
        set_autostart(self.chk_autostart.isChecked())
        config.set_value(config.K.HISTORY_LIMIT, self.spin_history.value())
        config.set_value(config.K.SOUND, self.chk_sound.isChecked())

        config.set_value(config.HK.SNIP,
                         self.se_snip.keySequence().toString(
                             QKeySequence.PortableText) or "F1")
        config.set_value(config.HK.PASTE,
                         self.se_paste.keySequence().toString(
                             QKeySequence.PortableText) or "Ctrl+F1")
        config.set_value(config.HK.TOGGLE_PASTERS,
                         self.se_toggle.keySequence().toString(
                             QKeySequence.PortableText) or "Ctrl+Shift+`")

        config.set_value(config.K.MASK_COLOR, self.btn_mask.color().name())
        config.set_value(config.K.MASK_ALPHA, self.slider_mask.value())
        config.set_value(config.K.BORDER_COLOR, self.btn_border.color().name())
        config.set_value(config.K.MAGNIFIER, self.chk_louvre.isChecked())
        config.set_value(config.K.MAGNIFIER_ZOOM, self.spin_zoom.value())
        config.set_value(config.K.SHOW_PIXEL_GRID, self.chk_grid.isChecked())
        config.set_value(config.K.SHOW_SIZE, self.chk_size.isChecked())

        config.set_value(config.K.PASTE_SHADOW, self.chk_shadow.isChecked())
        config.set_value(config.K.PASTE_SNAP, self.chk_snap.isChecked())
        config.set_value(config.K.PASTE_ESC_CLOSES, self.chk_esc.isChecked())
        config.set_value(config.K.PASTE_ZOOM_STEP, self.spin_zoom_step.value())

        self.accept()
