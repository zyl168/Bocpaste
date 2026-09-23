"""Annotation shapes rendered on top of the captured image."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF, QPainterPathStroker)

RECT = "rectangle"
ELLIPSE = "ellipse"
ARROW = "arrow"
LINE = "line"
PENCIL = "pencil"
MARKER = "marker"
TEXT = "text"
MOSAIC = "mosaic"
BLUR = "blur"
NUMBER = "number"
ERASER = "eraser"

STROKE_TOOLS = {RECT, ELLIPSE, ARROW, LINE, PENCIL, MARKER}


def _normalised(a: QPointF, b: QPointF) -> tuple[QPointF, QPointF]:
    x1, y1 = a.x(), a.y()
    x2, y2 = b.x(), b.y()
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return QPointF(x1, y1), QPointF(x2, y2)


class Shape:
    kind = ""

    def __init__(self, color=QColor("#ff0000"), width=2):
        self.color = QColor(color)
        self.width = width

    # -- geometry -----------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return QRectF()

    def outline_path(self) -> QPainterPath:
        """Area occupied by the shape, used for eraser hit-testing."""
        return QPainterPath()

    # -- painting -----------------------------------------------------------
    def paint(self, painter: QPainter) -> None:
        pass

    def _stroke_pen(self) -> QPen:
        p = QPen(self.color)
        p.setWidthF(max(1.0, float(self.width)))
        p.setCapStyle(Qt.RoundCap)
        p.setJoinStyle(Qt.RoundJoin)
        return p


class _TwoPoint(Shape):
    def __init__(self, a, b, color, width):
        super().__init__(color, width)
        self.a = QPointF(a)
        self.b = QPointF(b)

    def set_end(self, b):
        self.b = QPointF(b)

    def boundingRect(self) -> QRectF:
        return QRectF(self.a, self.b).normalized()


class RectShape(_TwoPoint):
    kind = RECT

    def _rect(self) -> QRectF:
        a, b = _normalised(self.a, self.b)
        return QRectF(a, b)

    def paint(self, painter):
        painter.setPen(self._stroke_pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect())

    def outline_path(self):
        path = QPainterPath()
        r = self._rect()
        if r.width() < 1 and r.height() < 1:
            return path
        path.addRect(r)
        stroker = QPainterPathStroker()
        stroker.setWidth(float(self.width) + 6)
        stroker.setCapStyle(Qt.RoundCap)
        return stroker.createStroke(path)


class EllipseShape(_TwoPoint):
    kind = ELLIPSE

    def paint(self, painter):
        painter.setPen(self._stroke_pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self.boundingRect())

    def outline_path(self):
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        stroker = QPainterPathStroker()
        stroker.setWidth(float(self.width) + 6)
        return stroker.createStroke(path)


class LineShape(_TwoPoint):
    kind = LINE

    def paint(self, painter):
        painter.setPen(self._stroke_pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(self.a, self.b)

    def outline_path(self):
        path = QPainterPath()
        path.moveTo(self.a); path.lineTo(self.b)
        stroker = QPainterPathStroker()
        stroker.setWidth(float(self.width) + 6)
        stroker.setCapStyle(Qt.RoundCap)
        return stroker.createStroke(path)


class ArrowShape(_TwoPoint):
    kind = ARROW

    def _head_size(self) -> float:
        return max(9.0, float(self.width) * 4.0 + 5)

    def _shaft_end(self) -> tuple[QPointF, float]:
        """Return (tip_point, angle) — tip is the arrowhead apex at self.b;
        the shaft line stops `head_size` before self.b so the line doesn't
        poke past the arrowhead."""
        dx = self.b.x() - self.a.x()
        dy = self.b.y() - self.a.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return QPointF(self.b), 0.0
        angle = math.atan2(dy, dx)
        return QPointF(self.b), angle, length

    def paint(self, painter):
        tip, angle, length = self._shaft_end()
        head = self._head_size()
        painter.setPen(self._stroke_pen())
        # shaft stops where the arrowhead base begins
        if length > head + 1:
            shrink = head * 0.78   # roughly the base midpoint of the head
            shaft_end = QPointF(
                tip.x() - shrink * math.cos(angle),
                tip.y() - shrink * math.sin(angle))
            painter.drawLine(self.a, shaft_end)
        # filled arrowhead
        a1 = angle + math.radians(155)
        a2 = angle - math.radians(155)
        p1 = QPointF(tip.x() + head * math.cos(a1),
                     tip.y() + head * math.sin(a1))
        p2 = QPointF(tip.x() + head * math.cos(a2),
                     tip.y() + head * math.sin(a2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)
        painter.drawPolygon(QPolygonF([tip, p1, p2]))

    def outline_path(self):
        tip, angle, length = self._shaft_end()
        head = self._head_size()
        path = QPainterPath()
        path.moveTo(self.a)
        path.lineTo(tip)
        # widen the hit area around the head
        a1 = angle + math.radians(155)
        a2 = angle - math.radians(155)
        p1 = QPointF(tip.x() + head * math.cos(a1),
                     tip.y() + head * math.sin(a1))
        p2 = QPointF(tip.x() + head * math.cos(a2),
                     tip.y() + head * math.sin(a2))
        path.lineTo(p1); path.lineTo(p2); path.closeSubpath()
        stroker = QPainterPathStroker()
        stroker.setWidth(max(6.0, float(self.width) + 4))
        stroker.setCapStyle(Qt.RoundCap)
        return stroker.createStroke(path).united(path)


class PathShape(Shape):
    def __init__(self, start, color, width, kind=PENCIL):
        super().__init__(color, width)
        self.kind = kind
        self._path = QPainterPath(QPointF(start))

    def add_point(self, pt):
        self._path.lineTo(QPointF(pt))

    def path(self) -> QPainterPath:
        return self._path

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect().adjusted(-self.width, -self.width,
                                                  self.width, self.width)

    def paint(self, painter):
        if self.kind == MARKER:
            col = QColor(self.color)
            col.setAlpha(95)
            pen = QPen(col)
            pen.setWidthF(max(6.0, float(self.width) * 4.0))
            pen.setCapStyle(Qt.FlatCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
        else:
            painter.setPen(self._stroke_pen())
        # stroke only: a leftover brush from another shape would fill the path
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self._path)

    def outline_path(self):
        stroker = QPainterPathStroker()
        extra = float(self.width) * (4 if self.kind == MARKER else 1) + 6
        stroker.setWidth(extra)
        stroker.setCapStyle(Qt.RoundCap)
        return stroker.createStroke(self._path)


class TextShape(Shape):
    kind = TEXT

    def __init__(self, pos, text, color, width):
        super().__init__(color, width)
        self.pos = QPointF(pos)
        self.text = text
        self.font = QFont()
        self.font.setPixelSize(max(13, int(width) * 8))

    def boundingRect(self) -> QRectF:
        from PySide6.QtGui import QFontMetricsF
        fm = QFontMetricsF(self.font)
        w = max(20.0, fm.horizontalAdvance(self.text) + 6)
        h = fm.height() + 4
        return QRectF(self.pos.x(), self.pos.y() - h, w, h)

    def paint(self, painter):
        painter.setFont(self.font)
        painter.setPen(self.color)
        painter.drawText(self.boundingRect(),
                         Qt.AlignLeft | Qt.AlignVCenter, self.text)

    def outline_path(self):
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path


class NumberShape(Shape):
    kind = NUMBER

    def __init__(self, pos, n, color, width):
        super().__init__(color, width)
        self.pos = QPointF(pos)
        self.n = n
        self.radius = max(12.0, float(width) * 5 + 8)

    def boundingRect(self) -> QRectF:
        return QRectF(self.pos.x() - self.radius,
                      self.pos.y() - self.radius,
                      self.radius * 2, self.radius * 2)

    def paint(self, painter):
        painter.setPen(self._stroke_pen())
        painter.setBrush(QColor(self.color.red(), self.color.green(),
                                self.color.blue(), 50))
        painter.drawEllipse(self.pos, self.radius, self.radius)
        painter.setPen(self.color)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(self.radius * 1.2))
        painter.setFont(f)
        painter.drawText(self.boundingRect(), Qt.AlignCenter, str(self.n))

    def outline_path(self):
        path = QPainterPath()
        path.addEllipse(self.pos, self.radius, self.radius)
        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        return stroker.createStroke(path).united(path)


class MosaicShape(Shape):
    """Pixelate or blur a rectangular region. Cache is built on finalise."""

    def __init__(self, a, b, mode=MOSAIC, color=None, width=2):
        super().__init__(color or QColor("#888"), width)
        self.kind = mode
        self.a = QPointF(a)
        self.b = QPointF(b)
        self._cache: QPixmap | None = None

    def set_end(self, b):
        self.b = QPointF(b)

    def rect(self) -> QRectF:
        a, b = _normalised(self.a, self.b)
        return QRectF(a, b)

    def boundingRect(self) -> QRectF:
        return self.rect()

    def build(self, source: QPixmap, target: QRect | None = None) -> None:
        """target: rect in *source* coordinates (physical canvas).

        Works directly on QPixmap (no QImage round-trip: converting a large
        region is a deep copy + format conversion and was the main lag).
        Both effects are a fast box-ish downsample followed by one upscale;
        only the blur's upscale pays for smooth filtering."""
        r = (target if target is not None else self.rect().toRect())
        r = r.intersected(source.rect())
        if r.isEmpty():
            self._cache = QPixmap()
            return
        sub = source.copy(r)
        if self.kind == BLUR:
            factor = 14
            small = sub.scaled(max(1, r.width() // factor),
                               max(1, r.height() // factor),
                               Qt.IgnoreAspectRatio, Qt.FastTransformation)
            out = small.scaled(r.width(), r.height(), Qt.IgnoreAspectRatio,
                               Qt.SmoothTransformation)
        else:
            block = 8
            small = sub.scaled(max(1, r.width() // block),
                               max(1, r.height() // block),
                               Qt.IgnoreAspectRatio, Qt.FastTransformation)
            out = small.scaled(r.width(), r.height(), Qt.IgnoreAspectRatio,
                               Qt.FastTransformation)
        self._cache = out

    def paint(self, painter):
        if self._cache is not None and not self._cache.isNull():
            r = self.rect()
            painter.drawPixmap(r, self._cache, QRectF(self._cache.rect()))

    def outline_path(self):
        path = QPainterPath()
        path.addRect(self.rect())
        return path
