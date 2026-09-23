"""Full-screen snipping overlay: region picking, smart window detection,
magnifier, annotation tools and output (copy / save / pin)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPainterPathStroker, QPen, QPixmap,
                           QRegion)
from PySide6.QtWidgets import QFileDialog, QWidget

from .. import config, win32
from . import magnifier as magnifier_mod
from . import shapes as S
from .capture import Capture
from .text_editor import TextEditor
from .toolbar import SnippetToolbar

_PHASE_IDLE = "idle"
_PHASE_SELECTING = "selecting"
_PHASE_SELECTED = "selected"

_DIGIT_TOOL = {
    Qt.Key_1: S.RECT, Qt.Key_2: S.ELLIPSE, Qt.Key_3: S.ARROW,
    Qt.Key_4: S.LINE, Qt.Key_5: S.PENCIL, Qt.Key_6: S.MARKER,
    Qt.Key_7: S.TEXT, Qt.Key_8: S.MOSAIC, Qt.Key_9: S.NUMBER,
    Qt.Key_0: S.ERASER,
}

_TWO_POINT = {
    S.RECT: S.RectShape, S.ELLIPSE: S.EllipseShape,
    S.ARROW: S.ArrowShape, S.LINE: S.LineShape,
}

_HANDLE_CURSORS = {
    "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
}


class Snipper(QWidget):
    closed = Signal()

    def __init__(self, capture: Capture, pin_callback, parent=None):
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.capture = capture
        self.source = capture.image          # native-resolution canvas
        self.src_image = self.source.toImage()
        self._pin_callback = pin_callback

        # widget spans the virtual desktop in LOGICAL pixels
        self.setGeometry(QRect(capture.origin, capture.logical_size))

        # state
        self.phase = _PHASE_IDLE
        self.tool = ""
        self.sel = QRect()
        self.start = QPoint()
        self.hover_rect: QRect | None = None
        self._hover_hwnd = 0
        self._chain: list[int] = []
        self._chain_idx = 0
        self._drag_mode = ""           # move | <handle>
        self._drag_anchor = QPoint()
        self._active: S.Shape | None = None
        self._erasing = False
        self._eraser_path = QPainterPath()
        self._last_erase_point = QPointF()
        self._removed_any = False
        self._editing = False
        self._editor: TextEditor | None = None
        self.number_counter = 0

        # annotations + undo
        self.shapes: list[S.Shape] = []
        self._hist: list[list[S.Shape]] = [[]]
        self._hist_idx = 0

        # toolbar (child, hidden until selection)
        self.toolbar = SnippetToolbar(
            self, config.get_color(config.K.PEN_COLOR),
            config.get_int(config.K.PEN_WIDTH))
        self.toolbar.hide()
        self.toolbar.toolChosen.connect(self.set_tool)
        self.toolbar.undoRequested.connect(self.undo)
        self.toolbar.redoRequested.connect(self.redo)
        self.toolbar.pinRequested.connect(self.do_pin)
        self.toolbar.saveRequested.connect(self.do_save)
        self.toolbar.copyRequested.connect(self.do_copy)
        self.toolbar.closeRequested.connect(self.cancel)
        self.toolbar.colorChosen.connect(self._set_color)
        self.toolbar.widthChanged.connect(self._set_width)
        self._pen_color = config.get_color(config.K.PEN_COLOR)
        self._pen_width = config.get_int(config.K.PEN_WIDTH)

        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start_snip(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        # pre-detect under the physical cursor
        gp = QCursor.pos()
        local = gp - self.capture.origin
        if self.rect().contains(local):
            self._update_hover(local)
            self.update()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    # output actions
    # ------------------------------------------------------------------ #
    def render_result(self) -> QPixmap:
        """Crop the selection at NATIVE resolution; shapes are re-rendered
        vector-crisp at the same scale."""
        phys = self.capture.physical_rect_for(self.sel)
        out = QPixmap(max(1, phys.width()), max(1, phys.height()))
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPixmap(QRectF(out.rect()), self.source, QRectF(phys))
        sx = phys.width() / max(1.0, float(self.sel.width()))
        sy = phys.height() / max(1.0, float(self.sel.height()))
        p.scale(sx, sy)
        p.translate(-self.sel.topLeft())
        for shape in self.shapes:
            p.save()
            shape.paint(p)
            p.restore()
        p.end()
        return out

    def do_copy(self):
        if self.phase != _PHASE_SELECTED or self.sel.isEmpty():
            return
        QApplication_set_clipboard(self.render_result())
        self.close()

    def do_pin(self):
        if self.phase != _PHASE_SELECTED or self.sel.isEmpty():
            return
        pix = self.render_result()
        global_top = self.capture.origin + self.sel.topLeft()
        scale = self.capture.scale_at(self.sel.center())
        self._pin_callback(pix, global_top, scale)
        self.close()

    def do_save(self):
        if self.phase != _PHASE_SELECTED or self.sel.isEmpty():
            return
        directory = config.get(config.K.QUICK_SAVE_DIR) or ""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存截图", directory,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;位图 (*.bmp)")
        if not path:
            return
        pix = self.render_result()
        if not pix.save(path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "保存失败", f"无法写入：\n{path}")
        else:
            config.set_value(config.K.QUICK_SAVE_DIR,
                             path.rsplit("/", 1)[0] if "/" in path else "")

    def cancel(self):
        self.close()

    # ------------------------------------------------------------------ #
    # painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        p = QPainter(self)
        # crisp vector annotations (lines/ellipses/arrows are jagged without it)
        p.setRenderHint(QPainter.Antialiasing, True)
        # canvas is native-resolution; scale down for display only
        p.drawPixmap(QRectF(self.rect()), self.source,
                     QRectF(self.source.rect()))

        focus = self._focus_rect()

        # dim everything outside the focus region
        mask = QColor(config.get_color(config.K.MASK_COLOR))
        mask.setAlpha(config.get_int(config.K.MASK_ALPHA))
        if focus is not None and focus.isValid():
            clear = QRegion(focus)
            dimmed = QRegion(self.rect()).subtracted(clear)
            p.setClipRegion(dimmed)
            p.fillRect(self.rect(), mask)
            p.setClipping(False)
        else:
            p.fillRect(self.rect(), mask)

        # annotations, clipped to the selection
        clip = self.sel if self.phase == _PHASE_SELECTED else (
            focus if focus else QRect())
        if clip and clip.isValid():
            p.setClipRect(clip)
            for shape in self.shapes:
                # save/restore: shapes mutate pen/brush (e.g. the arrow head
                # leaves a filled brush) and must not leak state onto others
                p.save()
                shape.paint(p)
                p.restore()
            if self._active is not None:
                p.save()
                self._active.paint(p)
                p.restore()
            p.setClipping(False)

        # eraser trail feedback
        if self._erasing:
            pen = QPen(QColor(255, 255, 255, 70))
            pen.setWidth(self._eraser_width())
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawPath(self._eraser_path)

        # focus border
        if focus is not None and focus.isValid() and focus.width() > 1:
            border = config.get_color(config.K.BORDER_COLOR)
            p.setPen(QPen(border, 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawRect(focus.adjusted(0, 0, -1, -1))

        # size tag (only while dragging a region or after it is finalised)
        if (config.get_bool(config.K.SHOW_SIZE)
                and self.phase in (_PHASE_SELECTING, _PHASE_SELECTED)
                and focus and focus.isValid() and focus.width() > 4):
            self._draw_size_tag(p, focus)

        # magnifier (samples the native-resolution canvas)
        if self._show_louvre():
            mp = self._louvre_pos(self._last_mouse)
            center_px = self.capture.to_physical(QPoint(self._last_mouse))
            magnifier_mod.draw_magnifier(
                p, mp, QPointF(center_px), self.source,
                self.src_image, self.capture.physical_origin,
                config.get_int(config.K.MAGNIFIER_ZOOM),
                config.get_bool(config.K.SHOW_PIXEL_GRID))
        p.end()

    def _focus_rect(self) -> QRect | None:
        if self.phase == _PHASE_IDLE:
            return self.hover_rect
        return self.sel if not self.sel.isEmpty() else None

    def _draw_size_tag(self, painter: QPainter, rect: QRect):
        # report real pixel size (physical), as Snipaste does
        sc = self.capture.scale_at(rect.center())
        text = f"{round(rect.width() * sc)} x {round(rect.height() * sc)}"
        f = painter.font()
        f.setPixelSize(12)
        painter.setFont(f)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(text) + 12
        th = fm.height() + 6
        x = rect.right() - tw
        y = rect.bottom() + 3
        if y + th > self.height():
            y = rect.top() - th - 3
        tag = QRect(x, y, tw, th)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 22, 26, 225))
        painter.drawRoundedRect(tag, 3, 3)
        painter.setPen(QColor(235, 235, 235))
        painter.drawText(tag, Qt.AlignCenter, text)

    # ------------------------------------------------------------------ #
    # mouse handling
    # ------------------------------------------------------------------ #
    _last_mouse = QPoint()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._editing:
            # commit/close any open text editor first; never stay stuck
            self._close_editor()
        pos = e.pos()
        self._last_mouse = QPoint(pos)

        if self.phase == _PHASE_IDLE:
            self._begin_drag_select(pos)
            return

        if self.phase == _PHASE_SELECTING:
            return

        # phase selected
        if self.tool == "":
            handle = self._hit_handle(pos)
            if handle:
                self._drag_mode = handle
                self._drag_anchor = QPoint(pos)
            elif self.sel.contains(pos):
                self._drag_mode = "move"
                self._drag_anchor = QPoint(pos)
            else:
                # start a brand new selection elsewhere
                self._restart(pos)
            return

        self._begin_tool_shape(pos)

    def mouseMoveEvent(self, e):
        pos = e.pos()
        self._last_mouse = QPoint(pos)

        if self.phase == _PHASE_IDLE:
            self._update_hover(pos)
        elif self.phase == _PHASE_SELECTING:
            self.sel = QRect(self.start, pos).normalized()
        elif self.phase == _PHASE_SELECTED:
            if self._drag_mode:
                self._apply_drag(pos)
            elif self._active is not None:
                self._update_tool_shape(pos)
            elif self._erasing:
                self._erase_to(pos)
            elif self.tool == "":
                self._update_cursor(pos)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.phase == _PHASE_SELECTING:
            self._finalise_selection(e.pos())
        elif self._active is not None:
            self._finish_tool_shape()
        elif self._erasing:
            self._erasing = False
            if self._removed_any:
                self._snapshot()
            self._removed_any = False
        self._drag_mode = ""

    def mouseDoubleClickEvent(self, e):
        if (self.phase == _PHASE_SELECTED and self.tool == ""
                and self.sel.contains(e.pos())):
            self.do_copy()

    # -- selection mechanics -------------------------------------------------
    def _begin_drag_select(self, pos):
        self.phase = _PHASE_SELECTING
        self.start = QPoint(pos)
        self.sel = QRect(pos, pos)
        self.toolbar.hide()

    def _restart(self, pos):
        self.shapes = []
        self._hist = [[]]
        self._hist_idx = 0
        self.number_counter = 0
        self.set_tool("")
        self._begin_drag_select(pos)

    def _finalise_selection(self, pos):
        moved = (pos - self.start).manhattanLength()
        if moved < 4:
            # a click without a drag -> accept detected window, else stay idle
            if self.hover_rect and not self.hover_rect.isEmpty():
                self.sel = QRect(self.hover_rect)
            else:
                self.phase = _PHASE_IDLE
                self.sel = QRect()
                self.update()
                return
        self.sel = self.sel.intersected(self.rect())
        if self.sel.width() < 2 or self.sel.height() < 2:
            self.phase = _PHASE_IDLE
            self.sel = QRect()
            self.update()
            return
        self._enter_selected()

    def _enter_selected(self):
        self.phase = _PHASE_SELECTED
        self._snapshot()
        self.setCursor(Qt.ArrowCursor)
        self._position_toolbar()
        self.toolbar.show()
        self.toolbar.raise_()

    # -- moving / resizing selection ----------------------------------------
    def _hit_handle(self, pos, margin=7) -> str:
        r = self.sel
        if QRect(r.left() - margin, r.top() - margin,
                 r.width() + 2 * margin, r.height() + 2 * margin).contains(pos):
            h = ("w" if abs(pos.x() - r.left()) <= margin else
                 "e" if abs(pos.x() - r.right()) <= margin else "")
            v = ("n" if abs(pos.y() - r.top()) <= margin else
                 "s" if abs(pos.y() - r.bottom()) <= margin else "")
            return v + h
        return ""

    def _apply_drag(self, pos):
        delta = pos - self._drag_anchor
        self._drag_anchor = QPoint(pos)
        if self._drag_mode == "move":
            self.sel.translate(delta)
        else:
            r = QRect(self.sel)
            if "n" in self._drag_mode:
                r.setTop(r.top() + delta.y())
            if "s" in self._drag_mode:
                r.setBottom(r.bottom() + delta.y())
            if "w" in self._drag_mode:
                r.setLeft(r.left() + delta.x())
            if "e" in self._drag_mode:
                r.setRight(r.right() + delta.x())
            if r.width() >= 4 and r.height() >= 4:
                self.sel = r
        self._position_toolbar()

    def _update_cursor(self, pos):
        handle = self._hit_handle(pos)
        if handle in _HANDLE_CURSORS:
            self.setCursor(_HANDLE_CURSORS[handle])
        elif self.sel.contains(pos):
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------ #
    # annotation tools
    # ------------------------------------------------------------------ #
    def set_tool(self, name: str):
        self.tool = name
        if name == "":
            self.setCursor(Qt.ArrowCursor if self.phase == _PHASE_SELECTED
                           else Qt.CrossCursor)
        else:
            self.setCursor(Qt.CrossCursor)
        self.toolbar.select_tool(name)
        if name == "text":
            # text starts on the next left click inside the selection
            pass

    def _begin_tool_shape(self, pos):
        tool = self.tool
        if tool == S.TEXT:
            self._open_text_editor(pos)
            return
        if tool == S.NUMBER:
            self.number_counter += 1
            shape = S.NumberShape(pos, self.number_counter,
                                  self._pen_color, self._pen_width)
            self.shapes.append(shape)
            self._snapshot()
            return
        if tool == S.ERASER:
            self._erasing = True
            self._removed_any = False
            self._eraser_path = QPainterPath(QPointF(pos))
            self._last_erase_point = QPointF(pos)
            self._erase_segment(QPointF(pos), QPointF(pos))
            return
        if tool in _TWO_POINT:
            cls = _TWO_POINT[tool]
            self._active = cls(pos, pos, self._pen_color, self._pen_width)
        elif tool in (S.PENCIL, S.MARKER):
            self._active = S.PathShape(pos, self._pen_color, self._pen_width,
                                       tool)
        elif tool in (S.MOSAIC, S.BLUR):
            self._active = S.MosaicShape(pos, pos, tool)

    def _update_tool_shape(self, pos):
        active = self._active
        shift = win32.is_key_pressed(0x10)
        if isinstance(active, S._TwoPoint):
            end = QPointF(pos)
            if shift:
                end = QPointF(self._constrain(active.kind, active.a, end))
            active.set_end(end)
        elif isinstance(active, S.PathShape):
            active.add_point(pos)
        elif isinstance(active, S.MosaicShape):
            active.set_end(pos)

    def _constrain(self, kind, start: QPointF, end: QPointF) -> QPoint:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        if kind in (S.ARROW, S.LINE):
            angle = math.atan2(dy, dx)
            step = math.pi / 4
            a = round(angle / step) * step
            length = math.hypot(dx, dy)
            return QPoint(int(start.x() + length * math.cos(a)),
                          int(start.y() + length * math.sin(a)))
        # rect / ellipse -> square / circle
        side = max(abs(int(dx)), abs(int(dy)))
        return QPoint(int(start.x()) + side * (1 if dx >= 0 else -1),
                      int(start.y()) + side * (1 if dy >= 0 else -1))

    def _finish_tool_shape(self):
        active = self._active
        if isinstance(active, S.MosaicShape):
            active.build(self.source,
                         self.capture.physical_rect_for(
                             active.rect().toRect()))
        # discard accidental zero-size shapes
        br = active.boundingRect()
        if br.width() > 1 or br.height() > 1:
            self.shapes.append(active)
            self._snapshot()
        self._active = None

    # -- text ----------------------------------------------------------------
    def _open_text_editor(self, pos):
        if not self.sel.contains(pos):
            return
        self.activateWindow()
        max_width = self.sel.right() - pos.x()
        editor = TextEditor(self, QPointF(pos), self._pen_color,
                            self._pen_width, max_width)
        editor.accepted.connect(self._text_accepted)
        editor.rejected.connect(self._text_rejected)
        self._editor = editor
        self._editing = True
        # belt & braces: grab focus once the event loop settles
        QTimer.singleShot(0, editor.setFocus)

    def _text_accepted(self, text):
        editor = self._editor
        if editor is not None and text:
            shape = S.TextShape(editor.final_pos(), text,
                                self._pen_color, self._pen_width)
            self.shapes.append(shape)
            self._snapshot()
        self._close_editor()

    def _text_rejected(self):
        self._close_editor()

    def _close_editor(self):
        if self._editor is not None:
            self._editor.deleteLater()
            self._editor = None
        self._editing = False
        self.activateWindow()
        self.setFocus()

    # -- eraser --------------------------------------------------------------
    def _eraser_width(self) -> int:
        return max(16, self._pen_width * 4)

    def _erase_segment(self, a: QPointF, b: QPointF):
        """Erase shapes touched by the segment a->b (eraser-width stroked)."""
        path = QPainterPath(a)
        if b != a:
            path.lineTo(b)
        stroker = QPainterPathStroker()
        stroker.setWidth(self._eraser_width())
        stroker.setCapStyle(Qt.RoundCap)
        self._erase_by(stroker.createStroke(path))

    def _erase_to(self, pos):
        here = QPointF(pos)
        self._eraser_path.lineTo(here)
        self._erase_segment(self._last_erase_point, here)
        self._last_erase_point = here

    def _erase_by(self, hit_region: QPainterPath):
        kept = []
        for shape in self.shapes:
            try:
                intersects = hit_region.intersects(shape.outline_path())
            except Exception:
                intersects = False
            if not intersects:
                kept.append(shape)
        if len(kept) != len(self.shapes):
            self.shapes = kept
            self._removed_any = True

    # ------------------------------------------------------------------ #
    # smart window detection
    # ------------------------------------------------------------------ #
    def _update_hover(self, local_pos: QPoint):
        global_pt = self.capture.origin + local_pos
        hwnd = win32.top_level_at_global_logical(global_pt, int(self.winId()))
        if hwnd:
            hwnd = win32.deepest_in(hwnd, global_pt)
        self._hover_hwnd = hwnd
        if hwnd:
            r = win32.window_rect_logical(hwnd)
            self.hover_rect = r.translated(-self.capture.origin).intersected(
                self.rect())
            self._chain = win32.hwnd_chain(hwnd)
            self._chain_idx = 0
        else:
            self.hover_rect = None
            self._chain = []

    def _cycle_window(self, step: int):
        if not self._chain:
            gp = self.capture.origin + self._last_mouse
            hwnd = win32.top_level_at_global_logical(gp, int(self.winId()))
            if hwnd:
                self._chain = win32.hwnd_chain(hwnd)
                self._chain_idx = 0
        if not self._chain:
            return
        self._chain_idx = (self._chain_idx + step) % len(self._chain)
        hwnd = self._chain[self._chain_idx]
        r = win32.window_rect_logical(hwnd)
        self.hover_rect = r.translated(-self.capture.origin).intersected(
            self.rect())
        self.update()

    # ------------------------------------------------------------------ #
    # toolbar placement / magnifier
    # ------------------------------------------------------------------ #
    def _position_toolbar(self):
        tb = self.toolbar
        tb.adjustSize()
        th = tb.sizeHint().height()
        tw = tb.sizeHint().width()
        x = self.sel.center().x() - tw // 2
        x = max(2, min(self.width() - tw - 2, x))
        y = self.sel.bottom() + 7
        if y + th > self.height() - 2:
            y = self.sel.top() - th - 7
        y = max(2, y)
        tb.move(int(x), int(y))

    def _show_louvre(self) -> bool:
        if not config.get_bool(config.K.MAGNIFIER):
            return False
        if self.phase in (_PHASE_IDLE, _PHASE_SELECTING):
            return True
        if self.phase == _PHASE_SELECTED and self.tool == "" and \
                not self._drag_mode:
            return not self.sel.contains(self._last_mouse)
        return False

    def _louvre_pos(self, mouse: QPoint) -> QPoint:
        ps = magnifier_mod.panel_size().size()
        w, h = ps.width(), ps.height()
        x = mouse.x() + 22
        if x + w > self.width() - 2:
            x = mouse.x() - w - 22
        y = mouse.y() + 22
        if y + h > self.height() - 2:
            y = mouse.y() - h - 22
        return QPoint(max(2, x), max(2, y))

    # ------------------------------------------------------------------ #
    # undo / redo
    # ------------------------------------------------------------------ #
    def _snapshot(self):
        self._hist = self._hist[:self._hist_idx + 1]
        self._hist.append(list(self.shapes))
        self._hist_idx = len(self._hist) - 1
        self.toolbar.set_history_enabled(self._hist_idx > 0,
                                         self._hist_idx < len(self._hist) - 1)

    def undo(self):
        if self._hist_idx > 0:
            self._hist_idx -= 1
            self.shapes = list(self._hist[self._hist_idx])
            self.toolbar.set_history_enabled(
                False, True)
            self.toolbar.set_history_enabled(
                self._hist_idx > 0, self._hist_idx < len(self._hist) - 1)
            self.update()

    def redo(self):
        if self._hist_idx < len(self._hist) - 1:
            self._hist_idx += 1
            self.shapes = list(self._hist[self._hist_idx])
            self.toolbar.set_history_enabled(
                self._hist_idx > 0, self._hist_idx < len(self._hist) - 1)
            self.update()

    # ------------------------------------------------------------------ #
    # keyboard
    # ------------------------------------------------------------------ #
    def keyPressEvent(self, e):
        key = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)

        if key == Qt.Key_Escape:
            self.cancel()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and not shift:
            self.do_copy()
            return
        if key == Qt.Key_Tab:
            if self.phase == _PHASE_IDLE:
                self._cycle_window(-1 if shift else 1)
            return

        if self.phase != _PHASE_SELECTED:
            super().keyPressEvent(e)
            return

        if ctrl:
            mapping = {
                Qt.Key_C: self.do_copy, Qt.Key_S: self.do_save,
                Qt.Key_D: self.do_pin, Qt.Key_Z: self.undo,
                Qt.Key_Y: self.redo,
            }
            if key in mapping:
                mapping[key]()
                return
            if key == Qt.Key_A:
                self._select_current_monitor()
                return

        if key in _DIGIT_TOOL and not ctrl:
            self.set_tool(_DIGIT_TOOL[key])
            return
        if key == Qt.Key_B and not ctrl:
            self.set_tool(S.BLUR)
            return
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) \
                and self.tool == "":
            step = 10 if shift else 1
            dx = {Qt.Key_Left: -step, Qt.Key_Right: step}.get(key, 0)
            dy = {Qt.Key_Up: -step, Qt.Key_Down: step}.get(key, 0)
            self.sel.translate(dx, dy)
            self._position_toolbar()
            self.update()
            return
        super().keyPressEvent(e)

    def _select_current_monitor(self):
        from PySide6.QtGui import QGuiApplication
        global_pt = self.capture.origin + self._last_mouse
        screen = QGuiApplication.screenAt(global_pt) or \
            QGuiApplication.primaryScreen()
        geo = screen.geometry().translated(-self.capture.origin)
        self.sel = geo.intersected(self.rect())
        self.shapes = []
        self._hist = [[]]
        self._hist_idx = 0
        self.set_tool("")
        self._enter_selected()

    def _set_color(self, color: QColor):
        self._pen_color = QColor(color)
        config.set_value(config.K.PEN_COLOR, color.name())

    def _set_width(self, width: int):
        self._pen_width = int(width)
        config.set_value(config.K.PEN_WIDTH, int(width))


def QApplication_set_clipboard(pix: QPixmap):
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setPixmap(pix)
