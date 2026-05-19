"""
PortaKeys – Portable Virtual Keyboard for Windows
==================================================
A single-file, dependency-free virtual on-screen keyboard with a fully
customizable "floor plan" (layout) defined in JSON.

Features
--------
* Pure standard library (tkinter + ctypes). No pip installs. Works from a USB stick.
* Sends real keystrokes to the focused window using the Win32 SendInput API,
  with hardware scancodes so it works in games, RDP, UAC dialogs, etc.
* Layouts are JSON files describing keys at arbitrary x/y/w/h grid positions.
  You can build any "floor plan": staggered, ortholinear, split, numpad,
  gaming pad, accessibility one-hand, custom macros – anything.
* Live layout editor (drag, resize, add, delete, rename, remap).
* Sticky modifiers (Shift / Ctrl / Alt / Win) with one-shot or lock modes.
* Multi-layer support (Base / Shift / Fn) per layout.
* Always-on-top, opacity slider, snap-to-edge, click-through option.
* Macro keys: type a string or run a sequence of keystrokes.
* Keystroke translations: define stroke patterns that auto-convert to target chars.
* Save / load layouts. Ships with several built-in presets that are written
  to disk on first run so you can edit them.

Run
---
    python portakeys.py

Build portable EXE (optional)
-----------------------------
    pip install pyinstaller
    pyinstaller --onefile --noconsole portakeys.py

Author: PortaKeys
License: MIT
"""

import os
import sys
import json
import time
import ctypes
import ctypes.wintypes as wt
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

APP_NAME = "PortaKeys"
APP_VERSION = "1.1.0"
APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
LAYOUT_DIR = os.path.join(APP_DIR, "layouts")
CONFIG_PATH = os.path.join(APP_DIR, "portakeys.config.json")

IS_WINDOWS = sys.platform.startswith("win")


