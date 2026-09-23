"""Programmatically drawn vector icons (no binary resources)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF)

_SIZE = 28


def _pen(color: QColor, width: float = 1.8) -> QPen:
    p = QPen(color)
    p.setWidthF(width)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    p.setCosmetic(True)
    return p


def _path_arrow_head(painter: QPainter, tip: QPointF, angle: float,
                     size: float, color: QColor) -> None:
    a1 = angle + math.radians(150)
    a2 = angle - math.radians(150)
    p1 = QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1))
    p2 = QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2))
    poly = QPolygonF([tip, p1, p2])
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(poly)


def _draw(name: str, p: QPainter, c: QColor) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(3.5, 3.5, _SIZE - 7, _SIZE - 7)

    if name == "rectangle":
        p.setPen(_pen(c)); p.drawRect(r)
    elif name == "filled_rect":
        p.setPen(Qt.NoPen); p.setBrush(c); p.drawRoundedRect(r, 3, 3)
    elif name == "ellipse":
        p.setPen(_pen(c)); p.drawEllipse(r)
    elif name == "arrow":
        p.setPen(_pen(c, 2.0))
        p.drawLine(QPointF(6, 22), QPointF(21, 7))
        _path_arrow_head(p, QPointF(21, 7), math.atan2(7 - 22, 21 - 6), 7, c)
    elif name == "double_arrow":
        p.setPen(_pen(c, 2.0))
        p.drawLine(QPointF(7, 21), QPointF(21, 7))
        _path_arrow_head(p, QPointF(21, 7), math.atan2(7 - 21, 21 - 7), 6, c)
        _path_arrow_head(p, QPointF(7, 21), math.atan2(21 - 7, 7 - 21), 6, c)
    elif name == "line":
        p.setPen(_pen(c, 2.0)); p.drawLine(QPointF(6, 22), QPointF(22, 6))
    elif name == "pencil":
        pen = _pen(c, 1.8)
        p.setPen(pen)
        path = QPainterPath(QPointF(7, 21)); path.lineTo(7, 17)
        path.lineTo(19, 5.5); path.lineTo(22.5, 9); path.lineTo(10.5, 20.5)
        path.lineTo(7, 21)
        p.drawPath(path)
    elif name == "marker":
        p.save()
        p.translate(14, 14); p.rotate(-45)
        p.setPen(Qt.NoPen); p.setBrush(c)
        p.drawRoundedRect(QRectF(-3.2, -10, 6.4, 13), 2, 2)
        p.setBrush(c)
        tip = QPolygonF([QPointF(-3.2, 3), QPointF(3.2, 3), QPointF(0, 9)])
        p.drawPolygon(tip)
        p.restore()
    elif name == "text":
        p.setPen(_pen(c, 2.0))
        p.drawLine(QPointF(8, 7), QPointF(20, 7))
        p.drawLine(QPointF(14, 7), QPointF(14, 21))
        p.drawLine(QPointF(10.5, 21), QPointF(17.5, 21))
    elif name in ("mosaic", "blur"):
        p.setPen(Qt.NoPen); p.setBrush(c)
        import random
        random.seed(7 if name == "mosaic" else 3)
        for row in range(4):
            for col in range(4):
                alpha = 90 + random.randint(0, 160)
                b = QColor(c); b.setAlpha(alpha)
                p.setBrush(b)
                p.drawRoundedRect(QRectF(5 + col * 4.6, 5 + row * 4.6,
                                         4.0, 4.0), 0.8, 0.8)
    elif name == "eraser":
        p.save(); p.translate(14, 14); p.rotate(-45)
        p.setPen(_pen(c)); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-4.5, -9, 9, 14), 2, 2)
        p.drawLine(QPointF(-4.5, 2), QPointF(4.5, 2))
        p.restore()
    elif name == "undo":
        p.setPen(_pen(c, 2.0))
        path = QPainterPath(QPointF(9, 12))
        path.lineTo(6, 9); path.lineTo(10, 6)
        p.drawPath(path)
        p.drawArc(QRectF(8, 5, 13, 13), 90 * 16, 200 * 16)
    elif name == "redo":
        p.setPen(_pen(c, 2.0))
        path = QPainterPath(QPointF(19, 12))
        path.lineTo(22, 9); path.lineTo(18, 6)
        p.drawPath(path)
        p.drawArc(QRectF(3, 5, 13, 13), -10 * 16, 200 * 16)
    elif name == "pin":
        p.setPen(_pen(c, 1.8)); p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(14, 4))
        path.lineTo(20, 10); path.lineTo(17, 12.5)
        path.lineTo(17, 18); path.lineTo(14, 17)
        path.lineTo(11, 18); path.lineTo(11, 12.5)
        path.lineTo(8, 10); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(14, 17), QPointF(14, 23))
    elif name == "save":
        p.setPen(_pen(c)); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(6, 5, 16, 18), 2, 2)
        p.drawRect(QRectF(10, 5, 8, 6))
        p.drawRect(QRectF(9, 15, 10, 8))
    elif name == "copy":
        p.setPen(_pen(c)); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(9, 9, 11, 11), 2, 2)
        p.drawRect(QRectF(6, 6, 11, 11))
    elif name == "close":
        p.setPen(_pen(c, 2.2))
        p.drawLine(QPointF(7, 7), QPointF(21, 21))
        p.drawLine(QPointF(21, 7), QPointF(7, 21))
    elif name == "eyedropper":
        p.setPen(_pen(c, 1.9))
        path = QPainterPath(QPointF(15, 6))
        path.lineTo(20, 11); path.lineTo(11, 20)
        path.lineTo(7, 21); path.lineTo(8, 17); path.lineTo(15, 6)
        p.drawPath(path)
        p.drawLine(QPointF(13, 8), QPointF(18, 13))
    elif name == "check":
        p.setPen(_pen(c, 2.4))
        p.drawLine(QPointF(6, 14), QPointF(11, 19))
        p.drawLine(QPointF(11, 19), QPointF(22, 7))
    elif name == "scissors":
        p.setPen(_pen(c, 1.9))
        p.drawEllipse(QPointF(9, 17), 3.2, 3.2)
        p.drawEllipse(QPointF(19, 17), 3.2, 3.2)
        p.drawLine(QPointF(11.5, 14.8), QPointF(20, 6))
        p.drawLine(QPointF(16.5, 14.8), QPointF(8, 6))
    elif name == "clipboard":
        p.setPen(_pen(c)); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(7, 6, 14, 17), 2, 2)
        p.drawRoundedRect(QRectF(10.5, 4, 7, 4), 1.2, 1.2)
    elif name == "number":
        # circled "1" (① style) — the sequence-marker glyph
        p.setPen(_pen(c, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(4, 4, 20, 20))
        f = p.font()
        f.setBold(True)
        f.setPixelSize(15)
        p.setFont(f)
        p.setPen(c)
        p.drawText(QRectF(0, 0, _SIZE, _SIZE), Qt.AlignCenter, "1")
    else:
        p.setPen(_pen(c)); p.drawRect(r)


def pixmap(name: str, color=QColor(255, 255, 255), size: int = _SIZE) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    _draw(name, p, QColor(color))
    p.end()
    return pm


def icon(name: str, color=QColor(255, 255, 255)) -> QIcon:
    return QIcon(pixmap(name, color))


def tray_pixmap(size: int = 64) -> QPixmap:
    """App/tray logo: rounded blue tile with a white scissors glyph."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#39b6ff"))
    grad.setColorAt(1, QColor("#0f7fd6"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), size * 0.22,
                      size * 0.22)
    # scale the scissors drawing into the tile
    p.setBrush(Qt.NoBrush)
    white = QColor("white")
    pen = QPen(white)
    pen.setWidthF(size * 0.055)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    cx, cy, rr = size * 0.30, size * 0.62, size * 0.10
    p.drawEllipse(QPointF(cx, cy), rr, rr)
    cx2 = size * 0.66
    p.drawEllipse(QPointF(cx2, cy), rr, rr)
    p.drawLine(QPointF(size * 0.36, size * 0.55),
               QPointF(size * 0.68, size * 0.22))
    p.drawLine(QPointF(size * 0.60, size * 0.55),
               QPointF(size * 0.26, size * 0.22))
    p.end()
    return pm


def tray_icon() -> QIcon:
    return QIcon(tray_pixmap(64))


def number_pixmap(n: int, color=QColor(255, 255, 255), size: int = _SIZE):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(_pen(color))
    p.setBrush(QColor(color.red(), color.green(), color.blue(), 40))
    p.drawEllipse(QRectF(3.5, 3.5, size - 7, size - 7))
    f = p.font()
    f.setBold(True)
    f.setPixelSize(int(size * 0.6))
    p.setFont(f)
    p.setPen(color)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, str(n))
    p.end()
    return pm
