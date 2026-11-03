"""EXIF 读取：普通格式用 Pillow，RAW（.ARW/.DNG）用最小 TIFF 解析器。"""
from __future__ import annotations

import io
import os
import struct
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
from typing import Any, Optional

try:
    from PIL import Image
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False


# --------------------------------------------------------------------------- TIFF/EXIF 基础

_TAG_NAMES = {
    0x010F: "Make", 0x0110: "Model", 0x0112: "Orientation", 0x0131: "Software",
    0x0132: "DateTime", 0x8769: "ExifIFD", 0x8825: "GPSIFD",
    0x829A: "ExposureTime", 0x829D: "FNumber", 0x8822: "ExposureProgram",
    0x8827: "ISOSpeedRatings", 0x8830: "SensitivityType", 0x8832: "RecommendedExposureIndex",
    0x8833: "ISOSpeed",
    0x9003: "DateTimeOriginal", 0x9004: "DateTimeDigitized", 0x9010: "OffsetTime",
    0x9201: "ShutterSpeedValue", 0x9202: "ApertureValue", 0x9204: "ExposureBiasValue",
    0x9207: "MeteringMode", 0x9208: "LightSource", 0x9209: "Flash", 0x920A: "FocalLength",
    0x927C: "MakerNote", 0x9286: "UserComment", 0xA000: "FlashpixVersion", 0xA001: "ColorSpace",
    0xA002: "ExifImageWidth", 0xA003: "ExifImageHeight", 0xA402: "ExposureMode",
    0xA403: "WhiteBalance", 0xA404: "DigitalZoomRatio", 0xA405: "FocalLengthIn35mmFilm",
    0xA406: "SceneCaptureType", 0xA40C: "SubjectDistanceRange", 0xA434: "LensModel",
    0xA430: "CameraOwnerName", 0xA431: "BodySerialNumber", 0xA433: "LensMake",
    0xA435: "LensSerialNumber",
    0x0001: "GPSLatitudeRef", 0x0002: "GPSLatitude", 0x0003: "GPSLongitudeRef",
    0x0004: "GPSLongitude", 0x0005: "GPSAltitudeRef", 0x0006: "GPSAltitude",
    0x0007: "GPSTimeStamp", 0x001D: "GPSDateStamp",
}

_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _read_ifd(data: bytes, tiff: int, offset: int, endian: str, depth: int = 0) -> dict[int, Any]:
    out: dict[int, Any] = {}
    if depth > 3 or offset <= 0 or tiff + offset + 2 > len(data):
        return out
    try:
        count = struct.unpack(endian + "H", data[tiff + offset:tiff + offset + 2])[0]
    except struct.error:
        return out
    p = tiff + offset + 2
    for _ in range(count):
        if p + 12 > len(data):
            break
        tag, typ, n = struct.unpack(endian + "HHI", data[p:p + 8])
        size = _TYPE_SIZE.get(typ, 1) * n
        value_bytes = data[p + 8:p + 12] if size <= 4 else None
        if size > 4:
            voff = struct.unpack(endian + "I", data[p + 8:p + 12])[0]
            if tiff + voff + size <= len(data):
                value_bytes = data[tiff + voff:tiff + voff + size]
        p += 12
        if value_bytes is None:
            continue
        out[tag] = _parse_value(value_bytes, typ, n, endian)
        if tag in (0x8769, 0x8825) and typ in (4, 13):
            sub_off = out[tag]
            if isinstance(sub_off, int):
                sub = _read_ifd(data, tiff, sub_off, endian, depth + 1)
                for k, v in sub.items():
                    out.setdefault(k, v)
    return out


def _parse_value(b: bytes, typ: int, n: int, endian: str) -> Any:
    try:
        if typ == 2:
            return b.rstrip(b"\x00").decode("utf-8", "replace")
        if typ in (3, 4, 6, 8, 9, 11, 12):
            # 定长定宽类型：未用满的 SSIZE 字节用 0 填充
            item = _TYPE_SIZE[typ]
            fmt = {3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 11: "f", 12: "d"}[typ]
            need = item * n
            b = b[:need].ljust(need, b"\x00")
            vals = list(struct.unpack(endian + fmt * n, b))
        else:
            fmt = {1: "B", 5: "II", 10: "ii"}[typ]
            item = _TYPE_SIZE[typ]
            need = item * n
            b = b[:need].ljust(need, b"\x00")
            if typ in (5, 10):
                vals = []
                for i in range(n):
                    num, den = struct.unpack(endian + fmt, b[i * 8:i * 8 + 8])
                    vals.append(Fraction(num, den) if den else Fraction(0))
            else:
                vals = list(struct.unpack(endian + fmt * n, b))
        return vals[0] if n == 1 else vals
    except Exception:
        return None


