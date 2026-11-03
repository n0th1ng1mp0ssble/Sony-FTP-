"""设置页：FTP 连接、照片保存、实时预览、相机检测、外观。"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional

from ..core import Settings, ensure_dir, valid_photo_dir
from .theme import Fonts
from .widgets import Button, Segmented, Switch


class SettingsPage(tk.Frame):
    def __init__(self, master, controller, palette: dict, fonts: Fonts,
                 on_saved: Optional[Callable[[Settings], None]] = None,
                 on_dirty: Optional[Callable[[bool], None]] = None):
        self.ctl = controller
        self.p = palette
        self.fonts = fonts
        self.on_saved = on_saved
        self.on_dirty = on_dirty
        super().__init__(master, bg=palette["bg"])
        self._dirty = False
        self._widgets: dict[str, object] = {}
        self._entries: dict[str, tk.Entry] = {}
        self._build()
        self.load_from(controller.settings)

    # ------------------------------------------------------------------ 基础构件

    def _mark_dirty(self, *_a) -> None:
        if not self._dirty:
            self._dirty = True
            if self.on_dirty:
                self.on_dirty(True)

    def is_dirty(self) -> bool:
        return self._dirty

    def _card(self, parent, title: str, subtitle: str = "") -> tk.Frame:
        p = self.p
        card = tk.Frame(parent, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
        card.pack(fill="x", pady=(0, 14))
        inner = tk.Frame(card, bg=p["surface"])
        inner.pack(fill="x", padx=22, pady=18)
        tk.Label(inner, text=title, bg=p["surface"], fg=p["text"], font=self.fonts.get("h2"),
                 anchor="w").pack(fill="x")
        if subtitle:
            tk.Label(inner, text=subtitle, bg=p["surface"], fg=p["text2"], font=self.fonts.get("small"),
                     anchor="w", justify="left", wraplength=820).pack(fill="x", pady=(3, 10))
        else:
            tk.Frame(inner, bg=p["surface"], height=6).pack(fill="x")
        return inner

    def _row(self, parent, label: str, hint: str = "") -> tk.Frame:
        p = self.p
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill="x", pady=5)
        left = tk.Frame(row, bg=p["surface"], width=170)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text=label, bg=p["surface"], fg=p["text"], font=self.fonts.get("body"),
                 anchor="w").pack(fill="x")
        if hint:
            tk.Label(left, text=hint, bg=p["surface"], fg=p["text3"], font=self.fonts.get("tiny"),
                     anchor="w", justify="left", wraplength=160).pack(fill="x")
        right = tk.Frame(row, bg=p["surface"])
        right.pack(side="left", fill="x", expand=True)
        return right

    def _entry(self, parent, key: str, width: int = 24, show: str = "", mask: bool = False) -> tk.Entry:
        p = self.p
        e = tk.Entry(parent, font=self.fonts.get("body"), width=width, bg=p["surface2"], fg=p["text"],
                     insertbackground=p["text"], relief="flat", highlightthickness=1,
                     highlightbackground=p["border_strong"], highlightcolor=p["accent"], show=show)
        e.pack(side="left", ipady=5)
        e.bind("<KeyRelease>", self._mark_dirty)
        e.bind("<<Paste>>", lambda ev: self.after(10, self._mark_dirty))
        if mask:
            sw = Switch(parent, p, False, command=lambda v: e.configure(show="" if v else "•"),
                        bg=p["surface"])
            sw.pack(side="left", padx=(10, 4))
            tk.Label(parent, text="显示", bg=p["surface"], fg=p["text2"],
                     font=self.fonts.get("small")).pack(side="left")
        self._entries[key] = e
        return e

    def _switch(self, key: str, parent, value: bool) -> Switch:
        sw = Switch(parent, self.p, value, command=lambda v: self._mark_dirty(), bg=self.p["surface"])
        self._widgets[key] = sw
        sw.pack(side="left")
        return sw

    def _seg(self, key: str, parent, options: list, value, width: int = 240) -> Segmented:
        seg = Segmented(parent, self.p, options, value, command=lambda v: self._mark_dirty(),
                        font=self.fonts.get("small"), width=width, bg=self.p["surface"])
        self._widgets[key] = seg
        seg.pack(side="left")
        return seg

    # ------------------------------------------------------------------ 界面

    def _build(self) -> None:
        p = self.p
        wrap = tk.Frame(self, bg=p["bg"])
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=p["bg"], highlightthickness=0, bd=0)
        bar = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(self.canvas, bg=p["bg"])
        win = self.canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))

        def wheel(evt):
            try:
                self.canvas.yview_scroll(int(-evt.delta / 120), "units")
            except tk.TclError:
                pass
        body.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", wheel))
        body.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        tk.Label(body, text="设置", bg=p["bg"], fg=p["text"], font=self.fonts.get("display"),
                 anchor="w").pack(fill="x", pady=(0, 2))
        tk.Label(body, text="改完点「保存设置」；FTP 端口变化后服务会自动重启。",
                 bg=p["bg"], fg=p["text2"], font=self.fonts.get("small"), anchor="w").pack(fill="x", pady=(0, 16))

        self._build_ftp(body)
        self._build_storage(body)
        self._build_preview(body)
        self._build_detect(body)
        self._build_appearance(body)
        self._build_actions(body)
        self.refresh_ips()
        # Canvas 按钮创建后再按像素校正一次尺寸
        for w in self._walk_buttons(self):
            try:
                w._resize()
                w._draw()
            except Exception:
                pass

    def _build_ftp(self, parent) -> None:
        p = self.p
        card = self._card(parent, "FTP 连接",
                          "以下四项按原样填进相机：MENU → 网络 → FTP 传输 → FTP 传输功能 → 服务器设置")
        row = self._row(card, "端口 Port", "默认 2121，0~65535")
        self._entry(row, "ftp_port", 10)
        tk.Label(row, text="   安全协议选「关闭」，目录层级选「标准」", bg=p["surface"], fg=p["text3"],
                 font=self.fonts.get("tiny")).pack(side="left")
        row = self._row(card, "用户名 User", "最长 64 字符")
        self._entry(row, "ftp_user", 20)
        row = self._row(card, "密码 Password", "")
        self._entry(row, "ftp_password", 20, show="•", mask=True)
        row = self._row(card, "本机主机名", "相机里填这个 IP")
        self.lbl_ips = tk.Label(row, text="", bg=p["surface"], fg=p["accent"],
                                font=self.fonts.get("mono"), anchor="w", justify="left",
                                wraplength=600)
        self.lbl_ips.pack(side="left")
        b = Button(row, "刷新", command=self.refresh_ips, kind="ghost", palette=p, fonts=self.fonts,
                   padx=8, pady=2, font_key="tiny")
        b._resize()
        b.pack(side="left", padx=(10, 0))
        row = self._row(card, "启动时自动开启", "打开程序就自动运行 FTP 服务")
        self._switch("auto_start", row, True)

    @staticmethod
    def _walk_buttons(widget):
        from .widgets import Button
        for child in widget.winfo_children():
            if isinstance(child, Button):
                yield child
            yield from SettingsPage._walk_buttons(child)

    def refresh_ips(self) -> None:
        try:
            ips = self.ctl.hosts_for_camera()
        except Exception:
            ips = []
        self.lbl_ips.configure(text="    ".join(ips) if ips else "未检测到局域网 IP，请检查网络连接")

    def _build_storage(self, parent) -> None:
        p = self.p
        card = self._card(parent, "照片保存位置",
                          "相机上传的照片会保存到这里，文件名保持相机原样。")
        row = self._row(card, "保存目录", "")
        self._entry(row, "photo_dir", 40)
        b = Button(row, "浏览…", command=self._browse, kind="secondary", palette=p, fonts=self.fonts,
                   padx=12, pady=4, font_key="small")
        b._resize()
        b.pack(side="left", padx=(8, 0))
        b2 = Button(row, "打开", command=self._open_dir, kind="ghost", palette=p, fonts=self.fonts,
                    padx=10, pady=4, font_key="small")
        b2._resize()
        b2.pack(side="left", padx=(6, 0))
        self.lbl_dir_state = tk.Label(card, text="", bg=p["surface"], fg=p["text3"],
                                      font=self.fonts.get("tiny"), anchor="w")
        self.lbl_dir_state.pack(fill="x", padx=(176, 0))
        row = self._row(card, "按日期建子文件夹", "例：2026-10-26/DSC01234.JPG")
        self._switch("date_subfolders", row, False)
        row = self._row(card, "保留相机目录结构", "相机发来 DCIM/100MSDCF 时原样保留")
        self._switch("keep_dir_structure", row, True)
        row = self._row(card, "同名文件覆盖", "关闭时自动加序号，绝不覆盖旧照片")
        self._switch("overwrite", row, False)
        row = self._row(card, "接收完打开文件夹", "")
        self._switch("open_folder_on_finish", row, False)

    def _build_preview(self, parent) -> None:
        p = self.p
        card = self._card(parent, "拍完即看（实时预览）",
                          "每收到一张照片就弹出大图并显示 EXIF，倒计时结束自动关闭。")
        row = self._row(card, "每张展示时长", "0 = 一直显示")
        self.lbl_seconds = tk.Label(row, text="10 秒", bg=p["surface"], fg=p["text"],
                                    font=self.fonts.get("num"), width=6, anchor="w")
        self.scale_seconds = tk.Scale(row, from_=0, to=120, orient="horizontal", resolution=1,
                                      length=240, showvalue=False, sliderlength=22, width=12,
                                      sliderrelief="flat", bg=p["surface"], bd=0,
                                      highlightthickness=0, fg=p["text"], troughcolor=p["track"],
                                      activebackground=p["accent"], command=self._on_seconds)
        self.scale_seconds.pack(side="left")
        self.lbl_seconds.pack(side="left", padx=(6, 10))
        for sec in (3, 5, 10, 20, 30):
            b = Button(row, f"{sec}s", command=lambda s=sec: self._set_seconds(s), kind="ghost",
                       palette=p, fonts=self.fonts, padx=7, pady=2, font_key="tiny")
            b._resize()
            b.pack(side="left", padx=1)
        row = self._row(card, "展示方式", "")
        self._seg("preview_mode", row, [("window", "窗口"), ("fullscreen", "全屏")], "window", 200)
        row = self._row(card, "EXIF 位置", "")
        self._seg("exif_side", row, [("right", "右侧"), ("left", "左侧"), ("below", "下方")], "right", 240)
        row = self._row(card, "新照片自动弹出", "关闭后只在「最近照片」里显示")
        self._switch("auto_open", row, True)

    def _set_seconds(self, s: int) -> None:
        self.scale_seconds.set(s)
        self._on_seconds(s)

    def _on_seconds(self, val) -> None:
        try:
            v = int(float(val))
        except (TypeError, ValueError):
            return
        self.lbl_seconds.configure(text="常亮" if v == 0 else f"{v} 秒")
        self._mark_dirty()

    def _build_detect(self, parent) -> None:
        p = self.p
        card = self._card(parent, "相机在线检测",
                          "除了「相机已连接」，程序还会在局域网里扫描相机端口，判断相机是否开机入网。")
        row = self._row(card, "相机 IP（可选）", "留空则自动扫描")
        self._entry(row, "camera_ip", 18)
        row = self._row(card, "检测间隔（秒）", "")
        self._entry(row, "detect_interval", 6)
        row = self._row(card, "离线判定（秒）", "多久没连接算断开")
        self._entry(row, "camera_offline_seconds", 6)

    def _build_appearance(self, parent) -> None:
        p = self.p
        card = self._card(parent, "外观")
        row = self._row(card, "主题", "")
        self._seg("theme", row, [("light", "浅色"), ("dark", "深色"), ("auto", "跟随系统")], "light", 280)
        row = self._row(card, "界面缩放", "1.0 为默认")
        self.scale_scale = tk.Scale(row, from_=0.8, to=1.6, orient="horizontal", resolution=0.1,
                                    length=240, sliderlength=22, width=12, sliderrelief="flat",
                                    bg=p["surface"], bd=0, highlightthickness=0,
                                    fg=p["text"], troughcolor=p["track"], activebackground=p["accent"],
                                    command=lambda v: self._mark_dirty())
        self.scale_scale.pack(side="left")
        tk.Label(row, text="重启程序后生效", bg=p["surface"], fg=p["text3"],
                 font=self.fonts.get("tiny")).pack(side="left", padx=10)

    def _build_actions(self, parent) -> None:
        p = self.p
        bar = tk.Frame(parent, bg=p["bg"])
        bar.pack(fill="x", pady=(2, 28))
        b1 = Button(bar, "保存设置", command=self.save, kind="primary", palette=p, fonts=self.fonts,
                    padx=26, pady=10)
        b1._resize()
        b1.pack(side="right")
        b2 = Button(bar, "恢复默认", command=self.reset_defaults, kind="secondary", palette=p,
                    fonts=self.fonts, padx=16, pady=10)
        b2._resize()
        b2.pack(side="right", padx=(0, 10))
        b3 = Button(bar, "放弃修改", command=lambda: self.load_from(self.ctl.settings), kind="ghost",
                    palette=p, fonts=self.fonts, padx=16, pady=10)
        b3._resize()
        b3.pack(side="right", padx=(0, 10))
        self.lbl_saved = tk.Label(bar, text="", bg=p["bg"], fg=p["ok"], font=self.fonts.get("small"))
        self.lbl_saved.pack(side="left")

    # ------------------------------------------------------------------ 读 / 写

    def _set_entry(self, key: str, value) -> None:
        e = self._entries.get(key)
        if e is not None:
            e.delete(0, "end")
            e.insert(0, str(value))

    def _get_entry(self, key: str, default: str = "") -> str:
        e = self._entries.get(key)
        return e.get().strip() if e is not None else default

    def load_from(self, s: Settings) -> None:
        self._set_entry("ftp_port", s.ftp_port)
        self._set_entry("ftp_user", s.ftp_user)
        self._set_entry("ftp_password", s.ftp_password)
        self._set_entry("photo_dir", s.photo_dir)
        self._set_entry("camera_ip", s.camera_ip)
        self._set_entry("detect_interval", s.detect_interval)
        self._set_entry("camera_offline_seconds", s.camera_offline_seconds)
        self.scale_seconds.set(s.preview_seconds)
        self._on_seconds(s.preview_seconds)
        self.scale_scale.set(s.ui_scale)
        for key, value in (
                ("auto_start", s.auto_start), ("date_subfolders", s.date_subfolders),
                ("keep_dir_structure", s.keep_dir_structure), ("overwrite", s.overwrite),
                ("open_folder_on_finish", s.open_folder_on_finish), ("auto_open", s.auto_open)):
            w = self._widgets.get(key)
            if w is not None:
                w.set(value)
        for key, value in (("preview_mode", s.preview_mode), ("exif_side", s.exif_side),
                           ("theme", s.theme)):
            w = self._widgets.get(key)
            if w is not None:
                w.set(value)
        self._check_dir(s.photo_dir)
        self._dirty = False
        if self.on_dirty:
            self.on_dirty(False)
        self.lbl_saved.configure(text="")

    def _check_dir(self, path: str) -> None:
        ok = bool(path) and os.path.isdir(path)
        self.lbl_dir_state.configure(text="✔ 目录存在，可写入" if ok else "目录尚不存在，保存时会自动创建",
                                     fg=self.p["ok"] if ok else self.p["text3"])

    def collect(self) -> Settings:
        s = Settings.from_dict(self.ctl.settings.to_dict())
        try:
            s.ftp_port = int(self._get_entry("ftp_port", str(s.ftp_port)) or s.ftp_port)
        except ValueError:
            s.ftp_port = self.ctl.settings.ftp_port
        s.ftp_user = self._get_entry("ftp_user") or "sony"
        s.ftp_password = self._get_entry("ftp_password") or "sony1234"
        path = self._get_entry("photo_dir")
        if path:
            s.photo_dir = os.path.abspath(os.path.expanduser(path))
        s.camera_ip = self._get_entry("camera_ip")
        for key in ("detect_interval", "camera_offline_seconds"):
            try:
                setattr(s, key, int(self._get_entry(key) or getattr(s, key)))
            except ValueError:
                pass
        s.preview_seconds = int(float(self.scale_seconds.get()))
        for key in ("auto_start", "date_subfolders", "keep_dir_structure", "overwrite",
                    "open_folder_on_finish", "auto_open"):
            w = self._widgets.get(key)
            if w is not None:
                setattr(s, key, bool(w.value))
        for key in ("preview_mode", "exif_side", "theme"):
            w = self._widgets.get(key)
            if w is not None:
                setattr(s, key, w.value)
        s.ui_scale = float(self.scale_scale.get())
        s.clamp()
        return s

    def save(self) -> None:
        s = self.collect()
        ok, why = valid_photo_dir(s.photo_dir)
        if not ok:
            messagebox.showerror("保存目录不可用", f"无法使用目录：\n{s.photo_dir}\n\n原因：{why}", parent=self)
            return
        old_port = self.ctl.settings.ftp_port
        was_running = self.ctl.server.running
        # 端口变了就必须重启；没在运行时也顺手启动
        self.ctl.apply_settings(s, restart_server=(s.ftp_port != old_port or not was_running))
        self.lbl_saved.configure(text="✔ 已保存" + ("，FTP 服务已重启" if s.ftp_port != old_port else ""))
        self._check_dir(s.photo_dir)
        self._dirty = False
        if self.on_dirty:
            self.on_dirty(False)
        if self.on_saved:
            self.on_saved(s)
        self.after(3000, lambda: self.lbl_saved.configure(text=""))

    def reset_defaults(self) -> None:
        if messagebox.askyesno("恢复默认", "把所有设置恢复为默认值？\n（保存目录会变回「图片\\ShutterDrop」）",
                               parent=self):
            self.load_from(Settings())
            self._mark_dirty()

    # ------------------------------------------------------------------ 动作

    def _browse(self) -> None:
        cur = self._get_entry("photo_dir") or self.ctl.settings.photo_dir
        path = filedialog.askdirectory(initialdir=cur if os.path.isdir(cur) else None,
                                       title="选择照片保存位置", parent=self)
        if path:
            s = os.path.abspath(os.path.normpath(path))
            self._set_entry("photo_dir", s)
            self._check_dir(s)
            self._mark_dirty()

    def _open_dir(self) -> None:
        path = self._get_entry("photo_dir") or self.ctl.settings.photo_dir
        try:
            ensure_dir(path)
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showwarning("无法打开", str(exc), parent=self)
