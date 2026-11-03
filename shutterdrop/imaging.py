import io
import os
import struct
import sys
import traceback
from typing import Optional

try:
    from PIL import Image, ImageOps, ImageDraw
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False

_HEIF_HOOK = None


def register_heif() -> bool:
    """如果装了 pillow-heif，就注册 HEIF 解码器（可选增强）。"""
    global _HEIF_HOOK
    try:
        import pillow_heif  # type: ignore
        pillow_heif.register_heif_opener()
        _HEIF_HOOK = "pillow_heif"
        return True
    except Exception:
        _HEIF_HOOK = None
        return False


def heif_supported() -> bool:
    return _HEIF_HOOK is not None


def pil_available() -> bool:
    return _PIL


# --------------------------------------------------------------------------- HEIF 容器

def _read_boxes(data: bytes, start: int = 0, end: Optional[int] = None) -> list:
    """把一段字节拆成 [(type, payload_start, payload_end)]。"""
    end = len(data) if end is None else end
    out = []
    pos = start
    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            break
        out.append((typ, pos + header, pos + size))
        pos += size
    return out


def _u(b: bytes) -> int:
    return int.from_bytes(b, "big") if b else 0


def heif_first_image_box(data: bytes) -> Optional[bytes]:
    """从 HEIF/HEIC 里取出主图（或第一张图）的压缩数据（hvc1 / hev1 / jpeg item）。"""
    try:
        iloc_items: list = []        # (item_id, offset, length, base)
        types: dict = {}
        primary = None
        for typ, s, e in _read_boxes(data):
            if typ != b"meta":
                continue
            # meta 是 full box：前 4 字节是 version/flags
            children = _read_boxes(data, s + 4, e)
            for ctyp, cs, ce in children:
                sub = data[cs:ce]
                if ctyp == b"pitm":
                    ver = sub[0]
                    primary = struct.unpack(">H", sub[4:6])[0] if ver == 0 else struct.unpack(">I", sub[4:8])[0]
                elif ctyp == b"iinf":
                    ver = sub[0]
                    p = 4 if ver == 0 else 6
                    count = struct.unpack(">H", sub[p:p + 2])[0]
                    p += 2
                    for _ in range(count):
                        if p + 8 > len(sub):
                            break
                        isize = struct.unpack(">I", sub[p:p + 4])[0]
                        ityp = sub[p + 4:p + 8]
                        payload = sub[p + 8:p + max(isize, 8)]
                        if ityp == b"infe" and len(payload) >= 8:
                            iid = struct.unpack(">H", payload[4:6])[0]
                            types[iid] = payload[8:].split(b"\x00", 1)[0].decode("ascii", "replace")
                        p += max(isize, 8)
                elif ctyp == b"iloc":
                    iloc_items.extend(_parse_iloc(sub))
        if not iloc_items:
            return None
        order = sorted(iloc_items, key=lambda it: 0 if it[0] == primary else 1)
        for item_id, off, ln, base in order:
            t = types.get(item_id, "")
            if not (t.startswith("hvc1") or t.startswith("hev1") or t == "jpeg"):
                continue
            start = base + off
            if 0 <= start and ln > 0 and start + ln <= len(data):
                return data[start:start + ln]
        return None
    except Exception:
        return None


def _parse_iloc(sub: bytes) -> list:
    out = []
    ver = sub[0]
    off_size = sub[4] & 0x0F
    len_size = sub[5] & 0x0F
    base_size = sub[6] & 0x0F
    idx_size = (sub[6] >> 4) & 0x0F if ver in (1, 2) else 0
    p = 6
    if ver in (1, 2):
        p += 2
    if ver < 2:
        entries = struct.unpack(">H", sub[p:p + 2])[0]
        if entries == 0:
            # 部分 MP4 风格的封装把 item_count 写成 4 字节，这里兼容一下
            entries = struct.unpack(">I", sub[p:p + 4])[0]
            p += 4
        else:
            p += 2
    else:
        entries = struct.unpack(">I", sub[p:p + 4])[0]
        p += 4
    for _ in range(entries):
        if ver < 2:
            item_id = struct.unpack(">H", sub[p:p + 2])[0]
            p += 2
        else:
            item_id = struct.unpack(">I", sub[p:p + 4])[0]
            p += 4
        if ver in (1, 2):
            p += 2                      # construction_method
        p += 2                          # data_reference_index
        base = _u(sub[p:p + base_size])
        p += base_size
        if p + 2 > len(sub):
            break
        ext_count = struct.unpack(">H", sub[p:p + 2])[0]
        p += 2
        for _ in range(ext_count):
            p += idx_size
            if p + off_size + len_size > len(sub):
                break
            off = _u(sub[p:p + off_size])
            p += off_size
            ln = _u(sub[p:p + len_size])
            p += len_size
            out.append((item_id, off, ln, base))
    return out


def extract_embedded_jpeg(path: str) -> Optional[bytes]:
    """在 HEIF / ARW / JPEG 里找出可显示的 JPEG 数据（用于预览）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
            if head[:2] == b"\xff\xd8":
                return None                     # 本身就是 JPEG
            f.seek(0)
            data = f.read()
        if head[4:8] == b"ftyp":
            payload = heif_first_image_box(data)
            if payload and payload[:2] == b"\xff\xd8":
                return payload
            if payload and not heif_supported():
                return payload                  # 交给 Pillow 尝试解码（hvc1 不行时会失败）
        # TIFF / ARW：取最大的内嵌 JPEG
        best = None
        idx = 0
        while True:
            i = data.find(b"\xff\xd8\xff", idx)
            if i < 0:
                break
            j = data.find(b"\xff\xd9", i + 3)
            if j > 0:
                cand = data[i:j + 2]
                if best is None or len(cand) > len(best):
                    best = cand
            idx = i + 3
        return best
    except Exception:
        return None


# --------------------------------------------------------------------------- 图像加载

def load_image(path: str, max_side: int = 2200) -> Optional["Image.Image"]:
    """读取图片，按 EXIF 方向校正并缩放到 max_side 以内。"""
    if not _PIL or not path or not os.path.isfile(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    img = None
    try:
        if ext in (".heic", ".heif", ".hif") and not heif_supported():
            raise RuntimeError("heif-unsupported")
        img = Image.open(path)
        img.load()
    except Exception:
        img = None
    if img is None:
        raw = extract_embedded_jpeg(path)
        if raw:
            try:
                img = Image.open(io.BytesIO(raw))
                img.load()
            except Exception:
                img = None
    if img is None:
        return None
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode not in ("RGB", "L"):
        try:
            img = img.convert("RGB")
        except Exception:
            pass
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    return img


def placeholder(h: int, w: int, filename: str, reason: str = "无法预览") -> "Image.Image":
    """给无法解码的文件（RAW / HEIF / 视频）生成一张占位图。"""
    h, w = max(60, h), max(60, w)
    img = Image.new("RGB", (w, h), (232, 234, 239))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 84], fill=(208, 212, 220))
    d.text((w // 2 - 40, 34), "NO PREVIEW", fill=(92, 97, 107))
    name = filename if len(filename) <= 46 else filename[:43] + "..."
    d.text((24, 120), name, fill=(70, 74, 82))
    d.text((24, 146), reason, fill=(112, 117, 126))
    d.text((24, h - 56), "文件已保存 · EXIF 仍可查看", fill=(132, 137, 146))
    return img


def make_thumbnail(path: str, max_side: int = 320) -> Optional["Image.Image"]:
    return load_image(path, max_side=max_side)
