"""配置、路径与通用小工具。全部使用标准库实现。"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict

APP_NAME = "ShutterDrop"
APP_NAME_CN = "快门落点"
APP_ID = "ShutterDrop"
VERSION = "1.0.0"

# 相机可能上传的静态图片格式（A7M4 / A7M5：JPEG、HEIF、RAW；视频的代理文件）
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".heic", ".heif", ".hif",
    ".arw", ".dng",
    ".tif", ".tiff",
    ".png",
    ".mp4", ".mts", ".m2ts", ".mpg", ".mov",
    ".xml", ".xmp",
}
PREVIEWABLE_EXTS = {".jpg", ".jpeg", ".jpe", ".jfif", ".heic", ".heif", ".hif", ".png", ".tif", ".tiff", ".arw", ".dng"}

IMAGE_EXTS_PLAIN = {"jpg", "jpeg", "jpe", "jfif", "png", "tif", "tiff", "bmp", "webp"}
IMAGE_EXTS_EXTRA = {"heic", "heif", "hif", "avif", "arw", "dng", "cr3", "nef", "gif"}


# --------------------------------------------------------------------------- 路径

def app_data_dir() -> str:
    """配置、日志、证书等可写数据目录。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_ID)
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        d = os.path.join(tempfile.gettempdir(), APP_ID)
        os.makedirs(d, exist_ok=True)
        return d


def default_photo_dir() -> str:
    base = os.path.expanduser("~")
    for sub in ("Pictures", "图片", "My Pictures"):
        p = os.path.join(base, sub)
        if os.path.isdir(p):
            return os.path.join(p, APP_NAME)
    return os.path.join(base, APP_NAME)


CONFIG_PATH = os.path.join(app_data_dir(), "settings.json")
LOG_PATH = os.path.join(app_data_dir(), "shutterdrop.log")


# --------------------------------------------------------------------------- 小工具

def human_size(n: float | int | None) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def human_speed(bps: float | None) -> str:
    if not bps or bps <= 0:
        return "—"
    return human_size(bps) + "/s"


def human_duration(sec: float | None) -> str:
    if sec is None:
        return "—"
    total = int(round(sec))
    if total < 60:
        return f"{total} 秒"
    if total < 3600:
        return f"{total // 60} 分 {total % 60:02d} 秒"
    return f"{total // 3600} 小时 {(total % 3600) // 60:02d} 分"


def local_ipv4s() -> list[str]:
    """列出本机局域网 IPv4（最佳接口在前）。"""
    found: dict[str, int] = {}

    def add(ip: str, prio: int) -> None:
        if not ip or ip.startswith("127.") or ip.startswith("169.254."):
            return
        if ip.count(".") != 3:
            return
        try:
            socket.inet_aton(ip)
        except OSError:
            return
        if ip not in found or found[ip] > prio:
            found[ip] = prio

    # 1) 默认路由所在接口（UDP connect 不会真正发包）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            add(s.getsockname()[0], 0)
        finally:
            s.close()
    except OSError:
        pass

    # 2) 主机名解析
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0], 1)
    except OSError:
        pass

    # 3) Windows 下用 ipconfig 兜底（能覆盖 USB 网卡、虚拟网卡）
    if sys.platform == "win32":
        exe = shutil.which("ipconfig")
        if exe:
            try:
                import subprocess
                out = subprocess.run([exe], capture_output=True, timeout=4,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
                text = out.decode("gbk", "replace") + out.decode("utf-8", "replace")
                for m in re.finditer(r"(?:IPv4[^:：]*)[:：]\s*([0-9]{1,3}(?:\.[0-9]{1,3}){3})", text):
                    add(m.group(1), 2)
            except Exception:
                pass

    return sorted(found, key=lambda ip: (found[ip], ip))


def guess_camera_subnets(own_ips: list[str]) -> list[str]:
    """根据本机网段推测相机可能的网段前缀（A7 相机默认自动获取 IP）。"""
    prefixes: list[str] = []
    for ip in own_ips:
        parts = ip.split(".")
        if parts[0] == "192" and parts[1] == "168":
            prefixes.append(".".join(parts[:3]) + ".")
        elif parts[0] == "10":
            prefixes.append(".".join(parts[:3]) + ".")
        elif parts[0] == "172" and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            prefixes.append(".".join(parts[:3]) + ".")
    # 相机直连/热点常见的默认网段
    for extra in ("192.168.1.", "192.168.0.", "192.168.137.", "192.168.54.", "10.0.0."):
        prefixes.append(extra)
    seen, out = set(), []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def ensure_dir(path: str) -> bool:
    """创建目录（带存在性检查，避免重复创建时的异常）。"""
    try:
        if path and not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        return bool(path) and os.path.isdir(path)
    except OSError:
        return False


def valid_photo_dir(path: str) -> tuple[bool, str]:
    """检查照片保存目录是否可用，返回 (是否可用, 说明)。"""
    if not path or not path.strip():
        return False, "目录为空"
    try:
        path = os.path.abspath(os.path.expanduser(path.strip()))
    except (OSError, ValueError):
        return False, "路径不合法"
    if os.path.exists(path) and not os.path.isdir(path):
        return False, "路径指向一个文件"
    try:
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".shutterdrop_write_test")
        with open(probe, "wb") as f:
            f.write(b"ok")
        os.remove(probe)
        return True, "可用"
    except OSError as exc:
        return False, f"无法写入：{exc}"


def safe_filename(name: str) -> str:
    """去掉路径分隔符和非法字符，只保留文件名。"""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "unnamed"


