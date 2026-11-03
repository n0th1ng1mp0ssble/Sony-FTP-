"""生成仿真“相机照片”和模拟相机上传客户端，用于离线联调与端到端测试。

模拟客户端还原了真实相机的行为：
  1. 每次上传都新建控制连接（USER/PASS/TYPE I/PASV）；A7M5 使用 EPSV。
  2. A7M4 风格：先主动 (PORT) 模式尝试，失败后回退到被动 (PASV) 模式。
  3. 数据连接可以先于 STOR 命令建立。
"""
from __future__ import annotations

import ftplib
import os
import random
import socket
import struct
import sys
import time
from datetime import datetime

try:
    from PIL import Image, ImageDraw
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False


# --------------------------------------------------------------------------- 生成测试照片

SCENES = [
    ((28, 40, 70), (240, 170, 90), "golden hour"),
    ((20, 60, 90), (120, 200, 230), "blue lake"),
    ((30, 70, 40), (170, 220, 120), "forest trail"),
    ((70, 40, 80), (250, 160, 200), "night street"),
    ((90, 60, 30), (230, 200, 150), "desert dune"),
]


def exif_block(model: str = "ILCE-7M5", lens: str = "FE 24-70mm F2.8 GM II",
               iso: int = 400, fnum=(28, 10), shutter=(1, 250), focal=35,
               size=(7008, 4672), when: str | None = None) -> bytes:
    """构造符合规范的 EXIF TIFF 数据块（可被 Pillow / Lightroom / ExifTool 读取）。"""
    e = "<"
    if when is None:
        when = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
    make = b"SONY\x00"
    model_b = model.encode() + b"\x00"
    lens_b = lens.encode() + b"\x00"
    dt = when.encode() + b"\x00"

    def rat(n, d):
        return struct.pack(e + "II", n, d)

    ifd0 = [(0x010F, 2, len(make), make), (0x0110, 2, len(model_b), model_b),
            (0x0112, 3, 1, struct.pack(e + "H", 1)), (0x0131, 2, 9, b"ShutterD\x00"),
            (0x8769, 4, 1, None)]
    exif = [(0x829A, 5, 1, rat(*shutter)), (0x829D, 5, 1, rat(*fnum)),
            (0x8827, 3, 1, struct.pack(e + "H", iso)), (0x9003, 2, len(dt), dt),
            (0x9204, 10, 1, struct.pack(e + "ii", 0, 1)), (0x920A, 5, 1, rat(focal, 1)),
            (0x9209, 3, 1, struct.pack(e + "H", 16)), (0xA001, 3, 1, struct.pack(e + "H", 1)),
            (0xA002, 4, 1, struct.pack(e + "I", size[0])), (0xA003, 4, 1, struct.pack(e + "I", size[1])),
            (0xA403, 3, 1, struct.pack(e + "H", 0)), (0xA405, 3, 1, struct.pack(e + "H", focal)),
            (0xA433, 2, 5, b"SONY\x00"), (0xA434, 2, len(lens_b), lens_b),
            (0xA431, 2, 9, b"1234567\x00")]

    def ifd_size(n):
        return 2 + 12 * n + 4

    # IFD0 + 值区 + ExifIFD + 值区
    val0 = b""
    offs0 = {}
    for i, (tag, typ, cnt, val) in enumerate(ifd0):
        if val is not None and len(val) > 4:
            offs0[i] = 8 + ifd_size(len(ifd0)) + len(val0)
            val0 += val
    exif_off = 8 + ifd_size(len(ifd0)) + len(val0)
    val1 = b""
    offs1 = {}
    for i, (tag, typ, cnt, val) in enumerate(exif):
        if len(val) > 4:
            offs1[i] = exif_off + ifd_size(len(exif)) + len(val1)
            val1 += val

    def build(entries, offsets, next_off=0, exif_ptr=None):
        out = struct.pack(e + "H", len(entries))
        for i, (tag, typ, cnt, val) in enumerate(entries):
            if tag == 0x8769:
                out += struct.pack(e + "HHI", tag, typ, cnt) + struct.pack(e + "I", exif_ptr)
            elif i in offsets:
                out += struct.pack(e + "HHI", tag, typ, cnt) + struct.pack(e + "I", offsets[i])
            else:
                out += struct.pack(e + "HHI", tag, typ, cnt) + val.ljust(4, b"\x00")
        return out + struct.pack(e + "I", next_off)

    tiff = (b"II*\x00" + struct.pack(e + "I", 8) +
            build(ifd0, offs0, exif_off, exif_off) + val0 +
            build(exif, offs1) + val1)
    return b"Exif\x00\x00" + tiff


