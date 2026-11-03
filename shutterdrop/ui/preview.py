"""实时预览窗：每收到一张照片弹出并展示 N 秒，倒计时结束自动关闭。"""
from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

from .theme import Fonts
from .widgets import Button, ImageLabel, ProgressBar

try:
    from PIL import ImageTk
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False


class PreviewWindow:
    """同一个窗口复用显示最新照片；支持全屏展示。"""

    def __init__(self, master: tk.Tk, controller, palette: dict, fonts: Fonts):
        self.master = master
        self.ctl = controller
        self.p = palette
        self.fonts = fonts
        self.win: Optional[tk.Toplevel] = None
        self.entry = None
        self.mode = "window"
        self.remaining = 0.0
        self.total = 0.0
        self._tick_job = None
        self._paused = False
        self._build_later = None
        self._last_tick = time.time()

    # ------------------------------------------------------------------ 显示

    def show(self, entry, seconds: int, mode: str = "window") -> None:
        """显示一张照片，seconds=0 表示不自动关闭。"""
        self.entry = entry
        self.mode = mode
        self.total = float(seconds)
        self.remaining = float(seconds)
        self._paused = False
        self._last_tick = time.time()
        if self.win is None or not self._alive():
            self._create()
        self._refresh_content()
        self._apply_mode()
        self.win.deiconify()
        try:
            self.win.lift()
        except tk.TclError:
            pass
        self._schedule_tick()
        self._update_countdown()

    def close(self) -> None:
        self._cancel_tick()
        win, self.win = self.win, None
        self.entry = None
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except tk.TclError:
                pass

    def is_open(self) -> bool:
        return self.win is not None and self._alive()

    def pause(self) -> None:
        self._paused = True
        self._update_countdown()

    def resume(self) -> None:
        self._paused = False
        self._last_tick = time.time()
        self._schedule_tick()
        self._update_countdown()

    def _alive(self) -> bool:
        try:
            return bool(self.win is not None and self.win.winfo_exists())
        except tk.TclError:
            return False

    # ------------------------------------------------------------------ 构建

    def _create(self) -> None:
        p = self.p
        top = tk.Toplevel(self.master)
        top.withdraw()
        top.title("实时预览")
        top.configure(bg=p["bg"])
        top.protocol("WM_DELETE_WINDOW", self.close)
        self.win = top
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        w, h = int(min(sw * 0.86, 1440)), int(min(sh * 0.86, 920))
        top.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 20)}")
        top.minsize(720, 460)
        # 给图片区一个较大的期望尺寸，窗口布局时它优先占满，不受 Label 空尺寸影响
        self._img_hint = tk.Frame(top, height=10, width=10)
        self._img_hint.place(x=-20, y=-20)

        outer = tk.Frame(top, bg=p["bg"])
        outer.pack(fill="both", expand=True, padx=22, pady=(18, 14))

        # 顶栏：倒计时 + 文件名 + 操作
        head = tk.Frame(outer, bg=p["bg"])
        head.pack(fill="x", pady=(0, 12))
        self.lbl_count = tk.Label(head, text="", bg=p["bg"], fg=p["accent"],
                                  font=self.fonts.get("title"))
        self.lbl_count.pack(side="left")
        self.lbl_name = tk.Label(head, text="", bg=p["bg"], fg=p["text2"],
                                 font=self.fonts.get("body"))
        self.lbl_name.pack(side="left", padx=(16, 0))
        btn_row = tk.Frame(head, bg=p["bg"])
        btn_row.pack(side="right")
        self.btn_pause = Button(btn_row, "暂停倒计时", command=self._toggle_pause, kind="secondary",
                                palette=p, fonts=self.fonts, padx=12, pady=6, font_key="small")
        self.btn_pause._resize()
        self.btn_pause.pack(side="left", padx=(0, 8))
        self.btn_full = Button(btn_row, "全屏", command=self._toggle_full, kind="secondary",
                               palette=p, fonts=self.fonts, padx=12, pady=6, font_key="small")
        self.btn_full._resize()
        self.btn_full.pack(side="left", padx=(0, 8))
        btn_close = Button(btn_row, "关闭", command=self.close, kind="ghost", palette=p,
                           fonts=self.fonts, padx=12, pady=6, font_key="small")
        btn_close._resize()
        btn_close.pack(side="left")

        # 倒计时进度
        self.bar = ProgressBar(outer, p, height=6, color="accent")
        self.bar.pack(fill="x", pady=(0, 14))

        # 主体：图片 + EXIF
        body = tk.Frame(outer, bg=p["bg"])
        body.pack(fill="both", expand=True)
        self.img = ImageLabel(body, bg=p["thumb_bg"])
        # 图片区优先占满：给 Label 一个较大的期望尺寸，避免空图时被压成一条线
        self.img.configure(width=760, height=500)
        self.exif = tk.Frame(body, bg=p["surface"], highlightthickness=1,
                             highlightbackground=p["border"])
        self.exif_body = tk.Frame(self.exif, bg=p["surface"])
        self.exif_body.pack(fill="both", expand=True, padx=18, pady=16)
        tk.Label(self.exif_body, text="照片参数", bg=p["surface"], fg=p["text"],
                 font=self.fonts.get("h2"), anchor="w").pack(fill="x", pady=(0, 10))
        self.exif_list = tk.Frame(self.exif_body, bg=p["surface"])
        self.exif_list.pack(fill="both", expand=True)
        tk.Label(self.exif_body, text="按 空格 暂停/继续 · Esc 关闭 · F 全屏",
                 bg=p["surface"], fg=p["text3"], font=self.fonts.get("tiny"),
                 anchor="w", justify="left").pack(side="bottom", fill="x", pady=(10, 0))
        self._layout()
        top.bind("<Escape>", lambda e: self.close())
        top.bind("<space>", lambda e: self._toggle_pause())
        top.bind("<KeyPress-f>", lambda e: self._toggle_full())
        top.bind("<KeyPress-F>", lambda e: self._toggle_full())
        top.bind("<Return>", lambda e: self.close())
        top.focus_set()

    def _on_space(self, _e=None):
        self._toggle_pause()

    def _layout(self) -> None:
        side = self.ctl.settings.exif_side
        for w in (self.img, self.exif):
            w.pack_forget()
        if side == "right":
            self.img.pack(side="left", fill="both", expand=True)
            self.exif.pack(side="right", fill="y", padx=(16, 0))
            self.exif.configure(width=300)
            self.exif.pack_propagate(False)
        elif side == "left":
            self.exif.pack(side="left", fill="y", padx=(0, 16))
            self.exif.configure(width=300)
            self.exif.pack_propagate(False)
            self.img.pack(side="left", fill="both", expand=True)
        else:  # below
            self.exif.pack(side="bottom", fill="x", pady=(14, 0))
            self.exif.configure(height=190)
            self.exif.pack_propagate(False)
            self.img.pack(side="top", fill="both", expand=True)

    def relayout(self) -> None:
        if self._alive():
            self._layout()

    def _apply_mode(self) -> None:
        if self.win is None:
            return
        if self.mode == "fullscreen":
            try:
                self.win.attributes("-fullscreen", True)
            except tk.TclError:
                pass
            self.btn_full.set_text("退出全屏")
            self.btn_full._resize()
        else:
            try:
                self.win.attributes("-fullscreen", False)
            except tk.TclError:
                pass
            self.btn_full.set_text("全屏")
            self.btn_full._resize()

    def _toggle_full(self) -> None:
        self.mode = "window" if self.mode == "fullscreen" else "fullscreen"
        self._apply_mode()

    # ------------------------------------------------------------------ 内容

    def _refresh_content(self) -> None:
        if not self._alive() or self.entry is None:
            return
        e = self.entry
        self.win.title(f"实时预览 · {e.filename}")
        self.lbl_name.configure(text=f"{e.filename}   ·   {_size(e.size)}")
        self.img.set_image(e.path, immediate=True)
        self.win.after(30, self._fit_image)
        self._fill_exif(e)

    def _fit_image(self) -> None:
        """窗口布局完成后，再按图片区域的实际大小渲染一次，避免底部留白。"""
        if self._alive() and self.entry is not None:
            self.img.set_image(self.entry.path, immediate=True)

    def _fill_exif(self, entry) -> None:
        for w in self.exif_list.winfo_children():
            w.destroy()
        p = self.p
        exif = self.ctl.load_exif(entry)
        rows = []
        priority = ["相机", "镜头", "光圈", "快门", "ISO", "焦距", "等效焦距",
                    "拍摄时间", "曝光补偿", "白平衡", "分辨率", "格式"]
        items = dict(exif.items) if exif is not None else {}
        for key in priority:
            if items.get(key):
                rows.append((key, items[key]))
        for key, val in items.items():
            if key not in priority and key not in ("文件名",):
                rows.append((key, val))
        if not rows:
            rows = [("提示", "此文件没有 EXIF（可能是导出图或视频）")]
        big_keys = {"相机", "镜头", "光圈", "快门", "ISO"}
        for i, (k, v) in enumerate(rows[:14]):
            row = tk.Frame(self.exif_list, bg=p["surface"])
            row.pack(fill="x", pady=(0, 6))
            tk.Label(row, text=k, bg=p["surface"], fg=p["text3"], width=7,
                     anchor="w", font=self.fonts.get("small")).pack(side="left")
            tk.Label(row, text=v, bg=p["surface"], fg=p["text"],
                     font=self.fonts.get("body_bold" if k in big_keys else "small"),
                     anchor="w", justify="left", wraplength=210).pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------ 倒计时

    def _schedule_tick(self) -> None:
        self._cancel_tick()
        if self._alive() and self.total > 0:
            self._tick_job = self.win.after(250, self._tick)

    def _cancel_tick(self) -> None:
        if self._tick_job is not None:
            try:
                self.master.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None

    def _tick(self) -> None:
        self._tick_job = None
        if not self._alive():
            return
        now = time.time()
        if not self._paused and self.total > 0:
            self.remaining -= now - self._last_tick
        self._last_tick = now
        self._update_countdown()
        if self.total > 0 and self.remaining <= 0:
            self.close()
            return
        self._schedule_tick()

    def _update_countdown(self) -> None:
        if not self._alive():
            return
        if self.total > 0:
            secs = max(0, int(self.remaining + 0.999))
            text = f"{secs} 秒后自动关闭" if not self._paused else f"已暂停 · 还剩 {secs} 秒"
            self.bar.set(max(0.0, min(1.0, self.remaining / self.total)))
            self.btn_pause.set_text("继续倒计时" if self._paused else "暂停倒计时")
            self.btn_pause._resize()
        else:
            text = "常亮显示（不会自动关闭）"
            self.bar.set(1.0)
        self.lbl_count.configure(text=text)

    def _toggle_pause(self) -> None:
        if self._paused:
            self.resume()
        else:
            self.pause()


def _size(n: int) -> str:
    from ..core import human_size
    return human_size(n)
