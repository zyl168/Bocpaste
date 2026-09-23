"""A pinned, always-on-top image ("paster").

Supports drag-to-move with edge snapping, wheel zoom around the cursor,
Ctrl+wheel opacity, rotation / flip, mouse click-through, GIF playback,
and a full context menu.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (QAction, QColor, QCursor, QGuiApplication,
                           QMovie, QPainter, QPixmap, QTransform)
from PySide6.QtWidgets import (QApplication, QFileDialog,
                               QGraphicsDropShadowEffect, QMenu, QWidget)

from .. import config, win32

_MIN_SCALE, _MAX_SCALE = 0.1, 16.0


class Paster(QWidget):
    closed = Signal(object)

    def __init__(self, pixmap: QPixmap | None = None, movie_path: str | None = None,
                 position: QPoint | None = None, manager=None,
                 anchor: QPoint | None = None, display_scale: float = 1.0):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.manager = manager

        self._original = pixmap or QPixmap()
        self._movie: QMovie | None = None
        if movie_path:
            self._movie = QMovie(movie_path)
            self._movie.jumpToFrame(0)

        # visual transform state; display_scale maps physical image pixels to
        # logical screen units so a pinned capture keeps its on-screen size.
        # _sx/_sy allow independent axis scaling (edge-stretch resize).
        _s = 1.0 / max(0.01, float(display_scale)) if display_scale else 1.0
        self._sx = _s
        self._sy = _s
        self._display_scale = float(display_scale) if display_scale else 1.0
        self._rotation = 0          # 0/90/180/270
        self._flip_h = False
        self._flip_v = False
        self._display = self._original
        self._through = False

        # interaction
        self._dragging = False
        self._drag_anchor = QPoint()
        self._was_moved = False
        self._resizing = ""         # "" | n/s/e/w/ne/nw/se/sw
        self._rs_anchor = QPoint()
        self._rs_orig_geo = QRect()
        self._rs_orig_sx = 1.0
        self._rs_orig_sy = 1.0

        self._shadow_m = 14 if config.get_bool(config.K.PASTE_SHADOW) else 0
        if self._shadow_m:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(18)
            eff.setOffset(0, 2)
            eff.setColor(QColor(0, 0, 0, 170))
            self.setGraphicsEffect(eff)

        self.setMouseTracking(True)
        if self._movie:
            self._movie.frameChanged.connect(lambda _=0: self._refresh_frame())
        self._rebuild_display()

        # opacity is applied at paint time (0-255); native layered attributes
        # are owned by Qt for WA_TranslucentBackground and must not be touched.
        self._opacity = max(10, min(255, config.get_int(config.K.PASTE_OPACITY)))

        # place on screen: either top-left anchored or centred on position
        if position is None and anchor is None:
            position = QCursor.pos()
        self._place_initial(position, anchor)

    # ------------------------------------------------------------------ #
    # geometry / display rebuild
    # ------------------------------------------------------------------ #
    def _content_base_size(self):
        return self._display.size()

    def _rebuild_display(self):
        if self._movie is not None:
            base = self._movie.currentPixmap()
        else:
            base = self._original
        t = QTransform()
        if self._flip_h:
            t.scale(-1, 1)
        if self._flip_v:
            t.scale(1, -1)
        t.rotate(self._rotation)
        self._display = base.transformed(t, Qt.SmoothTransformation)
        self._apply_window_size()

    def _refresh_frame(self):
        # animated frame: apply the same transform
        base = self._movie.currentPixmap()
        t = QTransform()
        if self._flip_h:
            t.scale(-1, 1)
        if self._flip_v:
            t.scale(1, -1)
        t.rotate(self._rotation)
        self._display = base.transformed(t, Qt.SmoothTransformation)
        self._apply_window_size()
        self.update()

    def _apply_window_size(self):
        m = self._shadow_m
        w = max(1, int(round(self._display.width() * self._sx))) + 2 * m
        h = max(1, int(round(self._display.height() * self._sy))) + 2 * m
        # keep top-left anchored while resizing
        tl = self.pos()
        self.resize(w, h)
        if self.isVisible():
            self.move(tl)

    def _content_rect(self) -> QRect:
        m = self._shadow_m
        return self.rect().adjusted(m, m, -m, -m)

    def _place_initial(self, position: QPoint | None, anchor: QPoint | None):
        w, h = self.width(), self.height()
        ref = anchor if anchor is not None else position
        screen = QGuiApplication.screenAt(ref) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        if anchor is not None:
            x, y = int(anchor.x()), int(anchor.y())
        else:
            x = int(position.x() - w / 2)
            y = int(position.y() - h / 2)
        # keep fully on screen when possible
        x = max(avail.left() + 2, min(x, avail.right() - w - 2))
        y = max(avail.top() + 2, min(y, avail.bottom() - h - 2))
        self.move(x, y)

    # ------------------------------------------------------------------ #
    # painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        target = self._content_rect()
        p.setOpacity(self._opacity / 255.0)
        p.drawPixmap(QRectF(target), self._display,
                     QRectF(self._display.rect()))
        p.setOpacity(1.0)
        if self._through:
            # subtle frame so a click-through paster is still visible
            from PySide6.QtGui import QPen
            p.setPen(QPen(QColor("#169fe6"), 1.5))
            p.drawRect(target.adjusted(0, 0, -1, -1))
        p.end()

    # ------------------------------------------------------------------ #
    # mouse: move / edge-resize / zoom / opacity / click-through
    # ------------------------------------------------------------------ #
    _RESIZE_M = 8            # px band inside the image edge
    _MIN_CONTENT = 16        # smallest content size in px

    _ZONE_CURSORS = {
        "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
        "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
        "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
        "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    }

    def _hit_resize_zone(self, pos: QPoint) -> str:
        r = self._content_rect()
        if not QRect(r.left() - 4, r.top() - 4,
                     r.width() + 8, r.height() + 8).contains(pos):
            return ""
        west = abs(pos.x() - r.left()) <= self._RESIZE_M
        east = abs(pos.x() - r.right()) <= self._RESIZE_M
        north = abs(pos.y() - r.top()) <= self._RESIZE_M
        south = abs(pos.y() - r.bottom()) <= self._RESIZE_M
        v = "n" if north else "s" if south else ""
        h = "w" if west else "e" if east else ""
        return v + h

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.pos()
        zone = self._hit_resize_zone(pos)
        if zone:
            self._resizing = zone
            self._rs_anchor = e.globalPosition().toPoint()
            self._rs_orig_geo = self.geometry()
            self._rs_orig_sx = self._sx
            self._rs_orig_sy = self._sy
        else:
            self._dragging = True
            self._was_moved = False
            self._drag_anchor = e.globalPosition().toPoint() - self.pos()
        e.accept()

    def mouseMoveEvent(self, e):
        g = e.globalPosition().toPoint()
        if self._resizing:
            self._apply_resize(g)
        elif self._dragging:
            self.move(g - self._drag_anchor)
            self._was_moved = True
        else:
            zone = self._hit_resize_zone(e.pos())
            self.setCursor(self._ZONE_CURSORS.get(zone, Qt.ArrowCursor))

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._resizing:
            self._resizing = ""
        elif self._dragging:
            self._dragging = False
            if self._was_moved and config.get_bool(config.K.PASTE_SNAP):
                self._snap_to_edges()

    def _apply_resize(self, g: QPoint):
        """Corner zones scale proportionally; edge zones stretch one axis."""
        zone = self._resizing
        og = self._rs_orig_geo
        m = self._shadow_m
        min_w = self._MIN_CONTENT + 2 * m
        min_h = self._MIN_CONTENT + 2 * m
        dx = g.x() - self._rs_anchor.x()
        dy = g.y() - self._rs_anchor.y()
        rect = QRect(og)

        if len(zone) == 2:
            # proportional: factor from the axis with the larger relative move
            base_w = max(1, og.width() - 2 * m)
            base_h = max(1, og.height() - 2 * m)
            fx = (og.width() + dx * (1 if "e" in zone else -1)) / og.width()
            fy = (og.height() + dy * (1 if "s" in zone else -1)) / og.height()
            f = max(0.05, max(fx, fy))
            new_sx = self._rs_orig_sx * f
            new_sy = self._rs_orig_sy * f
            new_w = og.width() * f
            new_h = og.height() * f
            if "e" in zone:
                rect.setWidth(int(round(new_w)))
            else:
                rect.setLeft(int(round(og.right() - new_w)))
            if "s" in zone:
                rect.setHeight(int(round(new_h)))
            else:
                rect.setTop(int(round(og.bottom() - new_h)))
        else:
            L, R, T, B = og.left(), og.right(), og.top(), og.bottom()
            if "e" in zone:
                R = max(L + min_w - 1, R + dx)
            if "w" in zone:
                L = min(R - min_w + 1, L + dx)
            if "s" in zone:
                B = max(T + min_h - 1, B + dy)
            if "n" in zone:
                T = min(B - min_h + 1, T + dy)
            rect = QRect(QPoint(L, T), QPoint(R, B))

        # derive the new per-axis scales from the resulting content size
        disp_w = max(1, self._display.width())
        disp_h = max(1, self._display.height())
        content_w = max(self._MIN_CONTENT, rect.width() - 2 * m)
        content_h = max(self._MIN_CONTENT, rect.height() - 2 * m)
        if len(zone) == 2:
            self._sx = new_sx
            self._sy = new_sy
        else:
            self._sx = content_w / disp_w
            self._sy = content_h / disp_h
        self.setGeometry(rect)
        self.update()

    # NOTE: no double-click handler on purpose. Click-through is toggled from
    # the context menu only — a pierced window never receives mouse events,
    # so double-click would be a one-way trap with no mouse-way back.
    # Recovery paths while pierced: tray menu "取消所有鼠标穿透".

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if not delta:
            return
        step = config.get_int(config.K.PASTE_ZOOM_STEP) / 100.0
        if e.modifiers() & Qt.ControlModifier:
            alpha = self._opacity + (8 if delta > 0 else -8)
            self._apply_opacity(max(30, min(255, alpha)))
            return
        factor = (1.0 + step) if delta > 0 else (1.0 / (1.0 + step))
        self._zoom_around(self._image_point(e.position()),
                          self._sx * factor, self._sy * factor)

    def _image_point(self, local_pos: QPointF) -> QPointF:
        cr = self._content_rect()
        return QPointF((local_pos.x() - cr.left()) / self._sx,
                       (local_pos.y() - cr.top()) / self._sy)

    def _zoom_around(self, img_pt: QPointF, new_sx: float, new_sy: float | None = None):
        """Zoom to an absolute per-axis scale, keeping img_pt under the cursor."""
        if new_sy is None:
            new_sy = new_sx
        new_sx = max(_MIN_SCALE, min(_MAX_SCALE, new_sx))
        new_sy = max(_MIN_SCALE, min(_MAX_SCALE, new_sy))
        if abs(new_sx - self._sx) < 1e-6 and abs(new_sy - self._sy) < 1e-6:
            return
        mouse_global = QCursor.pos()
        self._sx, self._sy = new_sx, new_sy
        m = self._shadow_m
        # resize then move so the image point stays under the cursor
        self._apply_window_size()
        new_x = mouse_global.x() - int(round(img_pt.x() * new_sx)) - m
        new_y = mouse_global.y() - int(round(img_pt.y() * new_sy)) - m
        self.move(new_x, new_y)
        self.update()

    def _snap_to_edges(self, threshold=14):
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or \
            QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        r = self.frameGeometry()
        x, y = r.left(), r.top()
        if abs(r.left() - avail.left()) < threshold:
            x = avail.left()
        if abs(r.right() - avail.right()) < threshold:
            x = avail.right() - r.width()
        if abs(r.top() - avail.top()) < threshold:
            y = avail.top()
        if abs(r.bottom() - avail.bottom()) < threshold:
            y = avail.bottom() - r.height()
        self.move(x, y)

    # ------------------------------------------------------------------ #
    # opacity / click-through
    # ------------------------------------------------------------------ #
    def _apply_opacity(self, alpha: int):
        self._opacity = max(10, min(255, int(alpha)))
        config.set_value(config.K.PASTE_OPACITY, self._opacity)
        self.update()

    def set_click_through(self, through: bool):
        self._through = through
        win32.set_click_through(int(self.winId()), through)
        self.update()

    # ------------------------------------------------------------------ #
    # rotation / flip
    # ------------------------------------------------------------------ #
    def rotate(self, delta_deg: int):
        self._rotation = (self._rotation + delta_deg) % 360
        self._rebuild_display()

    def flip(self, horizontal: bool):
        if horizontal:
            self._flip_h = not self._flip_h
        else:
            self._flip_v = not self._flip_v
        self._rebuild_display()

    def reset_transform(self):
        _s = 1.0 / max(0.01, self._display_scale)
        self._sx = _s
        self._sy = _s
        self._rotation = 0
        self._flip_h = self._flip_v = False
        self._rebuild_display()
        self._apply_opacity(255)

    # ------------------------------------------------------------------ #
    # context menu
    # ------------------------------------------------------------------ #
    def contextMenuEvent(self, event):
        if self._through:
            return
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_QSS)

        zoom_menu = menu.addMenu("缩放")
        for pct in (25, 50, 75, 100, 125, 150, 200, 300):
            act = QAction(f"{pct}%", self)
            act.triggered.connect(
                lambda _=False, p=pct:
                    self._zoom_around(QPointF(0, 0), p / 100.0))
            zoom_menu.addAction(act)

        op_menu = menu.addMenu("不透明度")
        for pct in (100, 90, 80, 70, 50, 30):
            act = QAction(f"{pct}%", self)
            act.triggered.connect(
                lambda _=False, a=pct * 2.55: self._apply_opacity(int(a)))
            op_menu.addAction(act)

        menu.addSeparator()
        act = QAction("向左旋转", self)
        act.triggered.connect(lambda: self.rotate(-90))
        menu.addAction(act)
        act = QAction("向右旋转", self)
        act.triggered.connect(lambda: self.rotate(90))
        menu.addAction(act)
        act = QAction("水平翻转", self)
        act.triggered.connect(lambda: self.flip(True))
        menu.addAction(act)
        act = QAction("垂直翻转", self)
        act.triggered.connect(lambda: self.flip(False))
        menu.addAction(act)

        if self._movie is not None:
            menu.addSeparator()
            act = QAction("暂停/播放", self)
            act.triggered.connect(self._toggle_play)
            menu.addAction(act)

        menu.addSeparator()
        act = QAction(("取消鼠标穿透" if self._through else "鼠标穿透"), self)
        act.triggered.connect(lambda: self.set_click_through(not self._through))
        menu.addAction(act)

        menu.addSeparator()
        act = QAction("复制", self)
        act.triggered.connect(self.copy_image)
        menu.addAction(act)
        act = QAction("保存…", self)
        act.triggered.connect(self.save_image)
        menu.addAction(act)
        act = QAction("重置", self)
        act.triggered.connect(self.reset_transform)
        menu.addAction(act)

        menu.addSeparator()
        act = QAction("关闭", self)
        act.triggered.connect(self.close)
        menu.addAction(act)
        if self.manager is not None:
            act = QAction("关闭所有贴图", self)
            act.triggered.connect(self.manager.close_all)
            menu.addAction(act)

        menu.exec(event.globalPos())

    def _toggle_play(self):
        if self._movie is None:
            return
        if self._movie.state() == QMovie.Running:
            self._movie.setPaused(True)
        else:
            self._movie.setPaused(False)
            self._movie.start()

    def copy_image(self):
        QApplication.clipboard().setPixmap(self._display)

    def save_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存贴图", "", "PNG 图片 (*.png);;JPEG 图片 (*.jpg)")
        if path:
            self._display.save(path)

    # ------------------------------------------------------------------ #
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and config.get_bool(config.K.PASTE_ESC_CLOSES):
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if self._movie is not None:
            self._movie.stop()
        self.closed.emit(self)
        super().closeEvent(e)


_MENU_QSS = """
QMenu { background:#2c2f35; color:#e6e6e6; border:1px solid #3a3e44;
        border-radius:6px; padding:6px; }
QMenu::item { padding:6px 22px; border-radius:4px; }
QMenu::item:selected { background:#169fe6; }
QMenu::separator { height:1px; background:#3a3e44; margin:5px 8px; }
"""
