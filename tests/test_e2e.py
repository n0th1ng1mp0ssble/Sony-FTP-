"""端到端测试：真实启动 FTP 服务器并模拟相机上传（被动 / 主动 / EPSV / 断点 / 中文名等）。

注意：本测试需要本机网络回环可用；自动化环境里如果回环受限会自动跳过网络部分。
"""
import os
import shutil
import socket
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shutterdrop.core import Settings, human_size          # noqa: E402
from shutterdrop.ftpserver import FtpServer, TransferFinished, TransferStarted, TransferProgress  # noqa: E402
from shutterdrop.mock import SimCamera, make_photo          # noqa: E402
from shutterdrop import exif_reader as E                    # noqa: E402

WORK = os.path.join(ROOT, "_test", "e2e_" + str(os.getpid()))
events = []
lock = threading.Lock()
failures = []


def on_event(ev):
    with lock:
        events.append(ev)


def check(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def wait_finished(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with lock:
            fin = [e for e in events if isinstance(e, TransferFinished)]
        if fin:
            return fin
        time.sleep(0.05)
    return []


def reset():
    with lock:
        events.clear()


def loopback_ok() -> bool:
    """有些受限环境禁止进程自连回环端口，这里先探测一次。"""
    srv = socket.socket()
    try:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(2)
        port = srv.getsockname()[1]
        try:
            c = socket.create_connection(("127.0.0.1", port), timeout=2)
            c.close()
            return True
        except OSError:
            return False
        finally:
            srv.close()
    except OSError:
        return False


def main():
    print("测试目录：", WORK)
    shutil.rmtree(WORK, ignore_errors=True)
    photos = os.path.join(WORK, "src")
    os.makedirs(photos, exist_ok=True)
    p1 = make_photo(os.path.join(photos, "A7M50001.JPG"), seed=1, size=(4200, 2800))
    p2 = make_photo(os.path.join(photos, "A7M40002.JPG"), seed=2, size=(4608, 3072), model="ILCE-7M4")
    p3 = make_photo(os.path.join(photos, "中文名字.JPG"), seed=3, size=(1600, 1067))
    big = os.path.join(photos, "BIG0001.JPG")
    with open(big, "wb") as f:
        f.write(open(p1, "rb").read() + os.urandom(6 * 1024 * 1024))

    dst = os.path.join(WORK, "photos")
    cfg = Settings(ftp_port=23456, ftp_user="sony", ftp_password="sony1234",
                   photo_dir=dst, keep_dir_structure=True)
    server = FtpServer(cfg, on_event=on_event)
    ok = server.start()
    check(ok, f"服务器启动于端口 {server.port}")
    if not ok:
        print(server.error)
        return 1
    if not loopback_ok():
        print("SKIP 当前环境禁止回环连接，跳过网络传输部分（服务器启动测试已通过）")
        server.stop()
        print("✅ 服务器生命周期测试通过")
        return 0

    # 1) 基础上传（被动 PASV）
    reset()
    cam = SimCamera(port=server.port)
    cam.upload(p1, remote_name="DSC00001.JPG")
    fin = wait_finished()
    check(len(fin) == 1 and fin[0].ok, "PASV 上传成功")
    if fin:
        path = fin[0].path
        check(os.path.isfile(path) and open(path, "rb").read() == open(p1, "rb").read(),
              "落盘内容与源文件一致")
        check(fin[0].size == os.path.getsize(p1), f"大小一致 {human_size(fin[0].size)}")
        ex = E.read_exif(path)
        check(ex.get("相机") == "SONY ILCE-7M5", "EXIF 相机型号：" + ex.get("相机"))
        check(ex.get("光圈", "").startswith("f/"), "EXIF 光圈：" + ex.get("光圈"))
        check("秒" in ex.get("快门", ""), "EXIF 快门：" + ex.get("快门"))
        check(ex.get("ISO", "").startswith("ISO"), "EXIF ISO：" + ex.get("ISO"))
        check("mm" in ex.get("焦距", ""), "EXIF 焦距：" + ex.get("焦距"))
        check(ex.get("镜头") == "FE 24-70mm F2.8 GM II", "EXIF 镜头：" + ex.get("镜头"))
        from shutterdrop.imaging import load_image
        img = load_image(path, 800)
        check(img is not None and max(img.size) == 800, "预览图解码并缩放成功")

    # 2) 进度事件
    prog = [e for e in events if isinstance(e, TransferProgress)]
    check(len(prog) >= 1, f"收到进度事件 {len(prog)} 个")

    # 3) 相机目录结构 + EPSV（A7M5 风格）
    reset()
    cam5 = SimCamera(port=server.port, use_epsv=True)
    cam5.upload(p2, remote_name="DSC00002.JPG", remote_dir="DCIM/100MSDCF")
    fin = wait_finished()
    check(len(fin) == 1 and fin[0].ok and "DCIM" in (fin[0].path or ""),
          "EPSV + 目录层级上传：" + (fin[0].path or "").replace(WORK, "~"))
    check(os.path.basename(fin[0].path if fin else "") == "DSC00002.JPG", "保留文件名")

    # 4) 主动模式（PORT）：两种数据连接顺序都要支持
    reset()
    from test_port_client import port_mode_upload
    for strict, label in ((True, "主动模式（PORT 后先连数据端口）"),
                          (False, "主动模式（收到 150 后再连）")):
        try:
            fname = "PORT_STRICT.JPG" if strict else "PORT_PLAIN.JPG"
            log = port_mode_upload("127.0.0.1", server.port, p3, fname, strict_order=strict)
            wait_finished()
            dst_port = os.path.join(dst, fname)
            ok = (any(line.startswith("226") for line in log) and os.path.exists(dst_port)
                  and open(dst_port, "rb").read() == open(p3, "rb").read())
            check(ok, label + " 上传成功")
        except Exception as exc:
            check(False, f"{label} 异常：{exc}")

    # 5) 中文文件名
    reset()
    cam.upload(p3, remote_name="中文文件名.JPG")
    fin = wait_finished()
    check(len(fin) == 1 and fin[0].ok and os.path.basename(fin[0].path).endswith("中文文件名.JPG"),
          "中文文件名正确落盘")

    # 6) 同名不覆盖时自动改名
    reset()
    cam.upload(p1, remote_name="DSC00001.JPG")
    fin = wait_finished()
    check(len(fin) == 1 and fin[0].ok and fin[0].path.endswith("DSC00001_1.JPG"),
          "同名文件自动加序号：" + (fin[0].path or "").split(os.sep)[-1])

    # 7) 大文件 + 限速下的进度
    reset()
    t = threading.Thread(target=cam.upload, args=(big, "BIG0001.JPG"),
                         kwargs={"throttle": 0.02, "chunk": 256 * 1024})
    t.start()
    time.sleep(0.8)
    with lock:
        prog = [e for e in events if isinstance(e, TransferProgress)]
        started = [e for e in events if isinstance(e, TransferStarted)]
    check(bool(started) and bool(prog), f"大文件有 started={len(started)} progress={len(prog)} 事件")
    t.join(120)
    fin = wait_finished()
    check(len(fin) == 1 and fin[0].ok and fin[0].size == os.path.getsize(big), "大文件完整传输")

    # 8) 断点续传（REST + STOR）
    import ftplib
    target = os.path.join(dst, "RESUME01.JPG")
    data_all = open(p1, "rb").read()
    open(target, "wb").write(data_all[:1000])
    reset()
    tail = os.path.join(photos, "tail.bin")
    open(tail, "wb").write(data_all[1000:])
    ftp = ftplib.FTP()
    ftp.connect("127.0.0.1", server.port)
    ftp.login("sony", "sony1234")
    with open(tail, "rb") as fh:
        ftp.storbinary("STOR RESUME01.JPG", fh, rest=1000)
    ftp.quit()
    wait_finished()
    check(os.path.getsize(target) == os.path.getsize(p1), "REST+STOR 续传后大小正确")
    check(open(target, "rb").read() == data_all, "续传内容与源文件一致")

    # 9) 拒绝非图片扩展名
    txt = os.path.join(photos, "evil.txt")
    open(txt, "w").write("hello")
    try:
        cam.upload(txt, remote_name="evil.txt")
        check(False, "非图片文件应被拒绝")
    except ftplib.error_perm as exc:
        check("553" in str(exc), "非图片文件被拒绝：" + str(exc))

    # 10) 越界路径
    ftp = ftplib.FTP()
    ftp.connect("127.0.0.1", server.port)
    ftp.login("sony", "sony1234")
    try:
        ftp.cwd("../../Windows")
        check(False, "越界 CWD 应失败")
    except ftplib.error_perm as exc:
        check(True, "越界 CWD 被拒绝：" + str(exc))
    finally:
        try:
            ftp.quit()
        except Exception:
            pass

    # 11) 错误密码
    try:
        SimCamera(port=server.port, password="wrong").upload(p1, "x.jpg")
        check(False, "错误密码应被拒绝")
    except ftplib.error_perm as exc:
        check("530" in str(exc), "错误密码被拒绝")

    # 12) ASCII 模式上传不损坏
    reset()
    cam.upload(p3, remote_name="ASCII0001.JPG", ascii_mode=True)
    fin = wait_finished()
    check(len(fin) == 1 and fin[0].ok and fin[0].size == os.path.getsize(p3),
          "ASCII 模式上传大小不变")
    check(open(fin[0].path, "rb").read() == open(p3, "rb").read() if fin else False,
          "ASCII 模式内容一致")

    server.stop()
    check(not server.running, "服务器已停止")

    print()
    if failures:
        print(f"❌ {len(failures)} 项失败")
        for f in failures:
            print(" -", f)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    rc = 1
    try:
        rc = main()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(rc)
