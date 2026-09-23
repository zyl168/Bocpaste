"""In-place transparent multi-line text editor used by the text tool."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QTextCursor
from PySide6.QtWidgets import QTextEdit


class TextEditor(QTextEdit):
    accepted = Signal(str)
    rejected = Signal()

    def __init__(self, parent, pos: QPointF, color: QColor, width: int,
                 max_width: int):
        super().__init__(parent)
        self._max_width = max(200, max_width)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setFrameStyle(0)
        self.setFont(_make_font(width))
        # visible frame so the editing box is discoverable (Snipaste-style)
        self.setStyleSheet(
            "QTextEdit { background: rgba(255, 255, 255, 50);"
            " border: 1px dashed #169fe6; }")
        self.setCursorWidth(2)
        self.setTextColor(color)

        self._anchor = QPointF(pos)
        fm = QFontMetrics(self.font())
        self._line_h = fm.height()
        self.move(int(pos.x()), int(pos.y() - self._line_h))
        self.resize(min(self._max_width, fm.horizontalAdvance("M") * 16),
                    self._line_h + 6)
        self.document().contentsChanged.connect(self._resize_to_contents)
        # children created after the parent is shown stay hidden until show()
        self.show()
        self.raise_()
        self.setFocus()

    def _resize_to_contents(self):
        fm = QFontMetrics(self.font())
        text = self.toPlainText()
        w = min(self._max_width, max(40, fm.horizontalAdvance(text) + 12))
        lines = max(1, text.count("\n") + 1)
        h = self._line_h * lines + 8
        x = int(self._anchor.x())
        y = int(self._anchor.y() - h)
        self.move(x, y)
        self.resize(int(w), int(h))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ControlModifier:
                super().keyPressEvent(event)   # Ctrl+Enter = newline
                return
            self.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.rejected.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.accept()

    def accept(self):
        text = self.toPlainText().strip()
        self.accepted.emit(text)

    def final_pos(self):
        """Bottom-left insertion point (matches TextShape anchor)."""
        return QPointF(self.x(), self.y() + self.height())


def _make_font(width: int) -> QFont:
    f = QFont()
    f.setPixelSize(max(13, int(width) * 8))
    return f
