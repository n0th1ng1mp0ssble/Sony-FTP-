"""在子进程里跑 FTP 服务器，父进程用主动模式（PORT）上传，验证环境无关的兼容性。"""
import json
import os
import subprocess
import sys
import textwrap
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
WORK = os.path.join(ROOT, "_test", "port_child")
os.makedirs(WORK, exist_ok=True)
PHOTOS = os.path.join(WORK, "photos2")
os.makedirs(PHOTOS, exist_ok=True)
SRC = os.path.join(WORK, "sample.JPG")
RESULT = os.path.join(WORK, "result.json")

SERVER = textwrap.dedent(f'''
    import json, os, sys, time
    sys.path.insert(0, {ROOT!r})
    from shutterdrop.core import Settings
    from shutterdrop.ftpserver import FtpServer
    srv = FtpServer(Settings(ftp_port=26777, photo_dir={PHOTOS!r}))
    ok = srv.start()
    with open({RESULT!r}, "w") as f:
        json.dump({{"started": ok, "port": srv.port, "error": srv.error}}, f)
    time.sleep(40)
    srv.stop()
''')


def main():
    from shutterdrop.mock import make_photo
    if not os.path.exists(SRC):
        make_photo(SRC, seed=2, size=(900, 600))
    script = os.path.join(WORK, "server_child.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(SERVER)
    if os.path.exists(RESULT):
        os.remove(RESULT)
    proc = subprocess.Popen([sys.executable, script], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    try:
        t0 = time.time()
        while not os.path.exists(RESULT) and time.time() - t0 < 20:
            time.sleep(0.1)
        info = json.load(open(RESULT))
        print("child server:", info)
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_port_client
        for strict in (True, False):
            name = "PORT_STRICT.JPG" if strict else "PORT_PLAIN.JPG"
            try:
                log = test_port_client.port_mode_upload("127.0.0.1", info["port"], SRC, name,
                                                        strict_order=strict)
                print(f"strict={strict} OK ->", [x for x in log if x.startswith(("150", "226"))])
            except Exception as exc:
                print(f"strict={strict} FAIL: {exc!r}")
            time.sleep(0.3)
        time.sleep(0.5)
        files = sorted(os.listdir(PHOTOS))
        print("files:", files)
        ok = "PORT_STRICT.JPG" in files and "PORT_PLAIN.JPG" in files
        print("RESULT:", "PASS 主动模式两种顺序都成功" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
