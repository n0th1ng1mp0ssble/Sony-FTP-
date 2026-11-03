"""配色、字体与主题。"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont

# --------------------------------------------------------------------------- 调色板

LIGHT = {
    "bg": "#f5f6f8",
    "surface": "#ffffff",
    "surface2": "#eef0f4",
    "border": "#e2e5ea",
    "border_strong": "#d3d7de",
    "text": "#16181d",
    "text2": "#5f6570",
    "text3": "#9aa0aa",
    "accent": "#2563eb",
    "accent_text": "#ffffff",
    "accent_soft": "#e8efff",
    "ok": "#16a34a",
    "ok_soft": "#e7f6ec",
    "warn": "#d97706",
    "warn_soft": "#fdf3e3",
    "danger": "#dc2626",
    "danger_soft": "#fdeaea",
    "thumb_bg": "#eceef2",
    "track": "#e7e9ee",
}

DARK = {
    "bg": "#121417",
    "surface": "#1a1d22",
    "surface2": "#22262d",
    "border": "#2a2f37",
    "border_strong": "#343a44",
    "text": "#f1f3f6",
    "text2": "#a3aab5",
    "text3": "#737a85",
    "accent": "#4f8ef7",
    "accent_text": "#ffffff",
    "accent_soft": "#1d2a44",
    "ok": "#3ecf7a",
    "ok_soft": "#17301f",
    "warn": "#f2a53c",
    "warn_soft": "#33260f",
    "danger": "#f27272",
    "danger_soft": "#3a1c1c",
    "thumb_bg": "#20242b",
    "track": "#2a2f37",
}

PALETTES = {"light": LIGHT, "dark": DARK}


def detect_dark_theme() -> bool:
    """Windows 10/11 是否处于深色模式。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except Exception:
        return False


def resolve_theme(theme: str) -> str:
    if theme == "auto":
        return "dark" if detect_dark_theme() else "light"
    return theme if theme in PALETTES else "light"


# --------------------------------------------------------------------------- 字体

_CJK_CANDIDATES = ["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                   "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC",
                   "Segoe UI", "Arial"]
_MONO_CANDIDATES = ["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"]


def pick_family(root: tk.Misc, numeric: bool = False) -> str:
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        families = set()
    for name in (_MONO_CANDIDATES if numeric else _CJK_CANDIDATES):
        if name in families:
            return name
    return "TkDefaultFont"


class Fonts:
    """按缩放系数生成各类字体。"""

    def __init__(self, root: tk.Misc, scale: float = 1.0):
        self.scale = scale
        self.family = pick_family(root)
        self.mono = pick_family(root, numeric=True)

    def _size(self, px: float) -> int:
        return max(8, int(round(px * self.scale)))

    def get(self, name: str) -> tuple:
        s = self._size
        table = {
            "display": (self.family, s(26), "bold"),
            "title": (self.family, s(17), "bold"),
            "h2": (self.family, s(13), "bold"),
            "body": (self.family, s(11), "normal"),
            "body_bold": (self.family, s(11), "bold"),
            "small": (self.family, s(10), "normal"),
            "tiny": (self.family, s(9), "normal"),
            "mono": (self.mono, s(10), "normal"),
            "num": (self.mono, s(13), "bold"),
            "big_num": (self.mono, s(22), "bold"),
        }
        return table.get(name, table["body"])
