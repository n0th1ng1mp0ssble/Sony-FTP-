"""启动打包好的程序、检查窗口是否出现、用模拟相机上传一张并核对保存结果。

    python tests/test_packaged.py             # 测便携版（dist_onedir 与 publish 各一份）
    python tests/test_packaged.py --onefile   # 顺便测单文件版（需要能解压到临时目录）
"""
import ctypes
import os
import socket
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DETACHED = 0x08
NO_WINDOW = 0x08000000
WORK = os.path.join(ROOT, "_test_packaged")
u = ctypes.windll.user32


def window_titles(prefix="ShutterDrop ·"):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            if b.value.startswith(prefix):
                found.append((h, b.value))
        return True

    u.EnumWindows(cb, 0)
    return found


def kill_tree(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def check_build(label, exe, port):
    from shutterdrop.mock import make_photo, SimCamera
    photos = os.path.join(WORK, label, "photos")
    os.makedirs(photos, exist_ok=True)
    ph = make_photo(os.path.join(WORK, label, "src.JPG"), seed=4, size=(1600, 1067))
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("SD_UTF8_OK", None)
    log = os.path.join(WORK, label, "stdout.txt")
    before = len(window_titles())
    with open(log, "wb") as fh:
        proc = subprocess.Popen([exe, "--port", str(port), "--photo-dir", photos],
                                stdout=fh, stderr=subprocess.STDOUT, env=env, creationflags=DETACHED)
    ok_win = False
    t0 = time.time()
    try:
        while time.time() - t0 < 60:
            if len(window_titles()) > before:
                ok_win = True
                break
            time.sleep(0.4)
        print(f"  {label}: 窗口出现={ok_win}（{time.time() - t0:.1f} 秒）")
        if ok_win:
            t1 = time.time()
            while time.time() - t1 < 20 and not port_open(port):
                time.sleep(0.2)
            try:
                SimCamera(port=port).upload(ph, remote_name="DSC00001.JPG", remote_dir="DCIM/100MSDCF")
                time.sleep(1.2)
            except Exception as exc:
                print(f"  {label}: 上传失败 {exc}")
        files = [os.path.relpath(os.path.join(dp, f), photos) for dp, _dn, fs in os.walk(photos) for f in fs]
        print(f"  {label}: 保存的文件 {files}")
        return ok_win and any(f.upper().endswith("DSC00001.JPG") for f in files)
    finally:
        kill_tree(proc.pid)
        time.sleep(1.5)
        ldir = os.path.dirname(exe)
        for name in ("shutterdrop.log", "shutterdrop-launcher.log"):
            lp = os.path.join(ldir, name)
            if os.path.exists(lp):
                try:
                    tail = open(lp, encoding="utf-8", errors="replace").read().strip().splitlines()[-2:]
                    print(f"  {label}: {name} -> {' | '.join(tail)}")
                    os.remove(lp)
                except OSError:
                    pass


def main():
    os.makedirs(WORK, exist_ok=True)
    targets = [
        ("便携版(dist_onedir)", os.path.join(ROOT, "dist_onedir", "ShutterDrop-Portable", "ShutterDrop.exe"), 27911),
    ]
    pub = os.path.join(ROOT, "publish", "ShutterDrop-Portable", "ShutterDrop.exe")
    if os.path.exists(pub):
        targets.append(("便携版(publish)", pub, 27912))
    if "--onefile" in sys.argv:
        targets.append(("单文件版", os.path.join(ROOT, "dist", "ShutterDrop.exe"), 27913))
    results = {}
    for label, exe, port in targets:
        if not os.path.exists(exe):
            print("  MISSING", exe)
            results[label] = False
            continue
        print(f"测试 {label}：{exe}")
        results[label] = check_build(label, exe, port)
    print()
    ok = True
    for k, v in results.items():
        print(("PASS " if v else "FAIL ") + k)
        ok = ok and v
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