def disk_usage(path: str) -> str:
    """返回照片目录所在磁盘的剩余空间说明。"""
    try:
        probe = path
        while probe and not os.path.exists(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        free = shutil.disk_usage(probe or ".").free
        return human_size(free)
    except OSError:
        return "—"


def unique_path(directory: str, filename: str, overwrite: bool = False) -> str:
    """返回一个在目录中不冲突的文件路径。overwrite=True 时同名覆盖。"""
    path = os.path.join(directory, filename)
    if overwrite or not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(filename)
    for i in range(1, 10000):
        cand = os.path.join(directory, f"{stem}_{i}{ext}")
        if not os.path.exists(cand):
            return cand
    return os.path.join(directory, f"{stem}_{int(time.time())}{ext}")


# --------------------------------------------------------------------------- 配置

@dataclass
class Settings:
    # FTP 服务器
    ftp_port: int = 2121
    ftp_user: str = "sony"
    ftp_password: str = "sony1234"
    advertise_ips: list[str] = field(default_factory=list)  # 显示给相机的“主机 IP”候选
    auto_start: bool = True                                 # 打开程序即启动 FTP 服务

    # 照片保存
    photo_dir: str = field(default_factory=default_photo_dir)
    overwrite: bool = False               # 同名文件覆盖（相机“不覆盖”时会自动改名）
    date_subfolders: bool = False         # 按 日期(YYYY-MM-DD) 建子文件夹
    keep_dir_structure: bool = True       # 保留相机上传时自带的目录层级（如 DCIM/100MSDCF）

    # 预览显示
    preview_seconds: int = 10             # 每张照片展示多少秒（0 = 不自动关闭）
    preview_mode: str = "window"          # window = 内置预览窗；fullscreen = 全屏展示
    exif_side: str = "right"              # 预览窗里 EXIF 在图片的哪一侧：right / left / below
    auto_open: bool = True                # 收到新照片自动弹出预览

    # 相机在线检测
    camera_ip: str = ""                   # 留空 = 自动检测
    detect_interval: int = 4              # 秒
    camera_offline_seconds: int = 15      # 超过多久没有连接就视为断开

    # 界面
    ui_scale: float = 1.0
    theme: str = "light"                  # light / dark / auto
    keep_recent: int = 200                # 最近照片列表保留数量

    # 其他
    open_folder_on_finish: bool = False

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        s = cls()
        for key, value in (data or {}).items():
            if not hasattr(s, key):
                continue
            cur = getattr(s, key)
            try:
                if isinstance(cur, bool):
                    value = bool(value)
                elif isinstance(cur, int):
                    value = int(value)
                elif isinstance(cur, list):
                    value = [str(v) for v in (value or [])]
                elif isinstance(cur, float):
                    value = float(value)
                elif isinstance(cur, str):
                    value = str(value)
            except (TypeError, ValueError):
                continue
            setattr(s, key, value)
        return s

    def load(self) -> "Settings":
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded = Settings.from_dict(data)
            self.__dict__.update(loaded.__dict__)
        except (OSError, ValueError):
            pass
        self.clamp()
        return self

    def save(self) -> bool:
        self.clamp()
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
            return True
        except OSError:
            return False

    def clamp(self) -> None:
        self.ftp_port = min(65535, max(1, int(self.ftp_port or 2121)))
        self.ftp_user = (self.ftp_user or "sony")[:64]
        self.ftp_password = (self.ftp_password or "")[:64]
        if not self.ftp_password:
            self.ftp_password = "sony1234"
        self.photo_dir = os.path.abspath(os.path.expanduser(self.photo_dir or default_photo_dir()))
        self.preview_seconds = min(600, max(0, int(self.preview_seconds)))
        self.detect_interval = min(60, max(2, int(self.detect_interval)))
        self.camera_offline_seconds = min(600, max(3, int(self.camera_offline_seconds)))
        self.keep_recent = min(2000, max(10, int(self.keep_recent)))
        self.ui_scale = min(2.0, max(0.7, float(self.ui_scale or 1.0)))
        if self.preview_mode not in ("window", "fullscreen"):
            self.preview_mode = "window"
        if self.exif_side not in ("right", "left", "below"):
            self.exif_side = "right"
        if self.theme not in ("light", "dark", "auto"):
            self.theme = "light"
        self.camera_ip = (self.camera_ip or "").strip()
        seen, ips = set(), []
        for ip in self.advertise_ips:
            ip = ip.strip()
            if ip and ip not in seen:
                seen.add(ip)
                ips.append(ip)
        self.advertise_ips = ips

    # ------------------------------------------------------------------
    def subdir_for(self, rel_dir: str, now: float) -> str:
        """根据设置计算某次上传的落盘子目录。"""
        parts: list[str] = []
        if self.date_subfolders:
            parts.append(time.strftime("%Y-%m-%d", time.localtime(now)))
        if self.keep_dir_structure and rel_dir:
            segments = rel_dir.replace("\\", "/").split("/")
            # 子目录不能越出保存目录：去掉 . / .. 与盘符，且以 .. 开头时整段丢弃
            if any(seg.strip() == ".." for seg in segments):
                segments = []
            for seg in segments:
                seg = seg.strip()
                if seg and seg not in (".", "..") and not re.fullmatch(r"[A-Za-z]:", seg):
                    cleaned = safe_filename(seg)
                    if cleaned:
                        parts.append(cleaned)
        return os.path.join(self.photo_dir, *parts) if parts else self.photo_dir
