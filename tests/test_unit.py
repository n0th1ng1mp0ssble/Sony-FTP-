"""不依赖网络的单元测试：配置、路径处理、EXIF、HEIF 解析、图片加载、相机检测工具。"""
import io
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from shutterdrop import core, exif_reader as E, imaging
from shutterdrop.mock import exif_block, make_photo

WORK = os.path.join(ROOT, "_test", "unit_" + str(os.getpid()))
os.makedirs(WORK, exist_ok=True)
fails = []


def check(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def test_core():
    s = core.Settings()
    s.ftp_port = 99999
    s.preview_seconds = 99999
    s.detector_interval = 1 if hasattr(s, "detector_interval") else None
    s.clamp()
    check(s.ftp_port == 65535, "端口上限收敛")
    check(s.preview_seconds == 600, "预览秒数上限收敛")
    check(core.safe_filename("../../etc/passwd") == "passwd", "文件名去掉路径")
    check(core.safe_filename('a<b>c:d|e?f*g"h') == "a_b_c_d_e_f_g_h", "非法字符替换")
    check(core.safe_filename("DSC00001.JPG ") == "DSC00001.JPG", "去掉尾部空格")
    check(core.human_size(0) == "0 B" and core.human_size(1536) == "1.5 KB", "大小格式化")
    check(core.human_speed(2048) == "2.0 KB/s", "速度格式化")
    check(core.human_duration(75) == "1 分 15 秒", "时长格式化")
    subs = core.guess_camera_subnets(["192.168.1.20", "10.1.2.3"])
    check("192.168.1." in subs and "10.1.2." in subs, "网段推测")
    base = os.path.join(WORK, "photos")
    s.photo_dir = base
    s.date_subfolders = False
    s.keep_dir_structure = True
    p = s.subdir_for("DCIM/100MSDCF", 0)
    check(p == os.path.join(base, "DCIM", "100MSDCF"), "保留目录层级")
    s.date_subfolders = True
    p = s.subdir_for("", 0)
    check(os.path.dirname(p) == base and len(os.path.basename(p)) == 10, "日期子目录 " + os.path.basename(p))
    s.date_subfolders = False
    check(s.subdir_for("../a", 0) == base, "越级目录被丢弃")
    ok, why = core.valid_photo_dir(base)
    check(ok and why == "可用", "有效目录检查：" + why)
    ftxt = os.path.join(WORK, "file.txt")
    with open(ftxt, "w") as fh:
        fh.write("x")
    bad, why2 = core.valid_photo_dir(ftxt)
    check(not bad, "指向文件时目录无效：" + why2)
    # Settings 往返
    s.save = lambda: True
    d = s.to_dict()
    s2 = core.Settings.from_dict(d)
    check(s2.photo_dir == s.photo_dir and s2.preview_seconds == s.preview_seconds, "配置序列化往返")


def test_exif():
    p = make_photo(os.path.join(WORK, "exif.jpg"), seed=5, size=(1200, 800))
    ex = E.read_exif(p)
    d = dict(ex.items)
    check(d.get("相机") == "SONY ILCE-7M5", "相机型号：" + str(d.get("相机")))
    check(d.get("镜头", "").startswith("FE "), "镜头：" + str(d.get("镜头")))
    check(d.get("光圈", "").startswith("f/"), "光圈：" + str(d.get("光圈")))
    check(d.get("快门", "").endswith("秒"), "快门：" + str(d.get("快门")))
    check(d.get("ISO", "").startswith("ISO "), "ISO：" + str(d.get("ISO")))
    check(d.get("焦距", "").endswith(" mm"), "焦距：" + str(d.get("焦距")))
    check(d.get("分辨率") == "1200 × 800", "分辨率：" + str(d.get("分辨率")))
    check(d.get("格式") == "JPEG", "格式：" + str(d.get("格式")))
    check(bool(d.get("拍摄时间")), "拍摄时间：" + str(d.get("拍摄时间")))
    line = E.summary_line(ex)
    check("SONY ILCE-7M5" in line, "摘要行：" + line)
    # 没有 EXIF 的图
    from PIL import Image
    plain = os.path.join(WORK, "plain.png")
    Image.new("RGB", (64, 48), (10, 20, 30)).save(plain)
    ex2 = E.read_exif(plain)
    check(ex2.get("格式") == "PNG" and not ex2.empty(), "无 EXIF 图片也能给出格式")
    # 坏文件
    bad = os.path.join(WORK, "bad.jpg")
    open(bad, "wb").write(b"not an image")
    check(E.read_exif(bad).empty() or True, "坏文件不崩溃")


def _tiny_jpeg() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 10, 10)).save(b, "JPEG")
    return b.getvalue()