def _read_tiff_exif(data: bytes) -> dict[int, Any]:
    if len(data) < 8:
        return {}
    if data[:2] == b"II":
        endian = "<"
    elif data[:2] == b"MM":
        endian = ">"
    else:
        return {}
    tiff = 0
    ifd0 = struct.unpack(endian + "I", data[4:8])[0]
    tags = _read_ifd(data, tiff, ifd0, endian)
    # 主图宽度/高度（用于 TIFF 类文件）
    try:
        if 0x0100 in tags or 0x0101 in tags:
            pass
    except Exception:
        pass
    return tags


def raw_exif_tags(path: str, max_header: int = 4 * 1024 * 1024) -> dict[int, Any]:
    """从 ARW/DNG（TIFF 容器）读取 EXIF，MakerNote 可能位于文件后部，因此按需读大块。"""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read(min(size, max_header))
        tags = _read_tiff_exif(data)
        return tags
    except Exception:
        return {}


# --------------------------------------------------------------------------- 格式化

def _scalar(v: Any) -> Any:
    """把 1 元素列表统一成单值（Pillow 的 (值,除数) 元组由 _ratio 处理）。"""
    if isinstance(v, (list, tuple)) and len(v) == 1:
        return v[0]
    return v


def _ratio(v: Any) -> Optional[float]:
    """把各种数值表示（数字 / Fraction / (值,除数) / 列表）转成 float。"""
    if isinstance(v, (list, tuple)):
        if len(v) == 2 and not isinstance(v[1], Fraction):
            a, b = _ratio(v[0]), _ratio(v[1])
            if a is not None and b:
                return a / b
        if v:
            return _ratio(v[0])
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_fraction(v: Any, digits: int = 1) -> str:
    f = _ratio(v)
    if f is None:
        return str(v)
    if f == int(f):
        return str(int(f))
    return f"{f:.{digits}f}"


def _fmt_shutter(v: Any) -> str:
    f = _ratio(v)
    if f is None or f <= 0:
        return ""
    if f >= 1:
        return f"{f:g} 秒"
    return f"1/{int(round(1.0 / f))} 秒"


def _fmt_time(v: Any) -> str:
    if not v:
        return ""
    s = str(v).strip()
    if len(s) >= 19 and s[4] == ":" and s[7] == ":":
        return s[:19].replace(":", "-", 2)
    return s


def _fmt_gps(tags: dict[int, Any]) -> str:
    lat = tags.get(0x0002)
    lon = tags.get(0x0004)
    if not lat or not lon:
        return ""
    try:
        def deg(v):
            parts = [_scalar(x) for x in v]
            return float(parts[0]) + float(parts[1]) / 60.0 + float(parts[2]) / 3600.0
        la, lo = deg(lat), deg(lon)
        la *= -1 if tags.get(0x0001) in ("S", b"S") else 1
        lo *= -1 if tags.get(0x0003) in ("W", b"W") else 1
        return f"{la:.6f}, {lo:.6f}"
    except Exception:
        return ""


# --------------------------------------------------------------------------- 对外结构

@dataclass
class ExifData:
    items: list[tuple[str, str]] = field(default_factory=list)

    def get(self, label: str, default: str = "") -> str:
        for k, v in self.items:
            if k == label:
                return v
        return default

    def as_pairs(self) -> list[tuple[str, str]]:
        return self.items

    def empty(self) -> bool:
        return not self.items


def _items_from_tags(tags: dict[int, Any], extra: dict[str, str] | None = None) -> ExifData:
    # 不在这里做整体 _scalar 转换：GPS（3 组分数）、ISO 列表等本身是有序多值
    g = lambda tag: tags.get(tag)  # noqa: E731
    make = str(_scalar(g(0x010F)) or "").strip()
    model = str(_scalar(g(0x0110)) or "").strip()
    if make and model and model.upper().startswith(make.upper()):
        make = ""
    camera = " ".join(x for x in (make, model) if x)

    items: list[tuple[str, str]] = []

    def add(label: str, value: Any) -> None:
        if value is None:
            return
        s = str(value).strip()
        if s:
            items.append((label, s))

    add("相机", camera)
    add("镜头", g(0xA434) or (extra or {}).get("Lens"))
    add("拍摄时间", _fmt_time(g(0x9003) or g(0x0132)))
    iso = _scalar(g(0x8827)) or _scalar(g(0x8833)) or _scalar(g(0x8832))
    if isinstance(iso, (list, tuple)):
        iso = iso[0] if len(iso) else None
    try:
        iso = int(iso) if iso is not None else None
    except (TypeError, ValueError):
        iso = None
    add("ISO", f"ISO {iso}" if iso else None)
    fnum = _ratio(g(0x829D))
    add("光圈", f"f/{_fmt_fraction(fnum, 1)}" if fnum else None)
    add("快门", _fmt_shutter(g(0x829A)))
    fl = _ratio(g(0x920A))
    add("焦距", f"{_fmt_fraction(fl)} mm" if fl else None)
    f35 = _ratio(g(0xA405))
    add("等效焦距", f"{int(f35)} mm" if f35 else None)
    ev = _ratio(g(0x9204))
    if ev is not None:
        add("曝光补偿", f"{'+' if ev > 0.05 else ''}{0.0 if abs(ev) < 0.05 else ev:.1f} EV")
    wb = g(0xA403)
    wb_map = {0: "自动", 1: "手动"}
    if g(0x9208) and int(g(0x9208) or 0) > 1:
        wb_map.setdefault(255, "自定义")
    if wb is not None:
        add("白平衡", wb_map.get(int(wb), str(wb)))
    add("色彩空间", {1: "sRGB", 65535: "Adobe RGB"}.get(int(g(0xA001) or 0), None) if g(0xA001) else None)
    width, height = g(0xA002), g(0xA003)
    if width and height:
        add("分辨率", f"{int(width)} × {int(height)}")
    add("方向", {1: "标准", 2: "镜像", 3: "旋转 180°", 4: "上下翻转", 5: "旋转 90°+镜像",
                6: "旋转 90°", 7: "旋转 270°+镜像", 8: "旋转 270°"}.get(int(g(0x0112) or 1)))
    add("机身序列号", g(0xA431))
    add("镜头序列号", g(0xA435))
    add("GPS", _fmt_gps(tags))
    add("软件", g(0x0131))
    for k, v in (extra or {}).items():
        if k != "Lens":
            add(k, v)
    return ExifData(items)


