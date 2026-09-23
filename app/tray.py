"""System tray icon and menu."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import config, icons


class TrayIcon(QSystemTrayIcon):
    def __init__(self, controller):
        super().__init__(icons.tray_icon())
        self.controller = controller
        self.setToolTip(f"{config.APP_NAME} {config.APP_VERSION}")

        self.menu = QMenu()
        self.menu.setStyleSheet(
            "QMenu { padding:6px; } QMenu::item { padding:6px 24px;"
            "border-radius:5px; } QMenu::item:selected { background:#169fe6; }"
            "QMenu::separator { height:1px; background:#ddd; margin:5px 8px; }")

        self.act_snip = QAction(icons.icon("scissors", controller.fg_color()),
                                 "截图", self.menu)
        self.act_snip.triggered.connect(controller.start_snip)
        self.menu.addAction(self.act_snip)

        self.act_paste = QAction(icons.icon("clipboard", controller.fg_color()),
                                  "将剪贴板内容贴图", self.menu)
        self.act_paste.triggered.connect(controller.paste_from_clipboard)
        self.menu.addAction(self.act_paste)

        self.act_toggle = QAction("显示/隐藏所有贴图", self.menu)
        self.act_toggle.triggered.connect(controller.toggle_pasters)
        self.menu.addAction(self.act_toggle)

        self.act_restore = QAction("取消所有鼠标穿透", self.menu)
        self.act_restore.triggered.connect(
            controller.paster_manager.restore_click_through)
        self.menu.addAction(self.act_restore)

        self.menu.addSeparator()
        self.history_menu = self.menu.addMenu("历史截图")
        self.history_menu.aboutToShow.connect(self._build_history)
        self.menu.addSeparator()

        self.act_settings = QAction("首选项…", self.menu)
        self.act_settings.triggered.connect(controller.open_settings)
        self.menu.addAction(self.act_settings)

        self.act_about = QAction("关于", self.menu)
        self.act_about.triggered.connect(self._about)
        self.menu.addAction(self.act_about)

        self.menu.addSeparator()
        self.act_quit = QAction("退出", self.menu)
        self.act_quit.triggered.connect(controller.quit)
        self.menu.addAction(self.act_quit)

        self.setContextMenu(self.menu)
        self.activated.connect(self._activated)

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            # left click: quick snip
            self.controller.start_snip()

    def _build_history(self):
        m = self.history_menu
        m.clear()
        recent = self.controller.paster_manager.recent
        if not recent:
            empty = QAction("（暂无历史）", m)
            empty.setEnabled(False)
            m.addAction(empty)
            return
        for i, pix in enumerate(recent):
            act = QAction(QIcon(pix), f"截图 {i + 1}", m)
            act.triggered.connect(
                lambda _=False, p=pix:
                    self.controller.paster_manager.add_pixmap(p))
            m.addAction(act)
        m.addSeparator()
        clear = QAction("清空历史", m)
        clear.triggered.connect(
            lambda: self.controller.paster_manager.recent.clear())
        m.addAction(clear)

    def _about(self):
        QMessageBox.about(
            None, f"关于 {config.APP_NAME}",
            f"<h3>{config.APP_NAME} {config.APP_VERSION}</h3>"
            "<p>一款截图与贴图工具。</p>"
            "<p style='color:#888'>功能对标 Snipaste：区域截图、窗口识别、"
            "放大镜取色、标注、钉屏贴图。</p>")

    def show_welcome(self):
        if config.get_bool(config.K.TRAY_SHOW_HINT):
            return
        self.showMessage(
            config.APP_NAME,
            f"{config.APP_NAME} 已在后台运行。\n按 F1 开始截图，"
            "Ctrl+F1 将剪贴板贴图。",
            icons.tray_icon(), msecs=4000)
        config.set_value(config.K.TRAY_SHOW_HINT, True)
