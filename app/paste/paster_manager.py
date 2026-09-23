"""Owns all live pasters; creates them from pixmaps or the clipboard and
keeps a small recent-images history for re-pinning."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import QApplication

from .. import config
from .paster import Paster

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")


class PasterManager(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.pasters: list[Paster] = []
        self.recent: list[QPixmap] = []
        self._all_visible = True

    # ------------------------------------------------------------------ #
    def add_pixmap(self, pix: QPixmap, position: QPoint | None = None,
                   anchor: QPoint | None = None,
                   display_scale: float = 1.0) -> Paster | None:
        if pix is None or pix.isNull():
            return None
        paster = Paster(pixmap=pix, position=position, manager=self,
                        anchor=anchor, display_scale=display_scale)
        self._track(paster)
        paster.show()
        self.add_recent(pix)
        return paster

    def add_movie(self, path: str, position=None, anchor=None,
                  display_scale: float = 1.0) -> Paster | None:
        paster = Paster(movie_path=path, position=position, manager=self,
                        anchor=anchor, display_scale=display_scale)
        self._track(paster)
        paster.show()
        return paster

    def add_from_clipboard(self) -> Paster | None:
        """Pin clipboard image, or an image/GIF file referenced by the clipboard."""
        cb = QApplication.clipboard()
        md = cb.mimeData()
        pos = QCursor.pos()

        if md.hasUrls():
            for url in md.urls():
                local = url.toLocalFile()
                if local and local.lower().endswith(_IMAGE_SUFFIXES):
                    if local.lower().endswith(".gif"):
                        return self.add_movie(local, pos)
                    pix = QPixmap(local)
                    if not pix.isNull():
                        return self.add_pixmap(pix, pos)
        if md.hasImage():
            pix = QPixmap(cb.image())
            return self.add_pixmap(pix, pos)
        return None

    def _track(self, paster: Paster):
        self.pasters.append(paster)
        paster.closed.connect(self._on_closed)
        self.changed.emit()

    def _on_closed(self, paster):
        if paster in self.pasters:
            self.pasters.remove(paster)
        self.changed.emit()

    # ------------------------------------------------------------------ #
    def close_all(self):
        for p in list(self.pasters):
            p.close()

    def restore_click_through(self):
        for p in self.pasters:
            if p._through:
                p.set_click_through(False)

    def toggle_all_visibility(self):
        self._all_visible = not self._all_visible
        for p in self.pasters:
            p.setVisible(self._all_visible)
        return self._all_visible

    # ------------------------------------------------------------------ #
    def add_recent(self, pix: QPixmap):
        # de-duplicate identical-size images at the front
        self.recent.insert(0, pix)
        limit = config.get_int(config.K.HISTORY_LIMIT) or 10
        if len(self.recent) > limit:
            self.recent = self.recent[:limit]
