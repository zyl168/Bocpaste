"""Magnifier louvre overlay: zoomed pixels, grid, coordinates and RGB."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

PANEL_W = 168
PANEL_H = 168
INFO_H = 26


def panel_size() -> QRect:
    return QRect(0, 0, PANEL_W, PANEL_H + INFO_H)


def color_at(image: QImage, pos: QPointF) -> QColor:
    x, y = int(round(pos.x())), int(round(pos.y()))
    if image.rect().contains(x, y):
        return image.pixelColor(x, y)
    return QColor(0, 0, 0)


def draw_magnifier(painter: QPainter, top_left: QPoint, center: QPointF,
                   source: QPixmap, image: QImage, global_origin: QPoint,
                   zoom: int, show_grid: bool) -> None:
    painter.save()
    painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
    panel = QRect(top_left, QPoint(top_left.x() + PANEL_W,
                                   top_left.y() + PANEL_H + INFO_H))
    view = QRect(top_left, QPoint(top_left.x() + PANEL_W,
                                  top_left.y() + PANEL_H))

    painter.setClipRect(panel)
    # zoomed source, centred on the integer pixel under the cursor
    half_w = PANEL_W / (2 * zoom)
    half_h = PANEL_H / (2 * zoom)
    src = QRectF(center.x() + 0.5 - half_w, center.y() + 0.5 - half_h,
                 PANEL_W / zoom, PANEL_H / zoom)
    painter.drawPixmap(QRectF(view), source, src)

    if show_grid and zoom >= 4:
        gx = PANEL_W / 2 - zoom / 2
        gy = PANEL_H / 2 - zoom / 2
        line = QColor(255, 255, 255, 110)
        painter.setPen(line)
        x = gx
        while x < PANEL_W:
            painter.drawLine(QPoint(int(view.left() + x), view.top()),
                             QPoint(int(view.left() + x), view.bottom()))
            x += zoom
        y = gy
        while y < PANEL_H:
            painter.drawLine(QPoint(view.left(), int(view.top() + y)),
                             QPoint(view.right(), int(view.top() + y)))
            y += zoom

    # current pixel frame + crosshair
    cur = QRect(int(view.left() + PANEL_W / 2 - zoom / 2),
                int(view.top() + PANEL_H / 2 - zoom / 2), zoom, zoom)
    painter.setPen(QPen_safe(QColor("#ff2d2d"), 1.4))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(cur.adjusted(0, 0, -1, -1))

    painter.setClipping(False)
    painter.setPen(QColor("#169fe6"))
    painter.drawRect(panel.adjusted(0, 0, -1, -1))

    # info strip
    strip = QRect(top_left.x(), top_left.y() + PANEL_H, PANEL_W, INFO_H)
    painter.fillRect(strip, QColor(20, 22, 26, 235))
    col = color_at(image, center)
    gx_global = int(round(center.x())) + global_origin.x()
    gy_global = int(round(center.y())) + global_origin.y()
    painter.setPen(QColor(230, 230, 230))
    f = painter.font()
    f.setPixelSize(12)
    painter.setFont(f)
    painter.drawText(strip.adjusted(6, 0, 6, 0),
                     Qt.AlignLeft | Qt.AlignVCenter,
                     f"{gx_global}, {gy_global}")
    swatch = QRect(strip.right() - 78, strip.top() + 6, 14, 14)
    painter.fillRect(swatch, col)
    painter.setPen(QColor(120, 120, 120))
    painter.drawRect(swatch)
    painter.setPen(QColor(230, 230, 230))
    painter.drawText(strip.adjusted(6, 0, -6, 0),
                     Qt.AlignRight | Qt.AlignVCenter,
                     f"{col.red()},{col.green()},{col.blue()}")
    painter.restore()


def QPen_safe(color, width):
    from PySide6.QtGui import QPen
    pen = QPen(color)
    pen.setWidthF(width)
    return pen