def _tiny_heif_bytes() -> bytes:
    """手工拼一个最小 HEIF：meta(hdlr/pitm/iinf/iloc) + mdat(内嵌 JPEG)。"""
    from PIL import Image
    jpeg = _tiny_jpeg()
    # 子盒
    def box(typ, payload):
        return struct.pack(">I", 8 + len(payload)) + typ + payload

    hdlr = box(b"hdlr", b"\x00" * 4 + b"pict" + b"\x00" * 12 + b"\x00")
    pitm = box(b"pitm", b"\x00\x00\x00\x00" + struct.pack(">H", 1))
    infe = box(b"infe", b"\x02\x00\x00\x00" + struct.pack(">H", 1) + b"\x00\x00" + b"jpeg" + b"\x00")
    iinf = box(b"iinf", b"\x00\x00\x00\x00" + struct.pack(">H", 1) + infe)
    # iloc v0: version/flags(4) + offset_size(1)=4 + length_size(1)=4 + base_offset_size(1)=0
    #           + reserved(1) + item_count(2)，然后每条：item_id(2) + data_ref(2) + extent_count(2)
    #           + extent：offset(4) + length(4)
    mdat_payload = jpeg

    def iloc_box(offset):
        payload = (b"\x00\x00\x00\x00" + b"\x04" + b"\x04" + b"\x00" + b"\x00" +
                   b"\x00\x01" +                                # item_count (MP4 4 字节)
                   b"\x00\x01" + b"\x00\x00" +                  # item_id, data_reference_index
                   b"\x00\x01" +                                # extent_count
                   struct.pack(">II", offset, len(mdat_payload)))
        return box(b"iloc", payload)

    # 先按 offset=0 算长度，再按真实 mdat 起点重算一次
    ftyp = box(b"ftyp", b"heic" + b"\x00\x00\x00\x00" + b"mif1heic")
    meta_len = len(box(b"meta", b"\x00\x00\x00\x00" + hdlr + pitm + iinf + iloc_box(0)))
    mdat_start = len(ftyp) + meta_len + 8
    iloc = iloc_box(mdat_start)
    meta = box(b"meta", b"\x00\x00\x00\x00" + hdlr + pitm + iinf + iloc)
    mdat = box(b"mdat", mdat_payload)
    return ftyp + meta + mdat


def test_heif():
    data = _tiny_heif_bytes()
    payload = imaging.heif_first_image_box(data)
    check(payload is not None and payload[:2] == b"\xff\xd8", "HEIF 容器里提取出内嵌 JPEG")
    p = os.path.join(WORK, "sample.heic")
    open(p, "wb").write(data)
    raw = imaging.extract_embedded_jpeg(p)
    check(raw is not None and raw[:2] == b"\xff\xd8", "extract_embedded_jpeg 处理 HEIC")
    img = imaging.load_image(p, max_side=200)
    check(img is not None and img.size == (8, 8), "HEIF 缩略图解码（无 pillow-heif 也能显示）")


def test_imaging():
    p = make_photo(os.path.join(WORK, "big.jpg"), seed=2, size=(3000, 2000))
    img = imaging.load_image(p, max_side=1200)
    check(img is not None and max(img.size) == 1200, "大图按比例缩放")
    thumb = imaging.make_thumbnail(p, 320)
    check(thumb is not None and max(thumb.size) == 320, "缩略图")
    ph = imaging.placeholder(400, 600, "DSC00001.ARW", "RAW")
    check(ph.size == (600, 400), "占位图尺寸")
    check(imaging.load_image(os.path.join(WORK, "nope.jpg")) is None, "不存在文件返回 None")
    # 伪造一个 ARW（TIFF 头 + 内嵌 JPEG）
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (1, 2, 3)).save(b, "JPEG")
    jp = b.getvalue()
    arw = b"II*\x00\x08\x00\x00\x00" + b"\x00" * 64 + jp + b"\x00" * 16
    ap = os.path.join(WORK, "fake.ARW")
    open(ap, "wb").write(arw)
    raw = imaging.extract_embedded_jpeg(ap)
    check(raw is not None and raw[:2] == b"\xff\xd8", "RAW 内的 JPEG 预览提取")
    im2 = imaging.load_image(ap, 300)
    check(im2 is not None, "RAW 预览图可加载")


def test_detector_helpers():
    from shutterdrop import detector
    check(detector.CAMERA_PORTS == (21, 15740, 64321), "相机端口列表")
    fake = detector.CameraDetector("127.0.0.1")
    res = fake._detect_once()
    check(res is not None and res.ip == "127.0.0.1" and res.reachable is False, "固定 IP 检测（本机未开 21）")


if __name__ == "__main__":
    print("单元测试目录：", WORK)
    test_core()
    test_exif()
    test_heif()
    test_imaging()
    test_detector_helpers()
    print()
    if fails:
        print(f"❌ {len(fails)} 项失败：")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("✅ 全部通过")
