"""应用状态与控制逻辑（不依赖界面，便于测试）。"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageTk

from . import core
from .core import Settings, human_size
from .detector import CameraDetector
from .ftpserver import (ClientEvent, FtpServer, ServerInfo, TransferFinished,
                        TransferProgress, TransferStarted)
from . import imaging

log = logging.getLogger("shutterdrop.app")

try:
    from PIL import Image as _Img
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False


# --------------------------------------------------------------------------- 数据

@dataclass
class ActiveTransfer:
    id: str
    remote: str
    filename: str
    dest: str
    peer: str
    total: int = 0
    received: int = 0
    started: float = field(default_factory=time.time)
    samples: deque = field(default_factory=lambda: deque(maxlen=12))
    finished: float = 0.0          # 已结束的留在列表里显示多少秒

    @property
    def fraction(self) -> float:
        if self.total > 0:
            return min(1.0, self.received / self.total)
        return 0.0

    def speed(self) -> float:
        now = time.time()
        self.samples.append((now, self.received))
        if len(self.samples) < 2:
            return 0.0
        t0, b0 = self.samples[0]
        dt = now - t0
        if dt <= 0.05:
            return 0.0
        return max(0.0, (self.received - b0) / dt)

    def eta(self, speed: float) -> Optional[float]:
        if not speed or self.total <= 0:
            return None
        return max(0.0, (self.total - self.received) / speed)


@dataclass
class PhotoEntry:
    path: str
    filename: str
    size: int
    origin: str
    received: float
    exif: object = None          # exif_reader.ExifData
    error: Optional[str] = None
    _photo_small: object = None
    _photo_big: object = None

    @property
    def ext(self) -> str:
        return os.path.splitext(self.path)[1].lower()


# --------------------------------------------------------------------------- 控制器

class AppController:
    """把 FTP 服务、相机检测、照片库、设置串起来。UI 通过回调订阅事件。"""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings().load()
        self.server = FtpServer(self.settings, on_event=self._on_event)
        self.detector = CameraDetector(self.settings.camera_ip)
        self.detector.on_result = self._on_detect
        self.photos: deque[PhotoEntry] = deque(maxlen=self.settings.keep_recent)
        self.transfers: list[ActiveTransfer] = []
        self.status = "idle"            # idle / running / stopped / error
        self.lock = threading.RLock()
        self.started_at = 0.0
        self._thumbs: dict[str, object] = {}
        self._thumb_size = (160, 120)

        # UI 回调
        self.on_status = None          # (text, color_key)
        self.on_state = None           # ()
        self.on_transfer = None        # ()
        self.on_photo = None           # (PhotoEntry, is_new)
        self.on_detect = None          # (reachable, info_text)
        self.on_log = None             # (text)

    # ------------------------------------------------------------------ 生命周期

    def start_server(self) -> bool:
        ok = self.server.start()
        self.status = "running" if ok else "error"
        self.started_at = time.time()
        self._notify_status()
        self._notify_state()
        if ok:
            self._log(f"FTP 服务已启动，端口 {self.server.port}")
        else:
            self._log(self.server.error or "FTP 服务启动失败")
        return ok

    def stop_server(self) -> None:
        self.server.stop()
        self.status = "stopped"
        self._notify_status()
        self._notify_state()
        self._log("FTP 服务已停止")

    def toggle_server(self) -> bool:
        if self.server.running:
            self.stop_server()
            return False
        return self.start_server()

    def start_detection(self) -> None:
        self.detector.set_fixed_ip(self.settings.camera_ip)
        self.detector.start(self.settings.detect_interval)
        self.detector.poke()

    def stop(self) -> None:
        try:
            self.server.stop()
        finally:
            self.detector.stop()

    def apply_settings(self, new: Settings, restart_server: bool = True) -> None:
        with self.lock:
            old_dir = self.settings.photo_dir
            old_port = self.settings.ftp_port
            self.settings.__dict__.update(new.__dict__)
            self.settings.clamp()
            self.settings.save()
            self.server.cfg = self.settings
            self.detector.set_fixed_ip(self.settings.camera_ip)
        if restart_server and (old_port != self.settings.ftp_port or not self.server.running):
            self._log("端口或保存目录已更改，正在重启 FTP 服务…")
            self.start_server()
        else:
            self._log("设置已保存")
        if old_dir != self.settings.photo_dir:
            try:
                core.ensure_dir(self.settings.photo_dir)
            except OSError:
                pass
        self._notify_state()

    @property
    def local_ips(self) -> list[str]:
        ips = core.local_ipv4s()
        preferred = [ip for ip in self.settings.advertise_ips if ip in ips]
        rest = [ip for ip in ips if ip not in preferred]
        return preferred + rest

    def hosts_for_camera(self) -> list[str]:
        """给用户抄进相机的“主机名”候选列表（按推荐顺序）。"""
        ips = self.local_ips
        if self.settings.advertise_ips:
            return list(self.settings.advertise_ips)
        return ips[:2]

    # ------------------------------------------------------------------ 事件

    def _on_event(self, ev) -> None:
        if isinstance(ev, TransferStarted):
            with self.lock:
                self.transfers.append(ActiveTransfer(ev.id, ev.remote, ev.filename,
                                                     ev.dest, ev.peer, ev.size))
                self.transfers = self.transfers[-20:]
            self._log(f"开始接收：{ev.filename}")
            self._notify_transfer()
        elif isinstance(ev, TransferProgress):
            with self.lock:
                for t in self.transfers:
                    if t.id == ev.id:
                        t.received = ev.received
                        t.total = ev.size or ev.received
                self._notify_transfer()
        elif isinstance(ev, TransferFinished):
            self._on_finished(ev)
        elif isinstance(ev, ClientEvent):
            if ev.kind == "connected":
                self.detector.poke()
                self._notify_status(force="connected")
            elif ev.kind == "disconnected":
                self._notify_status()
        elif isinstance(ev, ServerInfo):
            self._notify_status()

    def _on_finished(self, ev: TransferFinished) -> None:
        with self.lock:
            for t in self.transfers:
                if t.id == ev.id:
                    t.received = ev.size
                    t.total = max(t.total, ev.size)
                    t.finished = time.time() if ev.ok else 0
            self.transfers = [t for t in self.transfers if not (t.finished and time.time() - t.finished > 15)]
        self._notify_transfer()
        if not ev.ok or not ev.path:
            self._log(f"接收失败：{ev.filename}（{ev.error or '未知错误'}）")
            self._notify_status(force="error")
            return
        entry = PhotoEntry(path=ev.path, filename=os.path.basename(ev.path), size=ev.size,
                           origin=ev.peer, received=time.time())
        with self.lock:
            self.photos.appendleft(entry)
            if len(self.photos) > self.settings.keep_recent:
                self.photos.pop()
        speed = ev.speed
        self._log(f"接收完成：{os.path.basename(ev.path)}  {human_size(ev.size)}  "
                  f"{human_size(speed)}/s" if speed else
                  f"接收完成：{os.path.basename(ev.path)}  {human_size(ev.size)}")
        self._notify_photo(entry, True)
        self._notify_state()
        if self.settings.open_folder_on_finish:
            pass  # 由 UI 决定是否打开文件夹

    def _on_detect(self, result) -> None:
        text = ""
        if result and result.reachable:
            text = f"网络中存在相机：{result.ip}"
        if self.on_detect:
            try:
                self.on_detect(bool(result and result.reachable), text)
            except Exception:
                pass

    def _notify_status(self, force: Optional[str] = None) -> None:
        if not self.on_status:
            return
        text, color = self._current_status()
        try:
            self.on_status(text, color)
        except Exception:
            pass

    def _current_status(self) -> tuple[str, str]:
        """计算当前状态文本与颜色键。"""
        clients = self.server.connected_clients()
        if self.status == "error":
            return "FTP 服务未能启动（端口被占用？）", "danger"
        if not self.server.running:
            return "FTP 服务已停止", "text3"
        if time.time() - self.server.last_upload_at < 6:
            return "相机已连接 · 正在接收照片", "warn"
        if clients:
            return "相机已连接", "ok"
        if self.server.connected_at:
            last = max(self.server.connected_at.values())
            left = self.settings.camera_offline_seconds - (time.time() - last)
            if left > 0:
                return f"相机刚刚断开，{int(left) + 1} 秒后判定离线", "warn"
        return "等待相机连接", "text2"

    def _notify_state(self) -> None:
        if self.on_state:
            try:
                self.on_state()
            except Exception:
                pass

    def _notify_transfer(self) -> None:
        if self.on_transfer:
            try:
                self.on_transfer()
            except Exception:
                pass

    def _notify_photo(self, entry: PhotoEntry, is_new: bool) -> None:
        if self.on_photo:
            try:
                self.on_photo(entry, is_new)
            except Exception:
                pass

    def _log(self, text: str) -> None:
        log.info(text)
        if self.on_log:
            try:
                self.on_log(text)
            except Exception:
                pass

    # ------------------------------------------------------------------ 照片信息

    def load_exif(self, entry: PhotoEntry):
        if entry.exif is None:
            from .exif_reader import read_exif
            entry.exif = read_exif(entry.path)
        return entry.exif

    def thumbnail(self, entry: PhotoEntry, box=(160, 120)):
        """生成（缓存的）缩略图 PhotoImage。"""
        key = (entry.path, box)
        if key in self._thumbs:
            return self._thumbs[key]
        from .ui.widgets import fit_image
        img = fit_image(entry.path, box[0], box[1], bg=self.settings and "#e4e7ec")
        if img is None:
            return None
        try:
            ph = ImageTk.PhotoImage(img)
        except Exception:
            return None
        self._thumbs[key] = ph
        return ph

    def open_in_explorer(self, path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(os.path.dirname(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception:
            self._log(f"无法打开文件夹：{path}")

    def recent_files(self, limit: int = 40) -> list[str]:
        exts = core.IMAGE_EXTS
        found = []
        root = self.settings.photo_dir
        if not os.path.isdir(root):
            return []
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if os.path.splitext(name)[1].lower() in exts and not name.endswith(".shutterdrop-part"):
                    found.append(os.path.join(dirpath, name))
        found.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
        return found[:limit]

    def delete_photo(self, entry: PhotoEntry) -> bool:
        try:
            os.remove(entry.path)
        except OSError:
            return False
        with self.lock:
            try:
                self.photos.remove(entry)
            except ValueError:
                pass
        return True
