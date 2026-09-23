"""Screen capture. Composites every screen into one virtual-desktop pixmap.

The canvas keeps the monitors' NATIVE physical resolution (no downsampling),
while coordinates used across the app stay in Qt logical pixels; Capture
provides the logical->physical mapping for both single- and mixed-DPI setups.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap


@dataclass
class Capture:
    image: QPixmap                 # physical-resolution canvas
    origin: QPoint                 # logical virtual-desktop top-left
    logical_size: QSize
    physical_origin: QPoint        # physical desktop top-left
    monitors: list = field(default_factory=list)   # [(logical QRect, physical QRect)]

    # -- coordinate mapping --------------------------------------------------
    def _pair_for(self, logical_point: QPoint):
        for lg, ph in self.monitors:
            if lg.contains(logical_point):
                return lg, ph
        return None

    def scale_at(self, logical_point: QPoint) -> float:
        pair = self._pair_for(logical_point)
        if pair:
            lg, ph = pair
            return ph.width() / max(1, lg.width())
        screen = QGuiApplication.primaryScreen()
        return screen.devicePixelRatio() if screen else 1.0

    def to_physical(self, logical_point: QPoint) -> QPoint:
        pair = self._pair_for(logical_point)
        if pair:
            lg, ph = pair
            sx = ph.width() / max(1, lg.width())
            sy = ph.height() / max(1, lg.height())
            return QPoint(
                ph.left() + round((logical_point.x() - lg.left()) * sx),
                ph.top() + round((logical_point.y() - lg.top()) * sy))
        # fallback: uniform scale over the whole canvas
        sx = self.image.width() / max(1, self.logical_size.width())
        sy = self.image.height() / max(1, self.logical_size.height())
        return QPoint(round(logical_point.x() * sx),
                      round(logical_point.y() * sy))

    def physical_rect_for(self, logical_rect: QRect) -> QRect:
        pair = self._pair_for(logical_rect.center())
        if pair:
            lg, ph = pair
            sx = ph.width() / max(1, lg.width())
            sy = ph.height() / max(1, lg.height())
            x = ph.left() + round((logical_rect.left() - lg.left()) * sx)
            y = ph.top() + round((logical_rect.top() - lg.top()) * sy)
            w = max(1, round(logical_rect.width() * sx))
            h = max(1, round(logical_rect.height() * sy))
            return QRect(x, y, w, h).intersected(self.image.rect())
        sx = self.image.width() / max(1, self.logical_size.width())
        sy = self.image.height() / max(1, self.logical_size.height())
        return QRect(round(logical_rect.left() * sx),
                     round(logical_rect.top() * sy),
                     max(1, round(logical_rect.width() * sx)),
                     max(1, round(logical_rect.height() * sy))
                     ).intersected(self.image.rect())


def capture_virtual_desktop() -> Capture:
    """Grab all monitors at native resolution and stitch one canvas."""
    screens = QGuiApplication.screens()
    vgeo = QGuiApplication.primaryScreen().virtualGeometry()
    for s in screens:
        vgeo = vgeo.united(s.virtualGeometry())

    # physical rects per screen via Win32 (Qt only exposes logical geometry)
    pairs: list[tuple[QRect, QRect]] = []       # (logical, physical)
    try:
        from .. import win32
        by_name = {s.name(): s for s in screens}
        for m in win32._monitors():
            screen = by_name.get(m.name)
            if screen is None:
                continue
            pairs.append((screen.geometry(), m.physical))
    except Exception:
        pass
    if not pairs:
        # offscreen / fallback: derive physical rects from DPR
        for s in screens:
            dpr = s.devicePixelRatio() or 1.0
            g = s.geometry()
            ph = QRect(round(g.left() * dpr), round(g.top() * dpr),
                       round(g.width() * dpr), round(g.height() * dpr))
            pairs.append((g, ph))

    physical_origin = QPoint(min(ph.left() for _, ph in pairs),
                             min(ph.top() for _, ph in pairs))
    canvas_rect = QRect()
    for _, ph in pairs:
        moved = ph.translated(-physical_origin)
        canvas_rect = canvas_rect.united(moved)

    canvas = QPixmap(canvas_rect.size())
    canvas.fill(Qt.black)
    painter = QPainter(canvas)
    for (lg, ph) in pairs:
        grabbed = None
        for s in screens:
            if s.geometry() == lg:
                grabbed = s.grabWindow(0)
                break
        if grabbed is None or grabbed.isNull():
            continue
        target = ph.translated(-physical_origin)
        if grabbed.size() != target.size():
            grabbed = grabbed.scaled(target.size(), Qt.IgnoreAspectRatio,
                                     Qt.FastTransformation)
        painter.drawPixmap(target, grabbed, grabbed.rect())
    painter.end()

    return Capture(image=canvas, origin=vgeo.topLeft(),
                   logical_size=vgeo.size(), physical_origin=physical_origin,
                   monitors=pairs)