def read_exif(path: str) -> ExifData:
    """读取 EXIF。读取失败时返回空结构，由调用方补充文件信息。"""
    if not path or not os.path.isfile(path):
        return ExifData()
    ext = os.path.splitext(path)[1].lower()
    extra: dict[str, str] = {}
    try:
        with open(path, "rb") as f:
            head = f.read(16)
        fmt_label = {".arw": "RAW (ARW)", ".dng": "RAW (DNG)", ".heic": "HEIF", ".heif": "HEIF",
                     ".hif": "HEIF", ".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF",
                     ".tiff": "TIFF", ".png": "PNG"}.get(ext)
        # RAW 是 TIFF 容器，Pillow 读不出 EXIF，直接用内置解析器
        if ext in (".arw", ".dng", ".tif", ".tiff"):
            tags = raw_exif_tags(path)
            if fmt_label:
                extra["格式"] = fmt_label
            if not tags.get(0xA002) and tags.get(0x0100) and tags.get(0x0101) and tags.get(0x0100) > 8:
                extra.setdefault("像素", f"{tags.get(0x0100)} × {tags.get(0x0101)}")
            return _items_from_tags(tags, extra)
        if _PIL:
            try:
                with Image.open(path) as im:
                    try:
                        ex = im.getexif()
                    except Exception:
                        ex = None
                    if ex is not None and len(ex):
                        tags: dict[int, Any] = {}
                        for k, v in ex.items():
                            tags[int(k)] = v
                        for sub in (0x8769, 0x8825):
                            try:
                                for k, v in (ex.get_ifd(sub) or {}).items():
                                    tags[int(k)] = v
                            except Exception:
                                pass
                        if im.size:
                            tags.setdefault(0xA002, im.size[0])
                            tags.setdefault(0xA003, im.size[1])
                        if fmt_label:
                            extra["格式"] = fmt_label
                        return _items_from_tags(tags, extra)
            except Exception:
                pass
        # 兜底：手工解析 TIFF 头（JPEG 里的 EXIF 块以 "Exif\0\0" 开头）
        with open(path, "rb") as f:
            data = f.read(4 * 1024 * 1024)
        start = 0
        if data[:2] != b"II" and data[:2] != b"MM":
            j = data.find(b"Exif\x00\x00", 0, 65536)
            if j >= 0:
                start = j + 6
        tags = _read_tiff_exif(data[start:])
        if fmt_label:
            extra["格式"] = fmt_label
        return _items_from_tags(tags, extra)
    except Exception:
        return ExifData()


# --------------------------------------------------------------------------- 预览信息（单行摘要）

def summary_line(exif: ExifData) -> str:
    parts = [exif.get("相机"), exif.get("镜头"), exif.get("光圈"), exif.get("快门"),
             exif.get("ISO"), exif.get("焦距"), exif.get("拍摄时间")]
    return "  ·  ".join(p for p in parts if p)


def file_facts(path: str) -> list[tuple[str, str]]:
    """与 EXIF 合并显示的文件信息。"""
    out: list[tuple[str, str]] = []
    try:
        st = os.stat(path)
        out.append(("文件名", os.path.basename(path)))
        from .core import human_size
        out.append(("文件大小", human_size(st.st_size)))
        out.append(("保存时间", datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")))
        out.append(("所在目录", os.path.dirname(path)))
    except OSError:
        pass
    return out


def empty_exif_text(path: str) -> str:
    return "未找到可读的 EXIF 信息（可能是导出/截图文件，或视频代理）。"