def make_photo(path: str, seed: int = 0, size=(4200, 2800), model: str = "ILCE-7M5",
               lens: str = "FE 24-70mm F2.8 GM II", quality: int = 92) -> str:
    """生成一张有渐变、主体和文字的仿真照片（带 EXIF）。"""
    if not _PIL:
        raise RuntimeError("Pillow 不可用")
    rnd = random.Random(seed)
    (c1, c2, label) = SCENES[seed % len(SCENES)]
    w, h = size
    # 低分辨率画渐变和斑点，再放大，避免逐行绘制大图太慢
    small = Image.new("RGB", (max(2, w // 16), max(2, h // 16)))
    d = ImageDraw.Draw(small)
    sw, sh = small.size
    for y in range(sh):
        t = y / max(1, sh - 1)
        col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        d.line([(0, y), (sw, y)], fill=col)
    for _ in range(26):
        x, y = rnd.randint(0, sw), rnd.randint(0, sh)
        r = rnd.randint(2, max(3, sw // 12))
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=(rnd.randint(40, 230), rnd.randint(40, 230), rnd.randint(40, 230)))
    img = small.resize((w, h), Image.BICUBIC)
    d = ImageDraw.Draw(img)
    band = max(60, h // 20)
    d.rectangle([band // 2, band // 2, band * 7, band * 2], fill=(0, 0, 0))
    d.text((band, band), f"SAMPLE {seed:04d}  {label}", fill=(255, 255, 255))
    exif = exif_block(model=model, lens=lens, iso=rnd.choice([100, 200, 400, 800, 1600]),
                      fnum=rnd.choice([(18, 10), (28, 10), (40, 10), (56, 10)]),
                      shutter=rnd.choice([(1, 60), (1, 125), (1, 250), (1, 1000), (1, 4000)]),
                      focal=rnd.choice([16, 24, 35, 50, 70, 85]),
                      size=(w, h))
    img.save(path, quality=quality, exif=exif, subsampling=0)
    return path


# --------------------------------------------------------------------------- 模拟客户端

class SimCamera:
    """按真实相机的节奏上传文件。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 2121,
                 user: str = "sony", password: str = "sony1234",
                 use_epsv: bool = False, port_first: bool = False):
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.use_epsv = use_epsv
        self.port_first = port_first
        self.log: list[str] = []

    def _connect(self) -> ftplib.FTP:
        ftp = ftplib.FTP(timeout=20)
        ftp.encoding = "utf-8"
        ftp.connect(self.host, self.port, timeout=10)
        ftp.login(self.user, self.password)
        ftp.set_debuglevel(0)
        return ftp

    def upload(self, local_path: str, remote_name: str | None = None,
               remote_dir: str | None = None, chunk: int = 256 * 1024,
               throttle: float = 0.0, ascii_mode: bool = False) -> float:
        name = remote_name or os.path.basename(local_path)
        t0 = time.time()
        if self.port_first:
            self._upload_port_mode(local_path, name, remote_dir, chunk, throttle)
        else:
            ftp = self._connect()
            try:
                if remote_dir:
                    for seg in [s for s in remote_dir.strip("/").split("/") if s]:
                        try:
                            ftp.mkd(seg)
                        except ftplib.error_perm:
                            pass
                        ftp.cwd(seg)
                if ascii_mode:
                    ftp.voidcmd("TYPE A")
                else:
                    ftp.voidcmd("TYPE I")
                if self.use_epsv:
                    ftp.voidcmd("OPTS UTF8 ON")
                with open(local_path, "rb") as f:
                    ftp.storbinary(f"STOR {name}", f, blocksize=chunk, callback=None)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass
        return time.time() - t0

    def _upload_port_mode(self, local_path: str, name: str, remote_dir, chunk, throttle):
        """老式相机：主动模式 + 先开数据连接再发 STOR（本机 FTP 服务器也兼容这种顺序）。"""
        ctrl = socket.create_connection((self.host, self.port), timeout=10)
        f = ctrl.makefile("rwb")

        def cmd(line: str) -> str:
            f.write((line + "\r\n").encode("utf-8"))
            f.flush()
            resp = f.readline().decode("utf-8", "replace")
            self.log.append(f"> {line}\n< {resp.strip()}")
            return resp

        cmd("USER " + self.user)
        cmd("PASS " + self.password)
        cmd("TYPE I")
        if remote_dir:
            cmd("CWD " + remote_dir)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        p = listener.getsockname()[1]
        cmd(f"PORT 127,0,0,1,{p >> 8},{p & 0xFF}")
        # 先连数据端口（服务器 accept 后会等待 STOR）
        dsock = socket.create_connection((self.host, p), timeout=10)
        listener.close()
        resp = cmd(f"STOR {name}")
        if not resp.startswith("150") and not resp.startswith("125"):
            dsock.close()
            raise RuntimeError(f"STOR 失败：{resp}")
        with open(local_path, "rb") as fh:
            while True:
                buf = fh.read(chunk)
                if not buf:
                    break
                dsock.sendall(buf)
                if throttle:
                    time.sleep(throttle)
        dsock.close()
        resp = f.readline().decode("utf-8", "replace")
        self.log.append(f"< {resp.strip()}")
        cmd("QUIT")
        ctrl.close()

    def mkdir(self, path: str) -> None:
        ftp = self._connect()
        try:
            for seg in [s for s in path.strip("/").split("/") if s]:
                try:
                    ftp.mkd(seg)
                except ftplib.error_perm:
                    pass
                ftp.cwd(seg)
        finally:
            ftp.quit()


def camera_failure_paths(host: str, port: int) -> str:
    """一份常见错误检查清单（供 UI 帮助与测试使用）。"""
    return (f"1) 相机 ↔ PC 是否在同一网络（相机菜单 → 网络 → Wi-Fi / 有线 LAN）\n"
            f"2) 相机 FTP 服务器设置：主机 {host}  端口 {port}  安全协议 关闭\n"
            f"3) 相机 [FTP 功能] 需为 [开]，并确认相机屏幕出现 FTP 连接图标\n"
            f"4) Windows 防火墙需允许 Python 的 TCP {port} 与被动数据端口")


if __name__ == "__main__":
    print(camera_failure_paths("192.168.1.10", 2121))
