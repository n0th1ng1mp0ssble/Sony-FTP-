"""自绘控件：圆角卡片、按钮、进度条、开关、分段选择器、徽标、图像适配。

用 Canvas 自绘保证在 Windows 上风格统一（ttk 原生控件无法完整换色）。
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

try:
    from PIL import Image, ImageTk
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False


# --------------------------------------------------------------------------- 圆角矩形

def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r: float, **kw):
    """在 Canvas 上画圆角矩形（用平滑多边形近似）。"""
    r = max(0.0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    pts = [
        x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
        x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2,
        x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r,
        x1, y1 + r, x1, y1 + r, x1, y1, x1 + r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, splinesteps=24, **kw)


# --------------------------------------------------------------------------- 图像

def fit_image(path: str, box_w: int, box_h: int, radius: int = 0,
              bg: str = "#e4e7ec") -> Optional["Image.Image"]:
    """把图片缩放进 box 并居中到 box 大小的画布上（返回 PIL Image）。"""
    if not _PIL:
        return None
    from ..imaging import load_image, placeholder
    import os
    box_w, box_h = max(1, int(box_w)), max(1, int(box_h))
    img = load_image(path, max_side=max(box_w, box_h) * 2)
    if img is None:
        ext = os.path.splitext(path)[1].lower()
        reason = "RAW / HEIF / 视频 无内嵌预览" if ext in (".arw", ".dng", ".heic", ".heif", ".hif",
                                                         ".mp4", ".mts", ".m2ts", ".mov") else "无法解码该文件"
        img = placeholder(box_h, box_w, os.path.basename(path), reason)
    w, h = img.size
    scale = min(box_w / w, box_h / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    canvas = Image.new("RGB", (box_w, box_h), bg)
    ox, oy = (box_w - nw) // 2, (box_h - nh) // 2
    canvas.paste(img, (ox, oy))
    if radius > 0:
        from PIL import ImageDraw
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, 0, box_w - 1, oy], fill=bg)
        d.rectangle([0, oy + nh, box_w - 1, box_h - 1], fill=bg)
        d.rectangle([0, 0, ox - 1, box_h - 1], fill=bg)
        d.rectangle([ox + nw, 0, box_w - 1, box_h - 1], fill=bg)
    return canvas


class ImageLabel(tk.Label):
    """自适应尺寸显示图片的 Label（窗口缩放时重新渲染）。"""

    def __init__(self, master, bg: str, radius: int = 0, **kw):
        super().__init__(master, bg=bg, bd=0, highlightthickness=0, **kw)
        self._path: Optional[str] = None
        self._photo = None
        self._bg = bg
        self._radius = radius
        self._pending: Optional[str] = None
        self.bind("<Configure>", self._on_configure)

    def set_image(self, path: Optional[str], immediate: bool = False) -> None:
        self._path = path
        if immediate:
            self._render()
        else:
            if self._pending is None:
                self._pending = self.after(40, self._flush)

    def _flush(self) -> None:
        self._pending = None
        self._render()

    def _on_configure(self, _evt=None) -> None:
        if not self._pending:
            self._pending = self.after(120, self._flush)

    def _render(self) -> None:
        if not _PIL:
            return
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            return
        if not self._path:
            self.configure(image="")
            self._photo = None
            return
        try:
            # 内缩 10px，让照片周围留出一圈空白，看起来更干净
            pad = 10
            img = fit_image(self._path, max(8, w - pad * 2), max(8, h - pad * 2), self._radius, self._bg)
            if img is None:
                return
            self._photo = ImageTk.PhotoImage(img)
            self.configure(image=self._photo)
        except Exception:
            pass


# --------------------------------------------------------------------------- 按钮

class Button(tk.Canvas):
    """扁平圆角按钮，支持 primary / secondary / ghost / danger 样式。"""

    KINDS = ("primary", "secondary", "ghost", "danger")

    def __init__(self, master, text: str, command: Optional[Callable] = None,
                 kind: str = "secondary", palette: Optional[dict] = None, fonts=None,
                 padx: int = 16, pady: int = 8, font_key: str = "body_bold", radius: int = 8,
                 icon: str = "", **kw):
        self.palette = palette or {}
        self.kind = kind if kind in self.KINDS else "secondary"
        self.font = fonts.get(font_key) if fonts else ("Segoe UI", 11, "bold")
        self.text = text
        self.icon = icon
        self.command = command
        self._radius = radius
        self._hover = False
        self._pressed = False
        self._enabled = True
        self._padx = padx
        self._pady = pady
        self.fixed_width = 0
        super().__init__(master, bd=0, highlightthickness=0, **kw)
        self._label = self.create_text(0, 0, anchor="center", font=self.font, text=self._text())
        self._measure()
        self._resize()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.configure(cursor="hand2")
        self._draw()

    def _text(self) -> str:
        return f"{self.icon}  {self.text}" if self.icon else self.text

    def _measure(self) -> None:
        try:
            import tkinter.font as tkfont
            f = tkfont.Font(font=self.font)
            tw = f.measure(self._text())
            th = f.metrics("linespace")
        except Exception:
            tw, th = len(self.text) * 8, 16
        self._bw = tw + self._padx * 2
        if self.fixed_width:
            self._bw = max(self._bw, self.fixed_width)
        self._h = th + self._pady * 2

    def set_text(self, text: str) -> None:
        if text == self.text:
            return
        self.text = text
        self.itemconfigure(self._label, text=self._text())
        self._measure()
        self._resize()
        self._draw()

    def _resize(self) -> None:
        """按像素设置画布尺寸（Tk 的 Canvas width/height 选项本身就是像素）。"""
        try:
            self.configure(width=int(self._bw), height=int(self._h))
        except Exception:
            pass

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)
        self.configure(cursor="hand2" if on else "arrow")
        self._draw()

    def _colors(self) -> tuple[str, str, str]:
        p = self.palette
        kind = self.kind
        if not self._enabled:
            return p.get("surface2", "#eee"), p.get("text3", "#999"), p.get("border", "#ddd")
        if kind == "primary":
            bg = p.get("accent", "#2563eb")
            fg = p.get("accent_text", "#fff")
            border = bg
        elif kind == "danger":
            bg = p.get("danger_soft", "#fee")
            fg = p.get("danger", "#c00")
            border = p.get("danger", "#c00")
        elif kind == "ghost":
            bg = p.get("bg", "#f5f5f5")
            fg = p.get("text2", "#555")
            border = bg
        else:
            bg = p.get("surface", "#fff")
            fg = p.get("text", "#111")
            border = p.get("border_strong", "#ccc")
        if self._hover:
            if kind == "primary":
                bg = _shade(bg, -14)
            elif kind == "danger":
                bg = _shade(bg, -8)
            else:
                bg = _shade(bg, -10 if self._pressed else -5)
        elif self._pressed:
            bg = _shade(bg, -12)
        return bg, fg, border

    def _draw(self) -> None:
        self.delete("shape")
        bg, fg, border = self._colors()
        w, h = self._bw, self._h
        rounded_rect(self, 1, 1, w - 1, h - 1, self._radius, fill=bg, outline=border,
                     width=1, tags="shape")
        self.itemconfigure(self._label, fill=fg)
        self.coords(self._label, w / 2, h / 2)
        self.tag_lower("shape")

    def _on_enter(self, _e=None) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _e=None) -> None:
        self._hover = self._pressed = False
        self._draw()

    def _on_press(self, _e=None) -> None:
        if not self._enabled:
            return
        self._pressed = True
        self._draw()

    def _on_release(self, e=None) -> None:
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and self._enabled and self.command:
            try:
                self.command()
            except Exception:
                import logging
                logging.getLogger("shutterdrop.ui").exception("按钮回调出错")


def _shade(hex_color: str, amount: int) -> str:
    """把颜色调亮/调暗（amount 为 -100..100）。"""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if amount >= 0:
            r, g, b = (int(c + (255 - c) * amount / 100.0) for c in (r, g, b))
        else:
            r, g, b = (int(c * (1 + amount / 100.0)) for c in (r, g, b))
        return "#%02x%02x%02x" % (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    except Exception:
        return hex_color


# --------------------------------------------------------------------------- 进度条

class ProgressBar(tk.Canvas):
    """细长的进度条（也用于倒计时）。"""

    def __init__(self, master, palette: dict, height: int = 8, color: str = "accent",
                 radius: Optional[int] = None, **kw):
        self.palette = palette
        self.height = height
        self.color_key = color
        kw.setdefault("bg", palette.get("surface", "#fff"))
        super().__init__(master, bd=0, highlightthickness=0, **kw)
        self.configure(width=40, height=height)
        self._value = 0.0
        self._radius = radius if radius is not None else height // 2
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if abs(value - self._value) < 0.002 and value not in (0.0, 1.0):
            return
        self._value = value
        self._draw()

    def set_color(self, key: str) -> None:
        if key != self.color_key:
            self.color_key = key
            self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.height
        if w <= 2:
            return
        rounded_rect(self, 0, 0, w, h, self._radius, fill=self.palette.get("track", "#e7e9ee"),
                     outline="")
        fw = w * self._value
        if fw > 1:
            rounded_rect(self, 0, 0, max(fw, h), h, self._radius,
                         fill=self.palette.get(self.color_key, "#2563eb"), outline="")


# --------------------------------------------------------------------------- 开关

class Switch(tk.Canvas):
    """iOS 风格开关。"""

    def __init__(self, master, palette: dict, value: bool, command: Optional[Callable] = None,
                 width: int = 44, height: int = 24, **kw):
        self.palette = palette
        self._value = bool(value)
        self.command = command
        self._bw, self._h = width, height
        kw.setdefault("bg", palette.get("surface", "#fff"))
        super().__init__(master, bd=0, highlightthickness=0, cursor="hand2", **kw)
        self.configure(width=width, height=height)
        self.bind("<Button-1>", self._toggle)
        self._draw()

    @property
    def value(self) -> bool:
        return self._value

    def set(self, value: bool, notify: bool = False) -> None:
        self._value = bool(value)
        self._draw()
        if notify and self.command:
            self.command(self._value)

    def _toggle(self, _e=None) -> None:
        self._value = not self._value
        self._draw()
        if self.command:
            self.command(self._value)

    def _draw(self) -> None:
        self.delete("all")
        w, h = self._bw, self._h
        r = h / 2
        bg = self.palette.get("accent", "#2563eb") if self._value else self.palette.get("border_strong", "#ccc")
        rounded_rect(self, 0, 0, w, h, r, fill=bg, outline="")
        pad = 3
        d = h - pad * 2
        x = w - pad - d if self._value else pad
        self.create_oval(x, pad, x + d, pad + d, fill="#ffffff", outline="")


# --------------------------------------------------------------------------- 分段选择

class Segmented(tk.Canvas):
    """分段选择器：options=[(value, label), ...]。"""

    def __init__(self, master, palette: dict, options: list, value, command: Optional[Callable] = None,
                 font=None, height: int = 32, **kw):
        self.palette = palette
        self.options = list(options)
        self._value = value
        self.command = command
        self.font = font or ("Segoe UI", 10)
        self._h = height
        self._hover = -1
        kw.setdefault("bg", palette.get("surface", "#fff"))
        super().__init__(master, bd=0, highlightthickness=0, cursor="hand2", **kw)
        self.configure(width=kw.get("width", 200), height=height)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: self._set_hover(-1))
        self.bind("<Button-1>", self._on_click)

    @property
    def value(self):
        return self._value

    def set(self, value, notify: bool = False) -> None:
        self._value = value
        self._draw()
        if notify and self.command:
            self.command(value)

    def _segments(self):
        w = self.winfo_width()
        n = max(1, len(self.options))
        seg = (w - 4) / n
        return seg

    def _on_motion(self, e) -> None:
        idx = int(max(0, min(len(self.options) - 1, (e.x - 2) // max(1, self._segments()))))
        self._set_hover(idx)

    def _set_hover(self, idx: int) -> None:
        if idx != self._hover:
            self._hover = idx
            self._draw()

    def _on_click(self, e) -> None:
        idx = int(max(0, min(len(self.options) - 1, (e.x - 2) // max(1, self._segments()))))
        val = self.options[idx][0]
        if val != self._value:
            self._value = val
            self._draw()
            if self.command:
                self.command(val)

    def _draw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self._h
        if w <= 4:
            return
        rounded_rect(self, 0, 0, w, h, h / 2, fill=self.palette.get("surface2", "#eef"), outline="")
        seg = self._segments()
        for i, (val, label) in enumerate(self.options):
            x1 = 2 + i * seg
            x2 = x1 + seg
            if val == self._value:
                rounded_rect(self, x1 + 1, 3, x2 - 1, h - 3, (h - 6) / 2,
                             fill=self.palette.get("surface", "#fff"),
                             outline=self.palette.get("border", "#ddd"))
                fg = self.palette.get("text", "#111")
            elif i == self._hover:
                fg = self.palette.get("text2", "#555")
            else:
                fg = self.palette.get("text2", "#666")
            self.create_text((x1 + x2) / 2, h / 2, text=label, fill=fg, font=self.font)


# --------------------------------------------------------------------------- 徽标（状态胶囊）

class Badge(tk.Canvas):
    def __init__(self, master, palette: dict, text: str = "", color_key: str = "text2",
                 dot: bool = True, font=None, height: int = 26, **kw):
        self.palette = palette
        self.color_key = color_key
        self.text = text
        self.dot = dot
        self.font = font or ("Segoe UI", 10)
        self._h = height
        kw.setdefault("bg", palette.get("surface", "#fff"))
        super().__init__(master, height=height, bd=0, highlightthickness=0, **kw)
        # 注意：self._w 是 tkinter 内部的 Tcl 窗口名，千万不要给 Canvas 实例起这个属性名
        self._bw = 120

    def set(self, text: str, color_key: str) -> None:
        self.text = text
        self.color_key = color_key
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        import tkinter.font as tkfont
        try:
            f = tkfont.Font(font=self.font)
            tw = f.measure(self.text)
            ch = max(1, f.measure("0"))
        except Exception:
            tw, ch = len(self.text) * 8, 8
        dot_w = 14 if self.dot else 6
        w = tw + dot_w + 20
        h = self._h
        self._bw = w
        bg = self.palette.get(self.color_key + "_soft", self.palette.get("surface2", "#eee"))
        fg = self.palette.get(self.color_key, self.palette.get("text2", "#555"))
        rounded_rect(self, 0, 0, w, h, h / 2, fill=bg, outline="")
        x = 11
        if self.dot:
            cy = h / 2
            self.create_oval(x, cy - 4, x + 8, cy + 4, fill=fg, outline="")
            x += dot_w
        self.create_text(x, h / 2, anchor="w", text=self.text, fill=fg, font=self.font)
        # 按像素设置画布宽度（Tk 的 Canvas width 选项就是像素）
        try:
            self.configure(width=max(1, int(round(w))))
        except Exception:
            pass


# --------------------------------------------------------------------------- 卡片容器

class Card(tk.Frame):
    """白色圆角卡片（用 Frame + 边框模拟，内部可放任意控件）。"""

    def __init__(self, master, palette: dict, radius: int = 14, pad: int = 18, **kw):
        self.palette = palette
        super().__init__(master, bg=palette.get("surface", "#fff"),
                         highlightbackground=palette.get("border", "#e2e5ea"),
                         highlightthickness=1, bd=0, **kw)
        self.body = tk.Frame(self, bg=palette.get("surface", "#fff"))
        self.body.pack(fill="both", expand=True, padx=pad, pady=pad)
