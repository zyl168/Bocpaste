"""The floating annotation toolbar shown beneath the snip selection."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QToolButton, QWidget,
                               QColorDialog)

from .. import icons

TOOL_SPEC = [
    ("rectangle", "矩形框 (1)"),
    ("ellipse", "椭圆 (2)"),
    ("arrow", "箭头 (3)"),
    ("line", "直线 (4)"),
    ("pencil", "画笔 (5)"),
    ("marker", "马克笔 (6)"),
    ("text", "文字 (7)"),
    ("mosaic", "马赛克 (8)"),
    ("blur", "模糊 (8)"),
    ("number", "序号 (9)"),
    ("eraser", "橡皮擦 (0)"),
]

PRESET_COLORS = [
    "#FF1D1D", "#FF8C00", "#FFD400", "#2ECC40", "#00C2C2",
    "#169FE6", "#8A2BE2", "#FF6FB5",
    "#000000", "#4A4A4A", "#9B9B9B", "#E0E0E0",
    "#FFFFFF", "#8B4513", "#11611B", "#1B2A6B",
]

QSS = """
QFrame#Toolbar { background: #26292e; border-radius: 7px; }
QToolButton { background: transparent; border: none; border-radius: 5px;
              margin: 1px; }
QToolButton:hover { background: #3b4048; }
QToolButton:checked { background: #169fe6; }
QLabel { color: #cfd3d8; }
QSlider::groove:horizontal { height: 4px; background: #44484f; border-radius:2px;}
QSlider::handle:horizontal { width: 12px; margin: -5px 0; border-radius:6px;
                             background: #d8dce0; }
QPushButton#swatch { border: 1px solid #555a62; border-radius: 5px; }
QPushButton#accent { background:#21a35a; border:none; border-radius:5px;}
QPushButton#accent:hover { background:#28b866; }
"""


class ColorPopup(QFrame):
    picked = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet("QFrame { background:#2c2f35; border-radius:8px; }")
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(4)
        for i, hexc in enumerate(PRESET_COLORS):
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setStyleSheet(
                f"background:{hexc}; border-radius:4px; border:none;")
            b.clicked.connect(lambda _=False, c=hexc: self._pick(c))
            grid.addWidget(b, i // 8, i % 8)
        custom = QPushButton("自定义颜色…")
        custom.setStyleSheet("color:#e6e6e6; border:none; padding:4px;")
        custom.clicked.connect(self._custom)
        grid.addWidget(custom, grid.rowCount(), 0, 1, 8)

    def _pick(self, hexc):
        self.picked.emit(QColor(hexc))
        self.close()

    def _custom(self):
        c = QColorDialog.getColor(Qt.red, self, "选择颜色")
        if c.isValid():
            self.picked.emit(c)
        self.close()


class SnippetToolbar(QFrame):
    toolChosen = Signal(str)
    undoRequested = Signal()
    redoRequested = Signal()
    pinRequested = Signal()
    saveRequested = Signal()
    copyRequested = Signal()
    closeRequested = Signal()
    colorChosen = Signal(QColor)
    widthChanged = Signal(int)

    def __init__(self, parent=None, color: QColor = QColor("#ff1d1d"),
                 width: int = 2):
        super().__init__(parent)
        self.setObjectName("Toolbar")
        self.setStyleSheet(QSS)
        self.setAttribute(Qt.WA_StyledBackground)
        self._tool_buttons: dict[str, QToolButton] = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 5)
        lay.setSpacing(2)

        for name, tip in TOOL_SPEC:
            b = QToolButton()
            b.setFixedSize(30, 30)
            b.setIcon(icons.icon(name))
            b.setToolTip(tip)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, n=name: self._choose(n))
            self._tool_buttons[name] = b
            lay.addWidget(b)

        lay.addWidget(_separator())
        self.undo_button = self._action("undo", "撤销 (Ctrl+Z)",
                                        self.undoRequested)
        self.redo_button = self._action("redo", "重做 (Ctrl+Y)",
                                        self.redoRequested)
        lay.addWidget(self.undo_button)
        lay.addWidget(self.redo_button)
        lay.addWidget(_separator())

        self.swatch = QPushButton()
        self.swatch.setObjectName("swatch")
        self.swatch.setFixedSize(30, 30)
        self.set_swatch_color(color)
        self.swatch.clicked.connect(self._show_colors)
        lay.addWidget(self.swatch)

        self.width_value = QLabel(str(width))
        self.width_value.setFixedWidth(16)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, 30)
        self.slider.setValue(int(width))
        self.slider.setFixedWidth(92)
        self.slider.valueChanged.connect(self._width_changed)
        lay.addWidget(self.slider)
        lay.addWidget(self.width_value)

        lay.addWidget(_separator())
        lay.addWidget(self._action("pin", "钉到屏幕 (Ctrl+D)",
                                   self.pinRequested))
        lay.addWidget(self._action("save", "保存 (Ctrl+S)", self.saveRequested))

        self.copy_button = QToolButton()
        self.copy_button.setFixedSize(46, 30)
        self.copy_button.setIcon(icons.icon("copy"))
        self.copy_button.setToolTip("复制并退出 (Enter)")
        self.copy_button.clicked.connect(self.copyRequested.emit)
        lay.addWidget(self.copy_button)

        self.close_button = self._action("close", "取消 (Esc)",
                                         self.closeRequested)
        lay.addWidget(self.close_button)

        self._popup = ColorPopup()
        self._popup.picked.connect(self._color_picked)

    # -- helpers ------------------------------------------------------------
    def _action(self, icon_name, tip, signal):
        b = QToolButton()
        b.setFixedSize(30, 30)
        b.setIcon(icons.icon(icon_name))
        b.setToolTip(tip)
        b.clicked.connect(signal.emit)
        return b

    def _choose(self, name):
        # Qt toggles the checkable button BEFORE emitting clicked, so the
        # button's own new state tells us select (checked) or deselect.
        b = self._tool_buttons[name]
        # block signals while unchecking the others to avoid re-entrant toggled
        for n, other in self._tool_buttons.items():
            if n != name and other.isChecked():
                other.blockSignals(True)
                other.setChecked(False)
                other.blockSignals(False)
        self.toolChosen.emit(name if b.isChecked() else "")

    def current_tool(self) -> str:
        for n, b in self._tool_buttons.items():
            if b.isChecked():
                return n
        return ""

    def clear_tool(self):
        for b in self._tool_buttons.values():
            b.setChecked(False)

    def select_tool(self, name: str):
        """Sync checked state from keyboard without re-emitting."""
        for n, b in self._tool_buttons.items():
            b.setChecked(n == name)

    def _show_colors(self):
        pos = self.swatch.mapToGlobal(QPoint(0, self.swatch.height() + 2))
        self._popup.move(pos)
        self._popup.show()

    def _color_picked(self, color):
        self.set_swatch_color(color)
        self.colorChosen.emit(color)

    def set_swatch_color(self, color: QColor):
        self.swatch.setStyleSheet(
            f"background:{color.name()}; border-radius:5px;"
            "border:1px solid #555a62;")

    def _width_changed(self, v):
        self.width_value.setText(str(v))
        self.widthChanged.emit(int(v))

    def set_history_enabled(self, can_undo: bool, can_redo: bool):
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)


def _separator() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color:#3a3e44;")
    f.setFixedHeight(24)
    return f
