"""Win32 API wrappers (ctypes) used across the app.

Covers DPI aware coordinate conversion, window/control detection for smart
snapping, mouse-transparency for pasters and a few small helpers.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
shcore = ctypes.windll.shcore

# --- constants -------------------------------------------------------------
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105

DWMWA_EXTENDED_FRAME_BOUNDS = 9

GA_ROOT = 2
GA_ROOTOWNER = 3

CWP_SKIPINVISIBLE = 0x0001

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_HIDE, SW_SHOW = 0, 5

# --- structs / signatures --------------------------------------------------
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]

user32.RealChildWindowFromPoint.restype = wintypes.HWND
user32.RealChildWindowFromPoint.argtypes = [wintypes.HWND, wintypes.POINT]

user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]

user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]

user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]

user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]

user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]

user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.SetLayeredWindowAttributes.argtypes = [
    wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD
]
LWA_ALPHA = 0x00000002

user32.ShowWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

user32.VkKeyScanW.restype = ctypes.c_short
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]


@dataclass
class Monitor:
    name: str            # \\.\DISPLAY1 etc. matches QScreen.name()
    physical: QRect      # physical pixel rect (SetProcessDpiAwarenessContext v2)
    logical: QRect       # Qt logical geometry
    dpr: float


def _enum_monitors() -> list[Monitor]:
    """Return physical monitor rectangles keyed by device name."""
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    results: list[tuple[str, QRect]] = []

    def _cb(_hmon, _hdc, lprect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(_hmon, ctypes.byref(info)):
            r = info.rcMonitor
            results.append((info.szDevice, QRect(r.left, r.top,
                                                 r.right - r.left,
                                                 r.bottom - r.top)))
        return True

    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM
    ]
    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)

    monitors: list[Monitor] = []
    for name, prect in results:
        screen = None
        for s in QGuiApplication.screens():
            if s.name() == name:
                screen = s
                break
        if screen is None:
            continue
        monitors.append(Monitor(name=name, physical=prect,
                                logical=screen.geometry(),
                                dpr=screen.devicePixelRatio()))
    return monitors


def _monitors() -> list[Monitor]:
    return _enum_monitors()


def logical_to_physical(point: QPoint) -> QPoint:
    """Convert a global logical Qt point to physical Win32 pixels."""
    target = QGuiApplication.screenAt(point)
    for m in _monitors():
        if target is not None and m.name == target.name():
            return QPoint(
                m.physical.left()
                + round((point.x() - m.logical.left()) * m.dpr),
                m.physical.top()
                + round((point.y() - m.logical.top()) * m.dpr),
            )
    # fallback: primary screen scale
    ps = QGuiApplication.primaryScreen()
    dpr = ps.devicePixelRatio() if ps else 1.0
    return QPoint(round(point.x() * dpr), round(point.y() * dpr))


def physical_to_logical_rect(rect: QRect) -> QRect:
    """Convert a physical Win32 rect to global logical Qt coordinates."""
    for m in _monitors():
        if m.physical.contains(rect.center()):
            x = m.logical.left() + round((rect.left() - m.physical.left()) / m.dpr)
            y = m.logical.top() + round((rect.top() - m.physical.top()) / m.dpr)
            w = round(rect.width() / m.dpr)
            h = round(rect.height() / m.dpr)
            return QRect(x, y, w, h)
    ps = QGuiApplication.primaryScreen()
    dpr = ps.devicePixelRatio() if ps else 1.0
    return QRect(round(rect.left() / dpr), round(rect.top() / dpr),
                 round(rect.width() / dpr), round(rect.height() / dpr))


# --- window detection ------------------------------------------------------
def get_extended_frame(hwnd: int) -> QRect | None:
    """Real window bounds excluding the invisible resize/DWM shadow border."""
    rect = wintypes.RECT()
    hr = dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
        ctypes.sizeof(rect))
    if hr == 0 and rect.right > rect.left:
        return QRect(rect.left, rect.top,
                     rect.right - rect.left, rect.bottom - rect.top)
    return None


def get_window_rect(hwnd: int) -> QRect:
    rect = get_extended_frame(hwnd)
    if rect is not None:
        return rect
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)


def get_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def hwnd_at_global_logical(point: QPoint) -> int:
    """Deepest visible window/control under a global logical point."""
    p = logical_to_physical(point)
    pt = wintypes.POINT(p.x(), p.y())
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd:
        return 0
    # Walk into child controls (buttons, edits, panels ...). RealChildWindow*
    # honours HTTRANSPARENT so layered hit-testing behaves naturally.
    for _ in range(32):
        child = user32.RealChildWindowFromPoint(hwnd, pt)
        if not child or child == hwnd:
            break
        hwnd = child
    return hwnd


def top_level_at_global_logical(point: QPoint, skip_hwnd: int = 0) -> int:
    """Topmost visible *top-level* window under a point, ignoring skip_hwnd.

    EnumWindows walks top-to-bottom in Z order, so the first hit is the
    topmost window. We need this (instead of WindowFromPoint) while the
    full-screen snipper overlay itself would otherwise always be on top.
    """
    p = logical_to_physical(point)
    pt = wintypes.POINT(p.x(), p.y())
    found = wintypes.HWND(0)

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                     wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        if hwnd == skip_hwnd:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        r = get_window_rect(hwnd)
        if r.contains(p):
            found.value = hwnd
            return False  # stop: topmost hit
        return True

    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found.value or 0


def deepest_in(hwnd: int, point: QPoint) -> int:
    """Walk child controls inside a given top-level window at a logical point."""
    if not hwnd:
        return 0
    p = logical_to_physical(point)
    pt = wintypes.POINT(p.x(), p.y())
    for _ in range(32):
        child = user32.RealChildWindowFromPoint(hwnd, pt)
        if not child or child == hwnd:
            break
        hwnd = child
    return hwnd


def hwnd_chain(hwnd: int) -> list[int]:
    """Return [hwnd, parent, ..., top-level root] for Tab cycling."""
    chain = []
    cur = hwnd
    seen = set()
    while cur and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        root = user32.GetAncestor(cur, GA_ROOT)
        if not root or root == cur:
            break
        cur = user32.GetParent(cur)
    return chain


def window_rect_logical(hwnd: int) -> QRect:
    return physical_to_logical_rect(get_window_rect(hwnd))


# --- mouse transparency / layered attributes ------------------------------
def set_click_through(hwnd: int, through: bool) -> None:
    """Toggle WS_EX_LAYERED | WS_EX_TRANSPARENT for a native window."""
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if through:
        ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        ex &= ~WS_EX_TRANSPARENT
        ex |= WS_EX_LAYERED
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)


def set_window_opacity(hwnd: int, alpha: int) -> None:
    """alpha: 30-255. Requires the window to be layered."""
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if not (ex & WS_EX_LAYERED):
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    user32.SetLayeredWindowAttributes(hwnd, 0, max(10, min(255, alpha)),
                                      LWA_ALPHA)


def is_key_pressed(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def vk_for_char(ch: str) -> int:
    """Best-effort virtual-key code for a single character."""
    res = user32.VkKeyScanW(ch)
    if res == -1:
        return 0
    return res & 0xFF


def native_window_id(qwindow) -> int:
    return int(qwindow.winId()) if qwindow is not None else 0