# ---------------------------------------------------------------------------
# Win32 SendInput plumbing
# ---------------------------------------------------------------------------
# We use scancodes (KEYEVENTF_SCANCODE) so injected keys behave like real
# hardware. This is essential for DirectInput games and many secure dialogs
# that ignore virtual-key-only injection.

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_SCANCODE = 0x0008
    MAPVK_VK_TO_VSC_EX = 4

    # Low-level keyboard hook constants
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    LLKHF_EXTENDED = 0x00000001
    LLKHF_INJECTED = 0x00000010
    LLKHF_ALTDOWN = 0x00000020
    LLKHF_UP = 0x00000080

    ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wt.WORD),
            ("wScan", wt.WORD),
            ("dwFlags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wt.LONG),
            ("dy", wt.LONG),
            ("mouseData", wt.DWORD),
            ("dwFlags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = (
            ("uMsg", wt.DWORD),
            ("wParamL", wt.WORD),
            ("wParamH", wt.WORD),
        )

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = (
            ("vkCode", wt.DWORD),
            ("scanCode", wt.DWORD),
            ("flags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class _INPUTUnion(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = (("type", wt.DWORD), ("u", _INPUTUnion))

    user32.SendInput.argtypes = (wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wt.UINT
    user32.MapVirtualKeyExW.argtypes = (wt.UINT, wt.UINT, wt.HKL)
    user32.MapVirtualKeyExW.restype = wt.UINT
    user32.GetKeyboardLayout.argtypes = (wt.DWORD,)
    user32.GetKeyboardLayout.restype = wt.HKL

    # Low-level keyboard hook APIs
    # Define LRESULT as c_longlong (64-bit) or c_long (32-bit)
    LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
    LOWLEVELKEYBOARDPROC = ctypes.CFUNCTYPE(LRESULT, wt.INT, wt.WPARAM, wt.LPARAM)
    user32.SetWindowsHookExW.argtypes = (wt.INT, LOWLEVELKEYBOARDPROC, wt.HINSTANCE, wt.DWORD)
    user32.SetWindowsHookExW.restype = wt.HANDLE
    user32.UnhookWindowsHookEx.argtypes = (wt.HANDLE,)
    user32.UnhookWindowsHookEx.restype = wt.BOOL
    user32.CallNextHookEx.argtypes = (wt.HANDLE, wt.INT, wt.WPARAM, wt.LPARAM)
    user32.CallNextHookEx.restype = LRESULT
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.argtypes = (wt.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wt.HMODULE

    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_TOPMOST = 0x00000008
    HWND_TOPMOST = -1
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    GA_ROOT = 2

    user32.GetWindowLongW.argtypes = (wt.HWND, ctypes.c_int)
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = (wt.HWND, ctypes.c_int, ctypes.c_long)
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.GetAncestor.argtypes = (wt.HWND, wt.UINT)
    user32.GetAncestor.restype = wt.HWND
    user32.SetWindowPos.argtypes = (wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wt.UINT)
    user32.SetWindowPos.restype = wt.BOOL


def make_window_non_activating(tk_hwnd):
    """Apply WS_EX_NOACTIVATE so clicking the keyboard never steals focus
    from whatever editor/input field the user is typing into. This is the
    same trick the Windows on-screen keyboard (osk.exe) uses."""
    if not IS_WINDOWS:
        return
    try:
        root = user32.GetAncestor(int(tk_hwnd), GA_ROOT) or int(tk_hwnd)
        cur = user32.GetWindowLongW(root, GWL_EXSTYLE)
        new = cur | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        user32.SetWindowLongW(root, GWL_EXSTYLE, new)
        user32.SetWindowPos(
            root, wt.HWND(HWND_TOPMOST), 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
    except Exception:
        pass


def _build_keyboard_input(vk: int, scan: int, flags: int) -> "INPUT":
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def _scancode_for_vk(vk: int) -> int:
    if not IS_WINDOWS:
        return 0
    hkl = user32.GetKeyboardLayout(0)
    sc_ex = user32.MapVirtualKeyExW(vk, MAPVK_VK_TO_VSC_EX, hkl)
    return sc_ex & 0xFFFF


# Extended-key virtual-key codes that need the EXTENDEDKEY flag.
EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # PgUp/Dn, End, Home, arrows
    0x2D, 0x2E,  # Insert, Delete
    0x5B, 0x5C, 0x5D,  # LWin, RWin, Apps
    0x90,  # NumLock
    0xA3,  # RControl
    0xA5,  # RMenu (RAlt)
    0x6F,  # Numpad divide
    0x0D,  # Enter (numpad enter is extended)
}


def send_vk(vk: int, down: bool) -> None:
    """Send a virtual-key as a scancode event."""
    if not IS_WINDOWS:
        return
    scan = _scancode_for_vk(vk)
    flags = KEYEVENTF_SCANCODE
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
        scan = (scan & 0xFF) | 0xE000
    if not down:
        flags |= KEYEVENTF_KEYUP
    inp = _build_keyboard_input(0, scan & 0xFF, flags)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def send_unicode_char(ch: str) -> None:
    """Inject a unicode character via KEYEVENTF_UNICODE (handles surrogates)."""
    if not IS_WINDOWS:
        return
    encoded = ch.encode("utf-16-le")
    for i in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[i:i + 2], "little")
        for is_up in (False, True):
            flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if is_up else 0)
            inp = _build_keyboard_input(0, unit, flags)
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def tap_vk(vk: int, hold_ms: int = 0) -> None:
    send_vk(vk, True)
    if hold_ms:
        time.sleep(hold_ms / 1000.0)
    send_vk(vk, False)


def type_string(text: str) -> None:
    for ch in text:
        if ch == "\n":
            tap_vk(0x0D)
        elif ch == "\t":
            tap_vk(0x09)
        else:
            send_unicode_char(ch)


# ---------------------------------------------------------------------------
# Friendly key-name -> Win32 virtual-key code map
# ---------------------------------------------------------------------------

VK = {
    # mouse / system
    "Backspace": 0x08, "Tab": 0x09, "Clear": 0x0C, "Enter": 0x0D, "Return": 0x0D,
    "Shift": 0xA0, "LShift": 0xA0, "RShift": 0xA1,
    "Ctrl": 0xA2, "LCtrl": 0xA2, "RCtrl": 0xA3,
    "Alt": 0xA4, "LAlt": 0xA4, "RAlt": 0xA5,
    "Pause": 0x13, "CapsLock": 0x14, "Esc": 0x1B, "Escape": 0x1B,
    "Space": 0x20, "PgUp": 0x21, "PgDn": 0x22, "End": 0x23, "Home": 0x24,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
    "PrintScreen": 0x2C, "Insert": 0x2D, "Delete": 0x2E,
    "Win": 0x5B, "LWin": 0x5B, "RWin": 0x5C, "Apps": 0x5D, "Menu": 0x5D,
    # numpad
    "Num0": 0x60, "Num1": 0x61, "Num2": 0x62, "Num3": 0x63, "Num4": 0x64,
    "Num5": 0x65, "Num6": 0x66, "Num7": 0x67, "Num8": 0x68, "Num9": 0x69,
    "NumMul": 0x6A, "NumAdd": 0x6B, "NumSub": 0x6D, "NumDec": 0x6E, "NumDiv": 0x6F,
    "NumEnter": 0x0D, "NumLock": 0x90,
    # function row
    **{f"F{i}": 0x70 + (i - 1) for i in range(1, 25)},
    # OEM punctuation (US layout)
    "ScrollLock": 0x91, ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE,
    "/": 0xBF, "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
    # media
    "VolMute": 0xAD, "VolDown": 0xAE, "VolUp": 0xAF,
    "MediaNext": 0xB0, "MediaPrev": 0xB1, "MediaStop": 0xB2, "MediaPlay": 0xB3,
}

for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    VK[_c] = ord(_c)
for _c in "0123456789":
    VK[_c] = ord(_c)


def resolve_vk(name: str):
    """Return a virtual-key code for a friendly name, or None."""
    if not name:
        return None
    if name in VK:
        return VK[name]
    upper = name.upper()
    if upper in VK:
        return VK[upper]
    if len(name) == 1:
        return ord(name.upper())
    return None


MODIFIER_NAMES = {"Shift", "Ctrl", "Alt", "Win",
                  "LShift", "RShift", "LCtrl", "RCtrl",
                  "LAlt", "RAlt", "LWin", "RWin"}


# ---------------------------------------------------------------------------
# Built-in layout presets
# ---------------------------------------------------------------------------
#
# A layout is a JSON document:
#   {
#     "name": "...",
#     "grid": 36,                # pixel size of one grid unit
#     "cols": 30, "rows": 6,     # canvas dimensions, in grid units
#     "keys": [
#         {
#             "x": 0, "y": 0,    # position in grid units
#             "w": 2, "h": 1,    # size in grid units
#             "label": "Esc",    # text drawn on the cap
#             "vk": "Esc",       # OPTIONAL friendly VK name
#             "text": "hello",   # OPTIONAL: type literal text instead of vk
#             "macro": [ ... ],  # OPTIONAL: list of {"vk":"A","mods":["Ctrl"]}
#             "toggle": false,   # OPTIONAL: sticky / toggle key
#             "color": "#2a2a2a" # OPTIONAL: cap colour
#         },
#         ...
#     ]
#   }

def _row(y, keys, x_start=0):
    out = []
    x = x_start
    for spec in keys:
        if isinstance(spec, str):
            label, w = spec, 1
            vk = spec
        else:
            label = spec.get("label", spec.get("vk", "?"))
            w = spec.get("w", 1)
            vk = spec.get("vk", label)
        item = {"x": x, "y": y, "w": w, "h": 1, "label": label, "vk": vk}
        for k in ("text", "macro", "toggle", "color"):
            if isinstance(spec, dict) and k in spec:
                item[k] = spec[k]
        out.append(item)
        x += w
    return out


def preset_full_ansi():
    keys = []
    keys += _row(0, [
        {"label": "Esc", "vk": "Esc"},
        {"label": "F1", "vk": "F1"}, {"label": "F2", "vk": "F2"},
        {"label": "F3", "vk": "F3"}, {"label": "F4", "vk": "F4"},
        {"label": "F5", "vk": "F5"}, {"label": "F6", "vk": "F6"},
        {"label": "F7", "vk": "F7"}, {"label": "F8", "vk": "F8"},
        {"label": "F9", "vk": "F9"}, {"label": "F10", "vk": "F10"},
        {"label": "F11", "vk": "F11"}, {"label": "F12", "vk": "F12"},
        {"label": "PrtSc", "vk": "PrintScreen"},
        {"label": "ScrLk", "vk": "ScrollLock"},
        {"label": "Pause", "vk": "Pause"},
    ])
    keys += _row(1, [
        "`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=",
        {"label": "Backspace", "vk": "Backspace", "w": 2},
    ])
    keys += _row(2, [
        {"label": "Tab", "vk": "Tab", "w": 1},
        "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]",
        {"label": "\\", "vk": "\\"},
    ])
    keys += _row(3, [
        {"label": "Caps", "vk": "CapsLock", "toggle": True},
        "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'",
        {"label": "Enter", "vk": "Enter", "w": 2},
    ])
    keys += _row(4, [
        {"label": "Shift", "vk": "Shift", "toggle": True, "w": 2},
        "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/",
        {"label": "Shift", "vk": "RShift", "toggle": True, "w": 2},
    ])
    keys += _row(5, [
        {"label": "Ctrl", "vk": "Ctrl", "toggle": True},
        {"label": "Win", "vk": "Win"},
        {"label": "Alt", "vk": "Alt", "toggle": True},
        {"label": "Space", "vk": "Space", "w": 7},
        {"label": "Alt", "vk": "RAlt", "toggle": True},
        {"label": "Win", "vk": "RWin"},
        {"label": "Menu", "vk": "Apps"},
        {"label": "Ctrl", "vk": "RCtrl", "toggle": True},
    ])
    arrows = [
        {"x": 16, "y": 5, "w": 1, "h": 1, "label": "◄", "vk": "Left"},
        {"x": 17, "y": 5, "w": 1, "h": 1, "label": "▼", "vk": "Down"},
        {"x": 18, "y": 5, "w": 1, "h": 1, "label": "►", "vk": "Right"},
        {"x": 17, "y": 4, "w": 1, "h": 1, "label": "▲", "vk": "Up"},
    ]
    return {"name": "Full ANSI", "grid": 36, "cols": 19, "rows": 6,
            "keys": keys + arrows}


def preset_numpad():
    keys = [
        {"x": 0, "y": 0, "w": 1, "h": 1, "label": "Num", "vk": "NumLock", "toggle": True},
        {"x": 1, "y": 0, "w": 1, "h": 1, "label": "/", "vk": "NumDiv"},
        {"x": 2, "y": 0, "w": 1, "h": 1, "label": "*", "vk": "NumMul"},
        {"x": 3, "y": 0, "w": 1, "h": 1, "label": "-", "vk": "NumSub"},
        {"x": 0, "y": 1, "w": 1, "h": 1, "label": "7", "vk": "Num7"},
        {"x": 1, "y": 1, "w": 1, "h": 1, "label": "8", "vk": "Num8"},
        {"x": 2, "y": 1, "w": 1, "h": 1, "label": "9", "vk": "Num9"},
        {"x": 3, "y": 1, "w": 1, "h": 2, "label": "+", "vk": "NumAdd"},
        {"x": 0, "y": 2, "w": 1, "h": 1, "label": "4", "vk": "Num4"},
        {"x": 1, "y": 2, "w": 1, "h": 1, "label": "5", "vk": "Num5"},
        {"x": 2, "y": 2, "w": 1, "h": 1, "label": "6", "vk": "Num6"},
        {"x": 0, "y": 3, "w": 1, "h": 1, "label": "1", "vk": "Num1"},
        {"x": 1, "y": 3, "w": 1, "h": 1, "label": "2", "vk": "Num2"},
        {"x": 2, "y": 3, "w": 1, "h": 1, "label": "3", "vk": "Num3"},
        {"x": 3, "y": 3, "w": 1, "h": 2, "label": "Enter", "vk": "Enter"},
        {"x": 0, "y": 4, "w": 2, "h": 1, "label": "0", "vk": "Num0"},
        {"x": 2, "y": 4, "w": 1, "h": 1, "label": ".", "vk": "NumDec"},
    ]
    return {"name": "Numpad", "grid": 48, "cols": 4, "rows": 5, "keys": keys}


def preset_one_hand():
    keys = [
        {"x": 0, "y": 0, "w": 1, "h": 1, "label": "Q", "vk": "Q"},
        {"x": 1, "y": 0, "w": 1, "h": 1, "label": "W", "vk": "W"},
        {"x": 2, "y": 0, "w": 1, "h": 1, "label": "E", "vk": "E"},
        {"x": 3, "y": 0, "w": 1, "h": 1, "label": "R", "vk": "R"},
        {"x": 4, "y": 0, "w": 1, "h": 1, "label": "T", "vk": "T"},
        {"x": 0, "y": 1, "w": 1, "h": 1, "label": "A", "vk": "A"},
        {"x": 1, "y": 1, "w": 1, "h": 1, "label": "S", "vk": "S"},
        {"x": 2, "y": 1, "w": 1, "h": 1, "label": "D", "vk": "D"},
        {"x": 3, "y": 1, "w": 1, "h": 1, "label": "F", "vk": "F"},
        {"x": 4, "y": 1, "w": 1, "h": 1, "label": "G", "vk": "G"},
        {"x": 0, "y": 2, "w": 1, "h": 1, "label": "Z", "vk": "Z"},
        {"x": 1, "y": 2, "w": 1, "h": 1, "label": "X", "vk": "X"},
        {"x": 2, "y": 2, "w": 1, "h": 1, "label": "C", "vk": "C"},
        {"x": 3, "y": 2, "w": 1, "h": 1, "label": "V", "vk": "V"},
        {"x": 4, "y": 2, "w": 1, "h": 1, "label": "B", "vk": "B"},
        {"x": 0, "y": 3, "w": 2, "h": 1, "label": "Shift", "vk": "Shift", "toggle": True},
        {"x": 2, "y": 3, "w": 2, "h": 1, "label": "Space", "vk": "Space"},
        {"x": 4, "y": 3, "w": 1, "h": 1, "label": "↵", "vk": "Enter"},
    ]
    return {"name": "One-Hand Gaming", "grid": 56, "cols": 5, "rows": 4, "keys": keys}


def preset_macro_pad():
    keys = [
        {"x": 0, "y": 0, "w": 1, "h": 1, "label": "Copy",
         "macro": [{"vk": "C", "mods": ["Ctrl"]}], "color": "#274472"},
        {"x": 1, "y": 0, "w": 1, "h": 1, "label": "Cut",
         "macro": [{"vk": "X", "mods": ["Ctrl"]}], "color": "#274472"},
        {"x": 2, "y": 0, "w": 1, "h": 1, "label": "Paste",
         "macro": [{"vk": "V", "mods": ["Ctrl"]}], "color": "#274472"},
        {"x": 3, "y": 0, "w": 1, "h": 1, "label": "Undo",
         "macro": [{"vk": "Z", "mods": ["Ctrl"]}], "color": "#274472"},
        {"x": 0, "y": 1, "w": 1, "h": 1, "label": "Save",
         "macro": [{"vk": "S", "mods": ["Ctrl"]}], "color": "#3a6b35"},
        {"x": 1, "y": 1, "w": 1, "h": 1, "label": "Find",
         "macro": [{"vk": "F", "mods": ["Ctrl"]}], "color": "#3a6b35"},
        {"x": 2, "y": 1, "w": 1, "h": 1, "label": "All",
         "macro": [{"vk": "A", "mods": ["Ctrl"]}], "color": "#3a6b35"},
        {"x": 3, "y": 1, "w": 1, "h": 1, "label": "AltTab",
         "macro": [{"vk": "Tab", "mods": ["Alt"]}], "color": "#3a6b35"},
        {"x": 0, "y": 2, "w": 2, "h": 1, "label": "Sign-off",
         "text": "Best regards,\nAlex\n", "color": "#7a4a1f"},
        {"x": 2, "y": 2, "w": 2, "h": 1, "label": "Email",
         "text": "alex@example.com", "color": "#7a4a1f"},
        {"x": 0, "y": 3, "w": 4, "h": 1, "label": "Lock workstation",
         "macro": [{"vk": "L", "mods": ["Win"]}], "color": "#5a1f1f"},
    ]
    return {"name": "Macro Pad", "grid": 72, "cols": 4, "rows": 4, "keys": keys}


BUILT_IN_PRESETS = [preset_full_ansi, preset_numpad, preset_one_hand, preset_macro_pad]


# ---------------------------------------------------------------------------
# Disk I/O – config and layouts
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "last_layout": "Full ANSI.json",
    "always_on_top": True,
    "opacity": 0.95,
    "click_through": False,
    "theme": "dark",
    "window": {"x": 80, "y": 80},
    "keystroke_translations": {},  # stroke pattern -> target char
}


def ensure_dirs():
    os.makedirs(LAYOUT_DIR, exist_ok=True)


def write_default_layouts():
    ensure_dirs()
    for fn in BUILT_IN_PRESETS:
        layout = fn()
        path = os.path.join(LAYOUT_DIR, f"{layout['name']}.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(layout, f, indent=2)


def list_layout_files():
    ensure_dirs()
    return sorted(p for p in os.listdir(LAYOUT_DIR) if p.lower().endswith(".json"))


def load_layout_file(filename: str):
    path = os.path.join(LAYOUT_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_layout_file(filename: str, layout: dict):
    ensure_dirs()
    path = os.path.join(LAYOUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# THEME
# ---------------------------------------------------------------------------

THEMES = {
    "dark": {
        "bg": "#1e1e22", "panel": "#2a2a30", "cap": "#3a3a42",
        "cap_hover": "#4a4a55", "cap_active": "#6a8caf",
        "cap_locked": "#c08a3a", "text": "#f5f5f7", "muted": "#9a9aa0",
        "outline": "#0f0f12",
    },
    "light": {
        "bg": "#ececef", "panel": "#f6f6f8", "cap": "#fafafb",
        "cap_hover": "#e5e5ea", "cap_active": "#cfe1f5",
        "cap_locked": "#f5d68f", "text": "#1c1c1f", "muted": "#666",
        "outline": "#bcbcc2",
    },
}


# ---------------------------------------------------------------------------
# Key cap widget
# ---------------------------------------------------------------------------

class KeyCap:
    __slots__ = ("spec", "rect", "text_id", "x", "y", "w", "h",
                 "hovered", "active", "locked")

    def __init__(self, spec):
        self.spec = spec
        self.rect = None
        self.text_id = None
        self.x = spec.get("x", 0)
        self.y = spec.get("y", 0)
        self.w = max(1, spec.get("w", 1))
        self.h = max(1, spec.get("h", 1))
        self.hovered = False
        self.active = False
        self.locked = False

    @property
    def is_modifier(self):
        return self.spec.get("vk") in MODIFIER_NAMES

    @property
    def is_toggle(self):
        return bool(self.spec.get("toggle"))


# ---------------------------------------------------------------------------
# Translations Editor Dialog
# ---------------------------------------------------------------------------

class TranslationsDialog(tk.Toplevel):
    """Dialog for managing keystroke translation patterns."""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Keystroke Translations")
        self.geometry("450x400")
        self.transient(parent)
        self.grab_set()
        
        theme = THEMES[app.config_data.get("theme", "dark")]
        self.configure(bg=theme["panel"])
        
        self.translations = dict(app.config_data.get("keystroke_translations", {}))
        
        self._build_ui(theme)
        self._refresh_list()
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _build_ui(self, theme):
        # Info label
        info = tk.Label(self, text="Define stroke patterns that auto-convert to target characters.",
                       bg=theme["panel"], fg=theme["muted"], wraplength=400, justify="left")
        info.pack(fill="x", padx=10, pady=(10, 5))
        
        # List frame
        list_frame = tk.Frame(self, bg=theme["panel"])
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Scrollbar and listbox
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                   bg=theme["bg"], fg=theme["text"],
                                   selectbackground=theme["cap_active"],
                                   selectforeground=theme["text"],
                                   font=("Consolas", 10))
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        # Buttons frame
        btn_frame = tk.Frame(self, bg=theme["panel"])
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        def btn(text, cmd, accent=False):
            bg = theme["cap_active"] if accent else theme["cap"]
            return tk.Button(btn_frame, text=text, command=cmd,
                           bg=bg, fg=theme["text"],
                           activebackground=theme["cap_hover"],
                           relief="flat", padx=10, pady=3)
        
        btn("Add", self._add_translation).pack(side="left", padx=2)
        btn("Edit", self._edit_translation).pack(side="left", padx=2)
        btn("Delete", self._delete_translation).pack(side="left", padx=2)
        btn("Save & Close", self._save_and_close, accent=True).pack(side="right", padx=2)
        
        # Example label
        example = tk.Label(self, text="Example: '''' → a  or  xxxx → ä",
                          bg=theme["panel"], fg=theme["muted"], font=("Consolas", 9))
        example.pack(fill="x", padx=10, pady=(0, 10))
        
    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for stroke, target in sorted(self.translations.items()):
            display = f"{repr(stroke)[1:-1]:<15} → {repr(target)[1:-1]}"
            self.listbox.insert(tk.END, display)
            
    def _add_translation(self):
        self._edit_translation_dialog(None, None)
        
    def _edit_translation(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Edit", "Please select a translation to edit.", parent=self)
            return
        idx = sel[0]
        items = sorted(self.translations.items())
        stroke, target = items[idx]
        self._edit_translation_dialog(stroke, target)
        
    def _delete_translation(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Delete", "Please select a translation to delete.", parent=self)
            return
        idx = sel[0]
        items = sorted(self.translations.items())
        stroke, target = items[idx]
        if messagebox.askyesno("Confirm Delete", f"Delete '{stroke}' → '{target}'?", parent=self):
            del self.translations[stroke]
            self._refresh_list()
            
    def _edit_translation_dialog(self, old_stroke, old_target):
        """Open a dialog to add or edit a translation."""
        dialog = tk.Toplevel(self)
        dialog.title("Edit Translation" if old_stroke else "Add Translation")
        dialog.geometry("350x150")
        dialog.transient(self)
        dialog.grab_set()
        
        theme = THEMES[self.app.config_data.get("theme", "dark")]
        dialog.configure(bg=theme["panel"])
        
        # Stroke pattern
        tk.Label(dialog, text="Stroke Pattern:", bg=theme["panel"], fg=theme["text"]).pack(anchor="w", padx=10, pady=(10, 0))
        stroke_var = tk.StringVar(value=old_stroke if old_stroke else "")
        stroke_entry = tk.Entry(dialog, textvariable=stroke_var, bg=theme["bg"], fg=theme["text"], insertbackground=theme["text"])
        stroke_entry.pack(fill="x", padx=10, pady=2)
        
        # Target character
        tk.Label(dialog, text="Target Character:", bg=theme["panel"], fg=theme["text"]).pack(anchor="w", padx=10, pady=(5, 0))
        target_var = tk.StringVar(value=old_target if old_target else "")
        target_entry = tk.Entry(dialog, textvariable=target_var, bg=theme["bg"], fg=theme["text"], insertbackground=theme["text"])
        target_entry.pack(fill="x", padx=10, pady=2)
        
        def save():
            stroke = stroke_var.get()
            target = target_var.get()
            if not stroke or not target:
                messagebox.showwarning("Invalid", "Both fields are required.", parent=dialog)
                return
            if len(target) != 1:
                messagebox.showwarning("Invalid", "Target must be exactly one character.", parent=dialog)
                return
            # Remove old entry if editing
            if old_stroke and old_stroke in self.translations:
                del self.translations[old_stroke]
            self.translations[stroke] = target
            self._refresh_list()
            dialog.destroy()
            
        # Buttons
        btn_frame = tk.Frame(dialog, bg=theme["panel"])
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Button(btn_frame, text="Save", command=save,
                 bg=theme["cap_active"], fg=theme["text"],
                 activebackground=theme["cap_hover"], relief="flat", padx=15).pack(side="right", padx=2)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy,
                 bg=theme["cap"], fg=theme["text"],
                 activebackground=theme["cap_hover"], relief="flat", padx=15).pack(side="right", padx=2)
        
        stroke_entry.focus_set()
        if old_stroke:
            stroke_entry.select_range(0, tk.END)
        
        self.wait_window(dialog)
        
    def _save_and_close(self):
        self.app.config_data["keystroke_translations"] = self.translations
        save_config(self.app.config_data)
        self.destroy()
        
    def _on_close(self):
        # Discard changes
        self.destroy()


# ---------------------------------------------------------------------------
# Main keyboard widget
# ---------------------------------------------------------------------------


# Global keyboard hook callback (module-level for ctypes callback)
_keyboard_hook_handle = None
_keyboard_canvas_ref = None

def _get_char_from_vk_code(vk_code):
    """Convert VK code to character for stroke buffer."""
    # Letters A-Z
    if 0x41 <= vk_code <= 0x5A:
        return chr(vk_code).lower()
    # Numbers 0-9
    if 0x30 <= vk_code <= 0x39:
        return chr(vk_code)
    # Space
    if vk_code == 0x20:
        return " "
    # Common punctuation (VK codes)
    punct_map = {
        0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-",
        0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[",
        0xDC: "\\", 0xDD: "]", 0xDE: "'",
    }
    if vk_code in punct_map:
        return punct_map[vk_code]
    return None

def _check_physical_key_translations(char):
    """Check if buffer + new char matches any translation pattern."""
    if _keyboard_canvas_ref is None:
        return None
    canvas = _keyboard_canvas_ref()
    if canvas is None:
        return None
    
    translations = canvas.app.config_data.get("keystroke_translations", {})
    if not translations:
        return None
    
    test_buffer = canvas._stroke_buffer + char
    
    # Check for exact matches - sort by length (longest first)
    for pattern, target in sorted(translations.items(), key=lambda x: -len(x[0])):
        if test_buffer.endswith(pattern):
            return pattern, target
    
    return None

@LOWLEVELKEYBOARDPROC
def _low_level_keyboard_hook(nCode, wParam, lParam):
    """Low-level keyboard hook callback for physical keystrokes."""
    if nCode < 0:
        return user32.CallNextHookEx(None, nCode, wParam, lParam)
    
    if _keyboard_canvas_ref is None:
        return user32.CallNextHookEx(None, nCode, wParam, lParam)
    
    canvas = _keyboard_canvas_ref()
    if canvas is None:
        return user32.CallNextHookEx(None, nCode, wParam, lParam)
    
    # Parse the keyboard hook struct
    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
    vk_code = kb.vkCode
    
    # Skip injected/synthetic keystrokes to avoid re-processing our own output
    if kb.flags & LLKHF_INJECTED:
        return user32.CallNextHookEx(None, nCode, wParam, lParam)
    
    # Only process key down events
    is_keydown = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
    is_keyup = wParam in (WM_KEYUP, WM_SYSKEYUP)
    
    # Get character representation
    char = _get_char_from_vk_code(vk_code)
    
    # Clear buffer on special keys
    if is_keydown:
        if vk_code in (0x0D, 0x09, 0x08, 0x1B, 0x20,  # Enter, Tab, Backspace, Esc, Space
                       0x25, 0x26, 0x27, 0x28,  # Left, Up, Right, Down
                       0x23, 0x24, 0x21, 0x22):  # End, Home, PgUp, PgDn
            canvas._stroke_buffer = ""
        elif char:
            # Check for translation
            translation = _check_physical_key_translations(char)
            if translation:
                pattern, target = translation
                # Send backspaces to delete the pattern characters (minus 1 because current char is blocked)
                for _ in range(len(pattern) - 1):
                    tap_vk(0x08)  # Backspace VK
                    time.sleep(0.005)
                # Type the target character
                type_string(target)
                # Clear the buffer
                canvas._stroke_buffer = ""
                # Block the original keystroke
                return 1
            else:
                # Add to buffer
                canvas._stroke_buffer += char
                if len(canvas._stroke_buffer) > canvas._stroke_max_len:
                    canvas._stroke_buffer = canvas._stroke_buffer[-canvas._stroke_max_len:]
    
    # Pass through to next hook
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def _install_keyboard_hook(canvas):
    """Install the low-level keyboard hook."""
    global _keyboard_hook_handle, _keyboard_canvas_ref
    if not IS_WINDOWS:
        return
    
    import weakref
    _keyboard_canvas_ref = weakref.ref(canvas)
    
    hMod = kernel32.GetModuleHandleW(None)
    _keyboard_hook_handle = user32.SetWindowsHookExW(
        WH_KEYBOARD_LL, _low_level_keyboard_hook, hMod, 0
    )
    if _keyboard_hook_handle:
        print("Physical keyboard hook installed")
    else:
        print("Failed to install keyboard hook")

def _uninstall_keyboard_hook():
    """Uninstall the low-level keyboard hook."""
    global _keyboard_hook_handle, _keyboard_canvas_ref
    if _keyboard_hook_handle and IS_WINDOWS:
        user32.UnhookWindowsHookEx(_keyboard_hook_handle)
        _keyboard_hook_handle = None
        _keyboard_canvas_ref = None
        print("Physical keyboard hook uninstalled")


class KeyboardCanvas(tk.Canvas):
    def __init__(self, master, app, **kw):
        super().__init__(master, highlightthickness=0, **kw)
        self.app = app
        self.layout = None
        self.caps = []
        self.held_modifiers = set()
        self.locked_modifiers = set()
        self.editing = False
        self._drag = None
        self._selected = None
        
        # Stroke buffer for translation detection
        self._stroke_buffer = ""
        self._stroke_max_len = 50  # Maximum pattern length to track

        # Install physical keyboard hook
        _install_keyboard_hook(self)
        
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Button-3>", self._on_right_click)
        # NOTE: We deliberately do NOT bind <Double-Button-1>. In Tk, when both
        # <Button-1> and <Double-Button-1> are bound, the *second* click of a
        # rapid double-click fires only <Double-Button-1> (most-specific match
        # wins) and <Button-1> is suppressed. That caused every other keystroke
        # in a fast burst to be silently dropped. Instead we detect double
        # clicks in software inside _on_press using event.time, so every press
        # always sends a keystroke.
        self._last_press_time = 0
        self._last_press_cap = None
        self._double_click_ms = 350
        self.bind("<Configure>", lambda e: self.redraw())

    # ---- layout management -------------------------------------------------

    def set_layout(self, layout: dict):
        self.layout = layout
        self.caps = [KeyCap(s) for s in layout.get("keys", [])]
        self.held_modifiers.clear()
        self.locked_modifiers.clear()
        self._stroke_buffer = ""  # Clear buffer on layout change
        self._resize_canvas()
        self.redraw()

    def _resize_canvas(self):
        if not self.layout:
            return
        g = self.layout.get("grid", 36)
        cols = self.layout.get("cols", 16)
        rows = self.layout.get("rows", 5)
        self.config(width=cols * g + 8, height=rows * g + 8)

    def redraw(self):
        self.delete("all")
        if not self.layout:
            return
        theme = THEMES[self.app.config_data.get("theme", "dark")]
        self.configure(bg=theme["panel"])
        g = self.layout.get("grid", 36)
        pad = 3
        for cap in self.caps:
            x1 = cap.x * g + pad
            y1 = cap.y * g + pad
            x2 = (cap.x + cap.w) * g - pad
            y2 = (cap.y + cap.h) * g - pad
            base_color = cap.spec.get("color") or theme["cap"]
            if cap.locked:
                fill = theme["cap_locked"]
            elif cap.active:
                fill = theme["cap_active"]
            elif cap.hovered:
                fill = theme["cap_hover"]
            else:
                fill = base_color
            cap.rect = self.create_rectangle(
                x1, y1, x2, y2,
                fill=fill, outline=theme["outline"], width=1,
            )
            label = cap.spec.get("label", "")
            cap.text_id = self.create_text(
                (x1 + x2) / 2, (y1 + y2) / 2,
                text=label, fill=theme["text"],
                font=("Segoe UI", max(8, int(g * 0.32)), "bold"),
                width=(x2 - x1) - 6,
            )
            if self.editing and cap is self._selected:
                self.create_rectangle(x1, y1, x2, y2, outline="#ff9500", width=2)

    # ---- helpers ----------------------------------------------------------

    def _cap_at(self, px, py):
        if not self.layout:
            return None
        g = self.layout.get("grid", 36)
        for cap in reversed(self.caps):
            x1 = cap.x * g
            y1 = cap.y * g
            x2 = (cap.x + cap.w) * g
            y2 = (cap.y + cap.h) * g
            if x1 <= px <= x2 and y1 <= py <= y2:
                return cap
        return None

    def _grid_xy(self, px, py):
        g = self.layout.get("grid", 36)
        return px // g, py // g

    # ---- input ------------------------------------------------------------

    def _on_motion(self, e):
        cap = self._cap_at(e.x, e.y)
        changed = False
        for c in self.caps:
            target = c is cap
            if c.hovered != target:
                c.hovered = target
                changed = True
        if changed:
            self.redraw()

    def _on_press(self, e):
        cap = self._cap_at(e.x, e.y)
        if self.editing:
            self._selected = cap
            if cap:
                self._drag = ("move", cap, e.x, e.y, cap.x, cap.y)
            self.redraw()
            self.app.refresh_inspector()
            return
        if cap is None:
            return

        # Software double-click detection. Tk's native <Double-Button-1>
        # would steal the second <Button-1> event and cause dropped strokes
        # during fast typing, so we fire on every press and detect doubles
        # ourselves using the X event timestamp.
        now = getattr(e, "time", 0) or int(time.time() * 1000)
        is_double = (
            cap is self._last_press_cap
            and (now - self._last_press_time) <= self._double_click_ms
        )
        # Reset so a triple-click doesn't repeatedly count as "double".
        self._last_press_time = 0 if is_double else now
        self._last_press_cap = None if is_double else cap

        if is_double and cap.is_modifier and cap.is_toggle:
            # The first click already toggled the lock via _fire_key /
            # _toggle_lock. Force the lock to ON on a real double-click so
            # the documented "double-click to lock" gesture is idempotent
            # rather than re-toggling back to OFF.
            vk_name = cap.spec.get("vk")
            if vk_name and vk_name not in self.locked_modifiers:
                self._toggle_lock(cap)
            return

        cap.active = True
        self.redraw()
        self._fire_key(cap, down=True)

    def _on_drag(self, e):
        if self.editing and self._drag:
            mode, cap, sx, sy, ox, oy = self._drag
            g = self.layout.get("grid", 36)
            dx = (e.x - sx) // g
            dy = (e.y - sy) // g
            if mode == "move":
                cap.x = max(0, ox + dx)
                cap.y = max(0, oy + dy)
                cap.spec["x"] = cap.x
                cap.spec["y"] = cap.y
                self.redraw()

    def _on_release(self, e):
        if self.editing:
            self._drag = None
            return
        for cap in self.caps:
            if cap.active:
                cap.active = False
                self._fire_key(cap, down=False)
        self.redraw()

    def _on_right_click(self, e):
        if not self.editing:
            return
        cap = self._cap_at(e.x, e.y)
        if cap is None:
            return
        self._selected = cap
        self.app.edit_selected_cap()

    def _on_double(self, e):
        # Kept for backward compatibility but no longer wired up: the
        # <Double-Button-1> binding was removed because it suppressed the
        # second <Button-1> press of fast click bursts and dropped keystrokes.
        # Double-click handling now lives in _on_press (software-detected).
        return

    # ---- key dispatch -----------------------------------------------------

    def _toggle_lock(self, cap):
        vk_name = cap.spec.get("vk")
        if vk_name in self.locked_modifiers:
            self.locked_modifiers.discard(vk_name)
            cap.locked = False
            send_vk(resolve_vk(vk_name), False)
        else:
            self.locked_modifiers.add(vk_name)
            cap.locked = True
            send_vk(resolve_vk(vk_name), True)
        self.redraw()

    def _get_char_from_vk(self, vk_name):
        """Convert a VK name to the character it produces."""
        if not vk_name:
            return None
        vk = resolve_vk(vk_name)
        if vk is None:
            return None
        # Single letter keys
        if len(vk_name) == 1 and vk_name.isalpha():
            return vk_name.lower()
        # Number keys
        if vk_name in "0123456789":
            return vk_name
        # Punctuation keys - map to their character
        punct_map = {
            "Semicolon": ";", "Equal": "=", "Comma": ",", "Minus": "-",
            "Period": ".", "Slash": "/", "Backtick": "`", "LBracket": "[",
            "Backslash": "\\", "RBracket": "]", "Quote": "'",
            ";": ";", "=": "=", ",": ",", "-": "-", ".": ".",
            "/": "/", "`": "`", "[": "[", "\\": "\\", "]": "]", "'": "'",
        }
        if vk_name in punct_map:
            return punct_map[vk_name]
        # Space
        if vk_name == "Space":
            return " "
        return None

    def _check_stroke_translations(self, char):
        """Check if buffer + new char matches any translation pattern."""
        translations = self.app.config_data.get("keystroke_translations", {})
        if not translations:
            return None
            
        test_buffer = self._stroke_buffer + char
        
        # Check for exact matches - sort by length (longest first) to prioritize longer patterns
        for pattern, target in sorted(translations.items(), key=lambda x: -len(x[0])):
            if test_buffer.endswith(pattern):
                return pattern, target
                
        return None

    def _fire_key(self, cap, down):
        spec = cap.spec
        
        # Get character representation for stroke tracking
        char = None
        if "text" in spec and down:
            # Text keys - don't track for translations (they output directly)
            type_string(spec["text"])
            self._auto_release_modifiers()
            self._stroke_buffer = ""  # Clear buffer after text
            return
        if "macro" in spec and down:
            self._run_macro(spec["macro"])
            self._stroke_buffer = ""  # Clear buffer after macro
            return
            
        vk_name = spec.get("vk")
        char = self._get_char_from_vk(vk_name)
        
        # Check for stroke translation BEFORE sending the keystroke
        if down and char:
            # Check if this character completes a translation pattern
            translation = self._check_stroke_translations(char)
            if translation:
                pattern, target = translation
                # Send backspaces to delete the pattern characters (minus 1 because current char hasn't been output yet)
                for _ in range(len(pattern) - 1):
                    tap_vk(0x08)  # Backspace VK
                    time.sleep(0.005)
                # Type the target character
                type_string(target)
                # Clear the buffer
                self._stroke_buffer = ""
                return
            else:
                # Add to buffer (with length limit)
                self._stroke_buffer += char
                if len(self._stroke_buffer) > self._stroke_max_len:
                    self._stroke_buffer = self._stroke_buffer[-self._stroke_max_len:]
        
        # Clear buffer on modifier keys or special keys
        if down and vk_name in ("Enter", "Return", "Tab", "Backspace", "Esc", "Escape",
                                 "Space", "Left", "Right", "Up", "Down", "Home", "End",
                                 "PgUp", "PgDn", "Insert", "Delete"):
            self._stroke_buffer = ""
        
        # Normal key processing
        vk = resolve_vk(vk_name)
        if vk is None:
            return
        if cap.is_modifier and cap.is_toggle:
            if down:
                self._toggle_lock(cap)
            return
        if down:
            mods = list(self.held_modifiers)
            for m in mods:
                send_vk(resolve_vk(m), True)
            send_vk(vk, True)
        else:
            send_vk(vk, False)
            if not cap.is_modifier:
                self._auto_release_modifiers()

    def _auto_release_modifiers(self):
        for m in list(self.held_modifiers):
            if m in self.locked_modifiers:
                continue
            send_vk(resolve_vk(m), False)
            self.held_modifiers.discard(m)
        self.redraw()

    def _run_macro(self, steps):
        for step in steps:
            mods = step.get("mods", [])
            vk = resolve_vk(step.get("vk"))
            if vk is None and "text" in step:
                type_string(step["text"])
                continue
            for m in mods:
                send_vk(resolve_vk(m), True)
            if vk is not None:
                tap_vk(vk, hold_ms=step.get("hold_ms", 0))
            for m in reversed(mods):
                send_vk(resolve_vk(m), False)
            if "delay_ms" in step:
                time.sleep(step["delay_ms"] / 1000.0)

    # ---- editor add / delete ---------------------------------------------

    def add_blank_cap(self, gx, gy):
        spec = {"x": gx, "y": gy, "w": 1, "h": 1, "label": "?", "vk": "Space"}
        self.layout.setdefault("keys", []).append(spec)
        cap = KeyCap(spec)
        self.caps.append(cap)
        self._selected = cap
        self.redraw()

    def delete_selected(self):
        if self._selected is None:
            return
        self.layout["keys"].remove(self._selected.spec)
        self.caps.remove(self._selected)
        self._selected = None
        self.redraw()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        write_default_layouts()
        self.config_data = load_config()
        self._build_ui()
        self._apply_window_settings()
        self._load_last_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._install_noactivate)

    def _install_noactivate(self):
        if not IS_WINDOWS:
            return
        try:
            hwnd = self.winfo_id()
            make_window_non_activating(hwnd)
        except Exception:
            pass

    def _reapply_noactivate(self):
        self.after(20, self._install_noactivate)

    # ---------------- UI ----------------

    def _build_ui(self):
        theme = THEMES[self.config_data.get("theme", "dark")]
        self.configure(bg=theme["bg"])

        toolbar = tk.Frame(self, bg=theme["bg"])
        toolbar.pack(side="top", fill="x", padx=4, pady=4)

        self.layout_var = tk.StringVar()
        self.layout_combo = ttk.Combobox(
            toolbar, textvariable=self.layout_var, state="readonly", width=24
        )
        self._refresh_layout_list()
        self.layout_combo.bind("<<ComboboxSelected>>", lambda e: self._switch_layout())
        self.layout_combo.pack(side="left", padx=4)

        def btn(text, cmd):
            return tk.Button(
                toolbar, text=text, command=cmd, relief="flat",
                bg=theme["panel"], fg=theme["text"],
                activebackground=theme["cap_hover"], padx=8, pady=2,
            )

        btn("New", self._new_layout).pack(side="left", padx=2)
        btn("Save", self._save_current).pack(side="left", padx=2)
        btn("Save As…", self._save_as).pack(side="left", padx=2)
        btn("Import…", self._import).pack(side="left", padx=2)
        btn("Edit", self._toggle_edit).pack(side="left", padx=8)
        btn("Theme", self._toggle_theme).pack(side="left", padx=2)
        btn("Translations", self._open_translations).pack(side="left", padx=2)
        btn("?", self._show_help).pack(side="right", padx=2)

        self.opacity_var = tk.DoubleVar(value=self.config_data.get("opacity", 0.95))
        ttk.Scale(toolbar, from_=0.4, to=1.0, variable=self.opacity_var,
                  orient="horizontal", length=110,
                  command=lambda v: self._apply_opacity()).pack(side="right", padx=4)
        tk.Label(toolbar, text="Opacity", bg=theme["bg"],
                 fg=theme["muted"]).pack(side="right")

        self.top_var = tk.BooleanVar(value=self.config_data.get("always_on_top", True))
        tk.Checkbutton(toolbar, text="On top", variable=self.top_var,
                       bg=theme["bg"], fg=theme["text"],
                       selectcolor=theme["panel"], activebackground=theme["bg"],
                       command=self._apply_topmost).pack(side="right", padx=4)

        body = tk.Frame(self, bg=theme["bg"])
        body.pack(fill="both", expand=True)

        self.canvas = KeyboardCanvas(body, self, bg=theme["panel"], takefocus=0)
        self.canvas.pack(side="left", padx=4, pady=4)

        self.inspector = tk.Frame(body, bg=theme["panel"], width=240)
        self.inspector.pack(side="right", fill="y", padx=4, pady=4)
        self.inspector.pack_forget()

        self.status = tk.Label(self, anchor="w", bg=theme["bg"],
                               fg=theme["muted"], padx=6)
        self.status.pack(side="bottom", fill="x")
        self._set_status("Ready")

    def _refresh_layout_list(self):
        files = list_layout_files()
        self.layout_combo["values"] = files
        if self.config_data.get("last_layout") in files:
            self.layout_var.set(self.config_data["last_layout"])
        elif files:
            self.layout_var.set(files[0])

    def _set_status(self, msg):
        self.status.config(text=msg)

    # ---------------- window state ----------------

    def _apply_window_settings(self):
        self._apply_topmost()
        self._apply_opacity()
        win = self.config_data.get("window", {})
        x = win.get("x", 80); y = win.get("y", 80)
        self.geometry(f"+{x}+{y}")

    def _apply_topmost(self):
        flag = bool(self.top_var.get())
        self.attributes("-topmost", flag)
        self.config_data["always_on_top"] = flag
        self._reapply_noactivate()

    def _apply_opacity(self):
        v = float(self.opacity_var.get())
        try:
            self.attributes("-alpha", v)
        except tk.TclError:
            pass
        self.config_data["opacity"] = round(v, 3)

    def _toggle_theme(self):
        cur = self.config_data.get("theme", "dark")
        self.config_data["theme"] = "light" if cur == "dark" else "dark"
        theme = THEMES[self.config_data["theme"]]
        self.configure(bg=theme["bg"])
        for child in self.winfo_children():
            try:
                child.configure(bg=theme["bg"])
            except tk.TclError:
                pass
        self.canvas.redraw()

    def _on_close(self):
        # Uninstall keyboard hook before closing
        _uninstall_keyboard_hook()
        try:
            geom = self.geometry()
            x = int(geom.split("+")[1]); y = int(geom.split("+")[2])
            self.config_data["window"] = {"x": x, "y": y}
        except Exception:
            pass
        save_config(self.config_data)
        self.destroy()

    # ---------------- translations ----------------

    def _open_translations(self):
        """Open the keystroke translations editor dialog."""
        TranslationsDialog(self, self)

    # ---------------- layouts ----------------

    def _load_last_layout(self):
        fn = self.layout_var.get()
        if not fn:
            return
        try:
            layout = load_layout_file(fn)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not load layout:\n{e}")
            return
        self.canvas.set_layout(layout)
        self._set_status(f"Loaded layout: {layout.get('name', fn)}")
        self.config_data["last_layout"] = fn

    def _switch_layout(self):
        self._load_last_layout()

    def _new_layout(self):
        name = simpledialog.askstring(APP_NAME, "Layout name:", parent=self)
        if not name:
            return
        layout = {"name": name, "grid": 40, "cols": 10, "rows": 4, "keys": []}
        fn = f"{name}.json"
        save_layout_file(fn, layout)
        self._refresh_layout_list()
        self.layout_var.set(fn)
        self._switch_layout()
        if not self.canvas.editing:
            self._toggle_edit()

    def _save_current(self):
        fn = self.layout_var.get()
        if not fn or not self.canvas.layout:
            return
        save_layout_file(fn, self.canvas.layout)
        self._set_status(f"Saved {fn}")

    def _save_as(self):
        if not self.canvas.layout:
            return
        path = filedialog.asksaveasfilename(
            initialdir=LAYOUT_DIR, defaultextension=".json",
            filetypes=[("JSON layout", "*.json")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.canvas.layout, f, indent=2)
        if os.path.dirname(path) == LAYOUT_DIR:
            self._refresh_layout_list()
            self.layout_var.set(os.path.basename(path))
        self._set_status(f"Saved {os.path.basename(path)}")

    def _import(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON layout", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                layout = json.load(f)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Bad JSON: {e}")
            return
        fn = os.path.basename(path)
        save_layout_file(fn, layout)
        self._refresh_layout_list()
        self.layout_var.set(fn)
        self._switch_layout()

    # ---------------- editor / inspector ----------------

    def _toggle_edit(self):
        self.canvas.editing = not self.canvas.editing
        if self.canvas.editing:
            self.inspector.pack(side="right", fill="y", padx=4, pady=4)
            self.refresh_inspector()
            self._set_status("Edit mode ON – drag caps, double/right-click to edit, "
                             "or use the Inspector. Save when done.")
        else:
            self.inspector.pack_forget()
            self._set_status("Edit mode OFF")
        self.canvas.redraw()

    def refresh_inspector(self):
        for w in self.inspector.winfo_children():
            w.destroy()
        theme = THEMES[self.config_data.get("theme", "dark")]
        L = self.canvas.layout or {}

        def lab(t, **kw):
            return tk.Label(self.inspector, text=t, bg=theme["panel"],
                            fg=theme["text"], anchor="w", **kw)

        lab("Layout settings", font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(2, 4))

        for prop, label, cast in (
            ("name", "Name", str), ("grid", "Grid (px)", int),
            ("cols", "Cols", int), ("rows", "Rows", int),
        ):
            row = tk.Frame(self.inspector, bg=theme["panel"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, width=10, anchor="w",
                     bg=theme["panel"], fg=theme["muted"]).pack(side="left")
            var = tk.StringVar(value=str(L.get(prop, "")))
            ent = tk.Entry(row, textvariable=var, width=14)
            ent.pack(side="left", fill="x", expand=True)
            def commit(p=prop, v=var, c=cast):
                try:
                    self.canvas.layout[p] = c(v.get())
                    self.canvas._resize_canvas()
                    self.canvas.redraw()
                except Exception:
                    pass
            ent.bind("<FocusOut>", lambda e, c=commit: c())
            ent.bind("<Return>", lambda e, c=commit: c())

        lab("").pack()
        lab("Selected key", font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(2, 4))

        sel = self.canvas._selected
        if sel is None:
            lab("(click a key to edit)", fg=theme["muted"]).pack(fill="x")
        else:
            for prop, label in (
                ("label", "Label"), ("vk", "VK name"),
                ("x", "X"), ("y", "Y"), ("w", "W"), ("h", "H"),
                ("text", "Type text"), ("color", "Colour #hex"),
            ):
                row = tk.Frame(self.inspector, bg=theme["panel"])
                row.pack(fill="x", pady=1)
                tk.Label(row, text=label, width=10, anchor="w",
                         bg=theme["panel"], fg=theme["muted"]).pack(side="left")
                var = tk.StringVar(value=str(sel.spec.get(prop, "")))
                ent = tk.Entry(row, textvariable=var, width=14)
                ent.pack(side="left", fill="x", expand=True)
                def commit(p=prop, v=var, s=sel):
                    val = v.get()
                    if p in ("x", "y", "w", "h"):
                        try:
                            s.spec[p] = int(val)
                        except ValueError:
                            return
                        s.x = s.spec["x"]; s.y = s.spec["y"]
                        s.w = max(1, s.spec.get("w", 1))
                        s.h = max(1, s.spec.get("h", 1))
                    elif val == "":
                        s.spec.pop(p, None)
                    else:
                        s.spec[p] = val
                    self.canvas.redraw()
                ent.bind("<FocusOut>", lambda e, c=commit: c())
                ent.bind("<Return>", lambda e, c=commit: c())

            row = tk.Frame(self.inspector, bg=theme["panel"])
            row.pack(fill="x", pady=4)
            tk.Label(row, text="Toggle", width=10, anchor="w",
                     bg=theme["panel"], fg=theme["muted"]).pack(side="left")
            tog = tk.BooleanVar(value=bool(sel.spec.get("toggle", False)))
            def commit_tog():
                sel.spec["toggle"] = bool(tog.get())
            tk.Checkbutton(row, variable=tog, bg=theme["panel"],
                           command=commit_tog,
                           selectcolor=theme["panel"]).pack(side="left")

            tk.Button(self.inspector, text="Pick colour…",
                      command=lambda: self._pick_color(sel)).pack(fill="x", pady=2)
            tk.Button(self.inspector, text="Delete key",
                      command=self._delete_key).pack(fill="x", pady=2)

        tk.Button(self.inspector, text="Add key at (0,0)",
                  command=lambda: self.canvas.add_blank_cap(0, 0)).pack(
            fill="x", pady=(12, 2))

    def _pick_color(self, cap):
        col = colorchooser.askcolor(initialcolor=cap.spec.get("color", "#3a3a42"))[1]
        if col:
            cap.spec["color"] = col
            self.canvas.redraw()

    def _delete_key(self):
        self.canvas.delete_selected()
        self.refresh_inspector()

    def edit_selected_cap(self):
        self.refresh_inspector()

    # ---------------- help ----------------

    def _show_help(self):
        msg = (
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Click a cap to send a keystroke. Hold to repeat (OS auto-repeat).\n"
            "Double-click modifier caps (Shift / Ctrl / Alt / Win marked Toggle)\n"
            "to lock them ON until you tap them again.\n\n"
            "Edit mode: drag caps to reposition; right-click or use the\n"
            "Inspector to change label, vk, size, type-text, macro, colour.\n\n"
            "Keystroke Translations: define stroke patterns (like \"'''\")\n"
            "that auto-convert to target characters (like \"a\").\n\n"
            "Layouts live in:\n"
            f"   {LAYOUT_DIR}\n\n"
            "They are plain JSON – copy your favourites onto another PC and\n"
            "PortaKeys will pick them up automatically.\n\n"
            "Macros are JSON arrays:\n"
            '   [{"vk":"C","mods":["Ctrl"]}, {"vk":"Tab","mods":["Alt"]}]\n'
            'Or a "text" field on a key types a literal string.\n'
        )
        messagebox.showinfo(APP_NAME, msg)


def main():
    if not IS_WINDOWS:
        print("PortaKeys is Windows-only (uses SendInput). "
              "Running anyway in preview-mode (no keys will be sent).")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
