"""Global hotkeys via a WH_KEYBOARD_LL low-level hook.

Runs the hook + message loop on a dedicated thread; matches configurable
accelerators (including bare keys like F1 / PrintScreen) and emits Qt signals
on the GUI thread.

All Win32 entry points used here are declared with their exact 64-bit pointer
types; relying on ctypes' default c_int truncates HHOOK / LRESULT and makes
SetWindowsHookExW fail on x64.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

from . import win32

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

# --- exact 64-bit types ----------------------------------------------------
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.CFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM,
                            wintypes.LPARAM)

user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                     wintypes.HINSTANCE, wintypes.DWORD]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.GetLastError.argtypes = []
user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]

_MOD_VK = {"CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "WIN": 0x5B}

# left/right variants normalised to the generic vk
_NORMALISE = {
    0xA0: 0x10, 0xA1: 0x10,      # shift
    0xA2: 0x11, 0xA3: 0x11,      # control
    0xA4: 0x12, 0xA5: 0x12,      # alt/menu
    0x5B: 0x5B, 0x5C: 0x5B,      # win
}


def key_to_vk(name: str) -> int:
    n = name.strip().upper()
    if n in ("PRINT", "PRINTSCREEN", "PRTSC", "PRTSCN", "SNAPSHOT"):
        return 0x2C
    if n == "SPACE":
        return 0x20
    if n in ("INSERT", "INS"):
        return 0x2D
    if n in ("DELETE", "DEL"):
        return 0x2E
    if n == "HOME":
        return 0x24
    if n == "END":
        return 0x23
    if n in ("PAGEUP", "PGUP", "PRIOR"):
        return 0x21
    if n in ("PAGEDOWN", "PGDN", "NEXT"):
        return 0x22
    if n == "LEFT":
        return 0x25
    if n == "UP":
        return 0x26
    if n == "RIGHT":
        return 0x27
    if n == "DOWN":
        return 0x28
    if n in ("ESC", "ESCAPE"):
        return 0x1B
    if n == "TAB":
        return 0x09
    if n in ("ENTER", "RETURN"):
        return 0x0D
    if n in ("BACKSPACE", "BS"):
        return 0x08
    if len(n) >= 2 and n[0] == "F" and n[1:].isdigit():
        idx = int(n[1:])
        if 1 <= idx <= 24:
            return 0x6F + idx
    if len(n) == 1:
        ch = name.strip()
        if ch.isalpha():
            return ord(ch.upper())
        if ch.isdigit():
            return ord(ch)
        vk = win32.vk_for_char(ch)
        if vk:
            return vk
    return 0


def parse_hotkey(text: str) -> tuple[frozenset[int], int]:
    """Return (modifier vks, main vk) for a string like 'Ctrl+Shift+A'."""
    mods: set[int] = set()
    main = 0
    for part in str(text).split("+"):
        token = part.strip().upper()
        if not token:
            continue
        if token in _MOD_VK:
            mods.add(_MOD_VK[token])
        else:
            main = key_to_vk(part)
    return frozenset(mods), main


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HotkeyManager(QObject):
    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self._bindings: dict[str, tuple[frozenset[int], int]] = {}
        self._hook = None
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._fired: set[int] = set()
        self._lock = threading.Lock()
        # keep the callback alive for the lifetime of the manager
        self._proc = HOOKPROC(self._callback)

    # -- configuration ------------------------------------------------------
    def bind(self, action_id: str, text: str) -> None:
        with self._lock:
            mods, vk = parse_hotkey(text)
            if vk:
                self._bindings[action_id] = (mods, vk)
            else:
                self._bindings.pop(action_id, None)

    def unbind_all(self) -> None:
        with self._lock:
            self._bindings.clear()

    # -- current modifiers --------------------------------------------------
    @staticmethod
    def _live_modifiers() -> frozenset[int]:
        mods = set()
        if win32.is_key_pressed(0x11):
            mods.add(0x11)
        if win32.is_key_pressed(0x12):
            mods.add(0x12)
        if win32.is_key_pressed(0x10):
            mods.add(0x10)
        if win32.is_key_pressed(0x5B):
            mods.add(0x5B)
        return frozenset(mods)

    # -- hook callback ------------------------------------------------------
    def _callback(self, n_code, w_param, l_param):
        import os as _os
        _trace = _os.environ.get("HK_TRACE")
        if _trace:
            print(f"[hook] n={n_code} w={w_param} ", end="", flush=True)
        if n_code >= 0:
            kb = ctypes.cast(l_param,
                             ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            vk = int(kb.vkCode)
            vk = _NORMALISE.get(vk, vk)
            is_up = bool(kb.flags & 0x80)
            if _trace:
                print(f"vk={vk} up={is_up}", flush=True)
            if is_up:
                self._fired.discard(vk)
            elif w_param in (win32.WM_KEYDOWN, win32.WM_SYSKEYDOWN):
                if vk not in self._fired:
                    mods = self._live_modifiers()
                    with self._lock:
                        items = list(self._bindings.items())
                    if _trace:
                        print(f"        live_mods={set(mods)} "
                              f"bindings={[(a,set(m),v) for a,(m,v) in items]}",
                              flush=True)
                    for action_id, (need_mods, need_vk) in items:
                        if need_vk == vk and need_mods == mods:
                            self._fired.add(vk)
                            self.triggered.emit(action_id)
                            return 1  # swallow the hotkey
        return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="HotkeyHook",
                                        daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        hmod = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(
            win32.WH_KEYBOARD_LL, self._proc, hmod, 0)
        if not self._hook:
            err = kernel32.GetLastError()
            print(f"[HotkeyManager] SetWindowsHookExW failed, error={err}",
                  flush=True)
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def stop(self) -> None:
        if self._thread is not None and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(timeout=1.0)
            self._thread = None
