"""主窗口：顶部状态栏、导航、仪表盘、最近照片、传输状态、设置与帮助页。"""
from __future__ import annotations

import logging
import os
import queue
import time
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from .. import core
from ..app import AppController, PhotoEntry
from ..core import Settings, human_size, human_speed
from . import help as help_page
from .preview import PreviewWindow
from .settings import SettingsPage
from .theme import PALETTES, Fonts, resolve_theme
from .widgets import Badge, Button, Card, ProgressBar, Switch

log = logging.getLogger("shutterdrop.ui")

BG_KEYS = ("bg", "surface", "surface2", "border", "border_strong", "text", "text2", "text3",
           "accent", "accent_text", "accent_soft", "ok", "ok_soft", "warn", "warn_soft",
           "danger", "danger_soft", "thumb_bg", "track")


class MainWindow:
    def __init__(self, root: tk.Tk, controller: AppController):
        self.root = root
        self.ctl = controller
        self.events: "queue.Queue" = queue.Queue()
        self.p = dict(PALETTES[resolve_theme(controller.settings.theme)])
        self.fonts = Fonts(root, controller.settings.ui_scale)
        self.preview = PreviewWindow(root, controller, self.p, self.fonts)
        self.page = "dashboard"
        self._detect_reachable = False
        self._detect_text = ""
        self._thumbs: dict[str, tk.Frame] = {}
        self._thumb_widgets: list[tk.Frame] = []
        self._last_state_tick = 0.0
        self._build()
        self._wire()
        self.refresh_all()
        self.refresh_recent_from_disk()
        self.root.after(150, self._pump)

    # ================================================================== 构建

    def _build(self) -> None:
        p = self.p
        f = self.fonts
        r = self.root
        r.title("ShutterDrop · 索尼相机 FTP 照片实时接收")
        r.configure(bg=p["bg"])
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        # 默认窗口尺寸，但不能超过屏幕（高分屏缩放下否则会超出屏幕底部）
        w = max(1040, min(1320, int(sw * 0.88), sw - 80))
        h = max(680, min(860, int(sh * 0.86), sh - 100))
        w, h = min(w, sw - 40), min(h, sh - 60)
        r.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - 40)}")
        r.minsize(1040, 680)
        r.protocol("WM_DELETE_WINDOW", self.on_close)

        # ---------------- 顶部栏
        top = tk.Frame(r, bg=p["surface"], height=72, highlightthickness=1,
                       highlightbackground=p["border"])
        top.pack(fill="x")
        top.pack_propagate(False)
        brand = tk.Frame(top, bg=p["surface"])
        brand.pack(side="left", fill="y", padx=(22, 0))
        tk.Label(brand, text="ShutterDrop", bg=p["surface"], fg=p["text"],
                 font=f.get("title")).pack(anchor="w", pady=(14, 0))
        tk.Label(brand, text="索尼相机 FTP · 电脑实时接收", bg=p["surface"], fg=p["text3"],
                 font=f.get("tiny")).pack(anchor="w")

        mid = tk.Frame(top, bg=p["surface"])
        mid.pack(side="left", fill="y", padx=(30, 0))
        row = tk.Frame(mid, bg=p["surface"])
        row.pack(anchor="w", pady=(15, 0))
        self.badge_status = Badge(row, p, "等待相机连接", "text2", font=f.get("small"))
        self.badge_status.pack(side="left")
        self.lbl_hint = tk.Label(row, text="", bg=p["surface"], fg=p["text3"], font=f.get("tiny"))
        self.lbl_hint.pack(side="left", padx=(10, 0))
        self.lbl_detect_top = tk.Label(mid, text="", bg=p["surface"], fg=p["text3"], font=f.get("tiny"))
        self.lbl_detect_top.pack(anchor="w", pady=(2, 0))

        right = tk.Frame(top, bg=p["surface"])
        right.pack(side="right", fill="y", padx=(0, 22))
        self.btn_service = Button(right, "启动 FTP 服务", command=self.toggle_service, kind="primary",
                                  palette=p, fonts=f, padx=18, pady=7, font_key="small", bg=p["surface"])
        self.btn_service.pack(side="right", pady=(20, 0))
        self.switch_auto = Switch(right, p, self.ctl.settings.auto_start,
                                  command=self._on_auto_toggle, bg=p["surface"])
        self.switch_auto.pack(side="right", padx=(4, 16), pady=(21, 0))
        tk.Label(right, text="自动启动", bg=p["surface"], fg=p["text2"],
                 font=f.get("tiny")).pack(side="right", pady=(22, 0))

        # ---------------- 底部状态栏（先 pack，保证不被挤掉）
        status = tk.Frame(r, bg=p["surface"], height=30, highlightthickness=1,
                          highlightbackground=p["border"])
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        self.lbl_statusbar = tk.Label(status, text="", bg=p["surface"], fg=p["text2"],
                                      font=f.get("tiny"), anchor="w")
        self.lbl_statusbar.pack(side="left", padx=18, pady=6)
        self.lbl_cam = tk.Label(status, text="", bg=p["surface"], fg=p["text2"],
                                font=f.get("tiny"), anchor="e")
        self.lbl_cam.pack(side="right", padx=18, pady=6)

        # ---------------- 左侧导航
        body = tk.Frame(r, bg=p["bg"])
        body.pack(fill="both", expand=True)
        nav = tk.Frame(body, bg=p["bg"], width=188)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Label(nav, text="菜单", bg=p["bg"], fg=p["text3"], font=f.get("tiny")).pack(
            anchor="w", padx=22, pady=(22, 6))
        self.nav_buttons: dict[str, Button] = {}
        for key, text, icon in (("dashboard", "仪表盘", "◎"), ("settings", "设置", "⚙"),
                                ("help", "使用说明", "?")):
            b = Button(nav, text, command=lambda k=key: self.show_page(k), kind="ghost",
                       palette=p, fonts=f, padx=16, pady=9, font_key="body", bg=p["bg"], icon=icon)
            b.fixed_width = 150
            b._measure()
            b._resize()
            b._draw()
            b.pack(anchor="w", padx=14, pady=2)
            self.nav_buttons[key] = b
        tk.Frame(nav, bg=p["bg"]).pack(fill="both", expand=True)
        tips = ("小贴士\n\n相机端打开\n「自动 FTP 传输」，\n拍一张就会\n自动传一张。\n\n"
                "再用 USB-C 转\n网口连路由器\n会更快更稳。")
        tk.Label(nav, text=tips, bg=p["bg"], fg=p["text3"], font=f.get("tiny"),
                 anchor="w", justify="left").pack(anchor="w", padx=22, pady=(0, 8))
        tk.Label(nav, text="v1.0 · 仅局域网", bg=p["bg"], fg=p["text3"],
                 font=f.get("tiny")).pack(anchor="w", padx=22, pady=(0, 16))

        content = tk.Frame(body, bg=p["bg"])
        content.pack(side="left", fill="both", expand=True, padx=(0, 18), pady=(14, 0))
        self.content = content
        self.pages: dict[str, tk.Frame] = {}
        self.pages["dashboard"] = tk.Frame(content, bg=p["bg"])
        self.pages["settings"] = SettingsPage(content, self.ctl, p, f,
                                              on_saved=self._on_settings_saved,
                                              on_dirty=self._on_settings_dirty)
        self.pages["help"] = tk.Frame(content, bg=p["bg"])
        help_page.build_help(self.pages["help"], self.ctl, p, f,
                             on_goto_settings=lambda: self.show_page("settings"))
        self._build_dashboard(self.pages["dashboard"])
        self.show_page("dashboard")

    # ------------------------------------------------------------------ 仪表盘

    def _build_dashboard(self, parent) -> None:
        p = self.p
        f = self.fonts
        grid = tk.Frame(parent, bg=p["bg"])
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")
        grid.rowconfigure(3, weight=1)

        # 左列
        c = self._card(grid, "相机连接", "把下面的信息填进相机：FTP 传输 → 服务器设置", row=0, col=0)
        self.lbl_big_status = tk.Label(c, text="等待相机连接", bg=p["surface"], fg=p["text2"],
                                       font=f.get("title"), anchor="w")
        self.lbl_big_status.pack(fill="x")
        self.lbl_conn_detail = tk.Label(c, text="", bg=p["surface"], fg=p["text2"], font=f.get("small"),
                                        anchor="w", justify="left", wraplength=460)
        self.lbl_conn_detail.pack(fill="x", pady=(2, 10))
        info = tk.Frame(c, bg=p["surface2"])
        info.pack(fill="x")
        self.lbl_server_info = tk.Label(info, text="", bg=p["surface2"], fg=p["text"],
                                        font=f.get("mono"), anchor="w", justify="left")
        self.lbl_server_info.pack(fill="x", padx=12, pady=9)
        btns = tk.Frame(c, bg=p["surface"])
        btns.pack(fill="x", pady=(10, 0))
        b1 = Button(btns, "复制连接信息", command=self.copy_info, kind="secondary", palette=p, fonts=f,
                    padx=12, pady=5, font_key="small")
        b1._resize()
        b1.pack(side="left")
        b2 = Button(btns, "复制相机设置步骤", command=self.copy_steps, kind="ghost", palette=p, fonts=f,
                    padx=12, pady=5, font_key="small")
        b2._resize()
        b2.pack(side="left", padx=(8, 0))

        c2 = self._card(grid, "照片保存位置", "相机上传的照片直接存到这里", row=1, col=0)
        self.lbl_save_path = tk.Label(c2, text="", bg=p["surface"], fg=p["text"], font=f.get("mono"),
                                      anchor="w", justify="left", wraplength=460)
        self.lbl_save_path.pack(fill="x")
        self.lbl_save_detail = tk.Label(c2, text="", bg=p["surface"], fg=p["text3"], font=f.get("tiny"),
                                        anchor="w", justify="left", wraplength=460)
        self.lbl_save_detail.pack(fill="x", pady=(4, 10))
        rowb = tk.Frame(c2, bg=p["surface"])
        rowb.pack(fill="x")
        Button(rowb, "打开文件夹", command=lambda: self.open_dir(self.ctl.settings.photo_dir),
               kind="secondary", palette=p, fonts=f, padx=12, pady=5, font_key="small").pack(side="left")
        Button(rowb, "修改设置", command=lambda: self.show_page("settings"), kind="ghost",
               palette=p, fonts=f, padx=12, pady=5, font_key="small").pack(side="left", padx=(8, 0))
        self.lbl_disk = tk.Label(rowb, text="", bg=p["surface"], fg=p["text3"], font=f.get("tiny"))
        self.lbl_disk.pack(side="left", padx=(12, 0))

        # 右列
        c3 = self._card(grid, "传输进度", "有照片上传时实时显示速度与进度", row=0, col=1)
        self.lbl_tx_main = tk.Label(c3, text="暂无传输", bg=p["surface"], fg=p["text"],
                                    font=f.get("body_bold"), anchor="w")
        self.lbl_tx_main.pack(fill="x")
        self.lbl_tx_sub = tk.Label(c3, text="", bg=p["surface"], fg=p["text2"], font=f.get("small"),
                                   anchor="w")
        self.lbl_tx_sub.pack(fill="x")
        self.bar_tx = ProgressBar(c3, p, height=10, color="accent")
        self.bar_tx.pack(fill="x", pady=(10, 8))
        self.lbl_queue = tk.Label(c3, text="", bg=p["surface"], fg=p["text3"], font=f.get("tiny"),
                                  anchor="w", justify="left")
        self.lbl_queue.pack(fill="x")

        c4 = self._card(grid, "本次会话", "统计自本次服务启动以来", row=1, col=1)
        stats = tk.Frame(c4, bg=p["surface"])
        stats.pack(fill="x")
        self.stat_labels = {}
        for i, (key, label) in enumerate((("files", "照片"), ("speed", "速度"),
                                          ("total", "流量"), ("uptime", "运行"))):
            box = tk.Frame(stats, bg=p["surface"])
            box.grid(row=0, column=i, sticky="w", padx=(0, 18))
            val = tk.Label(box, text="—", bg=p["surface"], fg=p["text"], font=f.get("num"), anchor="w")
            val.pack(anchor="w")
            tk.Label(box, text=label, bg=p["surface"], fg=p["text3"], font=f.get("tiny"),
                     anchor="w").pack(anchor="w")
            self.stat_labels[key] = val
        self.lbl_session = tk.Label(c4, text="", bg=p["surface"], fg=p["text3"], font=f.get("tiny"),
                                    anchor="w")
        self.lbl_session.pack(fill="x", pady=(12, 0))

        # 最近照片（整行）
        c5 = self._card(grid, "最近照片", "点击任意一张即可放大并查看 EXIF 参数", row=3, col=0, colspan=2)
        head = tk.Frame(c5, bg=p["surface"])
        head.pack(fill="x", pady=(0, 6))
        self.lbl_recent_info = tk.Label(head, text="还没有收到照片", bg=p["surface"], fg=p["text2"],
                                        font=f.get("small"), anchor="w")
        self.lbl_recent_info.pack(side="left")
        Button(head, "打开文件夹", command=lambda: self.open_dir(self.ctl.settings.photo_dir),
               kind="ghost", palette=p, fonts=f, padx=10, pady=3, font_key="tiny").pack(side="right")
        Button(head, "刷新列表", command=self.refresh_recent_from_disk, kind="ghost", palette=p,
               fonts=f, padx=10, pady=3, font_key="tiny").pack(side="right", padx=(0, 6))
        wrap = tk.Frame(c5, bg=p["surface"])
        wrap.pack(fill="both", expand=True)
        self.recent_canvas = tk.Canvas(wrap, bg=p["surface"], highlightthickness=0, bd=0,
                                       height=20, yscrollincrement=10, xscrollincrement=10)
        self.recent_bar = tk.Scrollbar(wrap, orient="vertical", command=self.recent_canvas.yview)
        self.recent_canvas.configure(yscrollcommand=self.recent_bar.set)
        self.recent_bar.pack(side="right", fill="y")
        self.recent_canvas.pack(side="left", fill="both", expand=True)
        self.recent_strip = tk.Frame(self.recent_canvas, bg=p["surface"])
        self._strip_win = self.recent_canvas.create_window((0, 0), window=self.recent_strip, anchor="nw")
        self.recent_strip.bind("<Configure>", lambda e: self.recent_canvas.configure(
            scrollregion=self.recent_canvas.bbox("all")))
        self.recent_strip.bind("<Enter>", lambda e: self.recent_canvas.bind_all(
            "<MouseWheel>", lambda ev: self.recent_canvas.xview_scroll(int(-ev.delta / 120), "units")))
        self.recent_strip.bind("<Leave>", lambda e: self.recent_canvas.unbind_all("<MouseWheel>"))

    def _card(self, grid: tk.Frame, title: str, subtitle: str, row: int = 0, col: int = 0,
              colspan: int = 1) -> tk.Frame:
        p = self.p
        card = Card(grid, p, radius=14, pad=18)
        if row in (0, 1):
            padx = (0, 7) if col == 0 else (7, 0)
            card.grid(row=row, column=col, padx=padx, pady=(0, 7 if row == 0 else 14),
                      sticky="nsew")
        else:
            card.grid(row=row, column=0, columnspan=colspan, pady=(0, 14), sticky="nsew")
        inner = card.body
        tk.Label(inner, text=title, bg=p["surface"], fg=p["text"], font=self.fonts.get("h2"),
                 anchor="w").pack(fill="x")
        tk.Label(inner, text=subtitle, bg=p["surface"], fg=p["text2"], font=self.fonts.get("small"),
                 anchor="w", justify="left", wraplength=480).pack(fill="x", pady=(1, 8))
        return inner

    # ================================================================== 事件循环

    def _wire(self) -> None:
        ctl = self.ctl
        ctl.on_status = lambda text, color: self.events.put(("status", text, color))
        ctl.on_state = lambda: self.events.put(("state",))
        ctl.on_transfer = lambda: self.events.put(("transfer",))
        ctl.on_photo = lambda entry, new: self.events.put(("photo", entry, new))
        ctl.on_detect = lambda ok, text: self.events.put(("detect", ok, text))
        ctl.on_log = lambda text: self.events.put(("log", text))

    def _pump(self) -> None:
        try:
            while True:
                item = self.events.get_nowait()
                kind = item[0]
                if kind == "status":
                    self._apply_status(item[1], item[2])
                elif kind == "state":
                    self.events_apply_state()
                    self.events_apply_transfer()
                elif kind == "transfer":
                    self.events_apply_transfer()
                elif kind == "photo":
                    self.events_photo(item[1], item[2])
                elif kind == "detect":
                    self._detect_reachable = item[1]
                    self._detect_text = item[2]
                    self.events_apply_state()
                    self._apply_status(*self.ctl._current_status())
                elif kind == "log":
                    self.lbl_statusbar.configure(text=item[1])
        except queue.Empty:
            pass
        except Exception:
            log.exception("处理界面事件出错")
        try:
            self.events_apply_transfer()
            self._update_stats()
            now = time.time()
            if now - self._last_state_tick > 2.0:
                self._last_state_tick = now
                self.ctl._notify_status()
        except Exception:
            log.exception("刷新界面出错")
        self.root.after(150, self._pump)

    # ------------------------------------------------------------------ 状态

    def _apply_status(self, text: str, color: str) -> None:
        try:
            recent_done = any(t.finished and time.time() - t.finished < 12 for t in self.ctl.transfers)
            if color == "ok" and recent_done:
                text, color = "相机已连接 · 刚刚接收完成", "ok"
            self.badge_status.set(text, color)
            big = {"ok": "相机已连接", "warn": "正在接收照片", "danger": "FTP 服务异常",
                   "text3": "FTP 服务已停止", "text2": "等待相机连接"}.get(color, text)
            if color == "ok" and recent_done:
                big = "照片已接收"
            self.lbl_big_status.configure(text=big)
            self.lbl_big_status.configure(fg={"ok": self.p["ok"], "warn": self.p["warn"],
                                              "danger": self.p["danger"]}.get(color, self.p["text2"]))
            last = self.ctl.photos[0].filename if self.ctl.photos else ""
            detail = {
                "ok": (f"照片已保存，正在显示预览。相机保持连接，下一张拍完会自动上传。" if recent_done
                       else "相机已连上本机 FTP，拍摄后会自动上传。"),
                "warn": "数据传输中，传完后自动弹出大图预览。",
                "danger": (self.ctl.server.error or "服务未能启动，请检查端口是否被占用。"),
                "text3": "点右上角「启动 FTP 服务」开始接收。",
                "text2": "相机：打开 FTP 功能 → 服务器设置里填写下面的主机与端口。"
                         + ("（网络中已检测到相机）" if self._detect_reachable else ""),
            }.get(color, text)
            self.lbl_conn_detail.configure(text=detail)
        except tk.TclError:
            pass

    def events_apply_state(self) -> None:
        p = self.p
        s = self.ctl.settings
        server = self.ctl.server
        running = server.running
        hosts = self.ctl.hosts_for_camera()
        host = hosts[0] if hosts else "（未检测到 IP）"
        self.lbl_server_info.configure(
            text=(f"主机名  {host}\n端口    {server.port if running else s.ftp_port}\n"
                  f"用户    {s.ftp_user}\n密码    {s.ftp_password}\n"
                  f"协议    FTP · 安全协议选「关闭」"))
        self.btn_service.set_text("停止 FTP 服务" if running else "启动 FTP 服务")
        self.btn_service.kind = "secondary" if running else "primary"
        self.btn_service._draw()
        self.lbl_save_path.configure(text=s.photo_dir)
        extra = ["目录存在" if os.path.isdir(s.photo_dir) else "目录将在保存时自动创建"]
        extra.append("按日期分组" if s.date_subfolders else "不分日期")
        extra.append("保留目录结构" if s.keep_dir_structure else "平铺保存")
        extra.append("同名覆盖" if s.overwrite else "同名自动加序号")
        self.lbl_save_detail.configure(text="   ·   ".join(extra))
        try:
            self.lbl_disk.configure(text=f"磁盘剩余 {core.disk_usage(s.photo_dir)}")
        except Exception:
            pass
        clients = server.connected_clients()
        if clients:
            net = f"相机在线：{clients[0]}"
        elif self._detect_reachable:
            net = "网络中检测到相机，等待其发起 FTP 连接"
        else:
            net = "本地网络未发现相机"
        self.lbl_cam.configure(text=f"{net}    ·    保存到 {s.photo_dir}")
        self.lbl_detect_top.configure(
            text=self._detect_text or "正在扫描局域网中的相机…",
            fg=p["ok"] if self._detect_reachable else p["text3"])

    # ------------------------------------------------------------------ 传输

    def events_apply_transfer(self) -> None:
        now = time.time()
        active = [t for t in self.ctl.transfers if not t.finished]
        done_recent = [t for t in self.ctl.transfers if t.finished and now - t.finished < 10]
        if active:
            t = active[-1]
            speed = t.speed()
            frac = t.fraction
            self.bar_tx.set(frac)
            self.bar_tx.set_color("accent")
            if t.total > 0:
                self.lbl_tx_main.configure(text=f"{t.filename}    {int(frac * 100)}%")
                sub = f"{human_size(t.received)} / {human_size(t.total)}    ·    {human_speed(speed)}"
                eta = t.eta(speed)
                if eta:
                    sub += f"    ·    剩余约 {max(1, int(eta))} 秒"
            else:
                self.lbl_tx_main.configure(text=f"{t.filename}    {human_size(t.received)}")
                sub = human_speed(speed)
            self.lbl_tx_sub.configure(text=sub)
            self.lbl_queue.configure(
                text=f"还有 {len(active) - 1} 个文件在排队" if len(active) > 1 else "")
        elif done_recent:
            t = done_recent[-1]
            self.bar_tx.set(1.0)
            self.bar_tx.set_color("ok")
            self.lbl_tx_main.configure(text=f"✔ {t.filename}  已保存")
            secs = max(t.finished - t.started, 0.0)
            if secs >= 0.15:
                self.lbl_tx_sub.configure(
                    text=f"{human_size(t.received)}    ·    用时 {secs:.1f} 秒    ·    "
                         f"{human_speed(t.received / secs)}")
            else:
                self.lbl_tx_sub.configure(text=f"{human_size(t.received)}    ·    已完成")
            self.lbl_queue.configure(text="可以继续拍摄，下一张会自动接收")
        else:
            self.bar_tx.set(0.0)
            self.bar_tx.set_color("accent")
            self.lbl_tx_main.configure(text="暂无传输")
            self.lbl_tx_sub.configure(
                text="相机拍下照片后会在这里显示进度" if self.ctl.server.running else "FTP 服务未启动")
            self.lbl_queue.configure(text="")

    def _update_stats(self) -> None:
        srv = self.ctl.server
        now = time.time()
        act = [t for t in self.ctl.transfers if not t.finished]
        cur_speed = act[-1].speed() if act else 0.0
        self.stat_labels["files"].configure(text=str(len(self.ctl.photos)))
        self.stat_labels["speed"].configure(text=human_speed(cur_speed) if cur_speed else "—")
        self.stat_labels["total"].configure(text=human_size(srv.bytes_this_run))
        if srv.running:
            up = int(now - srv.started_at)
            self.stat_labels["uptime"].configure(
                text=f"{up // 60} 分" if up >= 60 else f"{up} 秒")
        else:
            self.stat_labels["uptime"].configure(text="—")
        clients = srv.connected_clients()
        last = self.ctl.photos[0].filename if self.ctl.photos else "—"
        if clients:
            state = "相机已连接"
        elif srv.connected_at:
            state = "相机已断开（等待重连）"
        else:
            state = "本次会话还没有相机连接"
        self.lbl_session.configure(text=f"端口 {srv.port}    ·    {state}    ·    最后一张 {last}")
        self.lbl_recent_info.configure(
            text=(f"已收到 {len(self.ctl.photos)} 张" if self.ctl.photos
                  else "还没有收到照片，拍一张试试"))

    # ------------------------------------------------------------------ 照片

    def events_photo(self, entry: PhotoEntry, is_new: bool) -> None:
        self.add_thumb(entry, first=is_new)
        s = self.ctl.settings
        if is_new:
            if s.auto_open:
                self.preview.show(entry, s.preview_seconds, s.preview_mode)
            if s.open_folder_on_finish:
                self.open_dir(os.path.dirname(entry.path))
            self.events_apply_state()

    def add_thumb(self, entry: PhotoEntry, first: bool = False) -> None:
        p = self.p
        if entry.path in self._thumbs:
            return
        box = tk.Frame(self.recent_strip, bg=p["surface"], cursor="hand2",
                       highlightthickness=1, highlightbackground=p["border"])
        ph = self.ctl.thumbnail(entry, (150, 100))
        holder = tk.Label(box, bg=p["thumb_bg"], image=ph if ph else "", width=150, height=100,
                          text="" if ph else "无预览图", fg=p["text3"], font=self.fonts.get("tiny"))
        holder.image = ph  # type: ignore[attr-defined]
        holder.pack(padx=6, pady=(6, 2))
        name = entry.filename if len(entry.filename) <= 22 else entry.filename[:19] + "…"
        tk.Label(box, text=name, bg=p["surface"], fg=p["text"], font=self.fonts.get("tiny"),
                 anchor="w").pack(fill="x", padx=8)
        tk.Label(box, text=time.strftime("%H:%M:%S", time.localtime(entry.received)),
                 bg=p["surface"], fg=p["text3"], font=self.fonts.get("tiny"), anchor="w").pack(
            fill="x", padx=8, pady=(0, 6))
        for w in (box, holder):
            w.bind("<Button-1>", lambda e, en=entry: self.open_preview(en))
        if first:
            box.pack(side="left", padx=(0, 10), pady=2)
            self._thumb_widgets.insert(0, box)
            self.recent_canvas.xview_moveto(0)
        else:
            box.pack(side="left", padx=(0, 10), pady=2)
            self._thumb_widgets.append(box)
        self._thumbs[entry.path] = box
        while len(self._thumb_widgets) > 60:
            old = self._thumb_widgets.pop()
            for k, v in list(self._thumbs.items()):
                if v is old:
                    del self._thumbs[k]
            old.destroy()
        self._recent_resize()

    def _recent_resize(self) -> None:
        """缩略图行的高度随数量变化，保证最近照片区域能撑开。"""
        try:
            self.recent_strip.update_idletasks()
            need = self.recent_strip.winfo_reqheight()
            self.recent_canvas.configure(height=max(40, min(190, need)))
        except tk.TclError:
            pass

    def refresh_recent_from_disk(self) -> None:
        for w in self.recent_strip.winfo_children():
            w.destroy()
        self._thumb_widgets = []
        self._thumbs = {}
        files = self.ctl.recent_files(40)
        entries = []
        for path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue
            entries.append(PhotoEntry(path=path, filename=os.path.basename(path), size=st.st_size,
                                      origin="", received=st.st_mtime))
        for e in entries:
            self.add_thumb(e)
        if entries and self.ctl.photos:
            self.lbl_statusbar.configure(
                text=f"从保存目录载入最近 {len(entries)} 张照片（本次会话已收到 {len(self.ctl.photos)} 张）")

    def open_preview(self, entry: PhotoEntry) -> None:
        s = self.ctl.settings
        self.preview.show(entry, s.preview_seconds, s.preview_mode)

    # ================================================================== 页面切换

    def show_page(self, key: str) -> None:
        if key not in self.pages:
            return
        self.page = key
        for name, frame in self.pages.items():
            frame.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for name, b in self.nav_buttons.items():
            active = name == key
            b.kind = "secondary" if active else "ghost"
            b._draw()
        if key == "settings":
            sp = self.pages["settings"]
            sp.refresh_ips()
            sp._check_dir(sp._get_entry("photo_dir"))
        if key == "dashboard":
            self.events_apply_state()
            self.events_apply_transfer()
            self._update_stats()

    # ================================================================== 动作

    def toggle_service(self) -> None:
        if self.ctl.server.running:
            self.ctl.stop_server()
        else:
            self.ctl.start_server()
        self.refresh_all()

    def _on_auto_toggle(self, value: bool) -> None:
        s = Settings.from_dict(self.ctl.settings.to_dict())
        s.auto_start = value
        self.ctl.apply_settings(s, restart_server=False)
        self.lbl_statusbar.configure(text="已开启「自动启动」" if value else "已关闭「自动启动」")

    def _on_settings_saved(self, s: Settings) -> None:
        self.refresh_all()
        self.lbl_statusbar.configure(text="设置已保存")

    def _on_settings_dirty(self, dirty: bool) -> None:
        lbl = getattr(self, "lbl_statusbar", None)
        if lbl is not None:
            lbl.configure(text="设置已修改，记得点「保存设置」" if dirty else "")

    def copy_info(self) -> None:
        s = self.ctl.settings
        hosts = self.ctl.hosts_for_camera()
        host = hosts[0] if hosts else "本机局域网 IP"
        text = (f"主机名：{host}\n端口：{s.ftp_port}\n用户：{s.ftp_user}\n密码：{s.ftp_password}\n"
                f"安全协议：关闭\n保存位置：{s.photo_dir}")
        self._copy(text, "已复制连接信息")

    def copy_steps(self) -> None:
        s = self.ctl.settings
        hosts = self.ctl.hosts_for_camera()
        host = hosts[0] if hosts else "本机局域网 IP"
        text = (
            "索尼相机 FTP 设置步骤：\n"
            "1) MENU → 网络 → Wi-Fi → 连接到访问点，连上与电脑相同的路由器\n"
            "   （或用 USB-C 转网口 + 网线接到同一个路由器，更快更稳）\n"
            "2) MENU → 网络 → FTP 传输 → FTP 传输功能 → 服务器设置 → 服务器1\n"
            f"   主机名 {host} / 端口 {s.ftp_port} / 安全协议 关闭\n"
            f"   用户 {s.ftp_user} / 密码 {s.ftp_password} / 目录层级 标准\n"
            "3) FTP 传输 → FTP 传输功能 → FTP 功能 → 开\n"
            "4) FTP 传输 → FTP 传输功能 → 自动 FTP 传输 → 开，自动 FTP 目标 → 静止影像 → 全部\n"
            "5) 拍一张照片，电脑上的 ShutterDrop 会自动弹出预览")
        self._copy(text, "已复制相机设置步骤")

    def _copy(self, text: str, toast: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.lbl_statusbar.configure(text=toast)
        except tk.TclError:
            pass

    def open_dir(self, path: str) -> None:
        try:
            core.ensure_dir(path)
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showwarning("无法打开", f"{path}\n{exc}", parent=self.root)

    def refresh_all(self) -> None:
        self.events_apply_state()
        self.events_apply_transfer()
        self._update_stats()
        self.switch_auto.set(self.ctl.settings.auto_start)

    def on_close(self) -> None:
        try:
            self.ctl.stop()
        except Exception:
            pass
        try:
            self.preview.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
