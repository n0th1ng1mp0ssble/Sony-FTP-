"""把最终构建复制到 publish/（便携版、单文件版、zip），并清理调试残留。"""
import os
import shutil
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(ROOT, "publish")


def remove(path: str, retries: int = 5) -> bool:
    for _ in range(retries):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.remove(path)
            return True
        except OSError:
            time.sleep(0.5)
    return not os.path.exists(path)


def main() -> int:
    os.makedirs(PUB, exist_ok=True)
    portable_src = os.path.join(ROOT, "dist_onedir", "ShutterDrop-Portable")
    portable_dst = os.path.join(PUB, "ShutterDrop-Portable")
    remove(portable_dst)
    shutil.copytree(portable_src, portable_dst)
    shutil.copyfile(os.path.join(ROOT, "dist", "ShutterDrop.exe"),
                    os.path.join(PUB, "ShutterDrop.exe（单文件版）.exe"))

    # 便携版 zip
    import zipfile
    zp = os.path.join(ROOT, "ShutterDrop-Portable-Windows-new.zip")
    if os.path.exists(zp):
        os.remove(zp)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _dn, fs in os.walk(portable_src):
            for fn in fs:
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, os.path.dirname(portable_src)))
    pub_zip = os.path.join(PUB, "ShutterDrop-Portable-Windows.zip")
    remove(pub_zip, retries=2)
    try:
        shutil.copyfile(zp, pub_zip)
    except OSError as exc:
        pub_zip = os.path.join(PUB, "ShutterDrop-Portable-Windows-new.zip")
        shutil.copyfile(zp, pub_zip)
        print("旧 zip 被占用，已用新文件名：", os.path.basename(pub_zip), exc)

    for rel in ("ShutterDrop 使用说明.docx", "ShutterDrop.html", "README.md"):
        src = os.path.join(ROOT, rel)
        dst = os.path.join(PUB, "ShutterDrop 介绍与预览.html" if rel.endswith(".html") else rel)
        if os.path.exists(src):
            shutil.copyfile(src, dst)

    for name in os.listdir(PUB):
        if name.startswith("_"):
            remove(os.path.join(PUB, name))
    for name in ("debug.log", "shutterdrop.log", "shutterdrop-launcher.log"):
        remove(os.path.join(PUB, name))

    print("publish 内容：")
    for name in sorted(os.listdir(PUB)):
        p = os.path.join(PUB, name)
        size = (sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs)
                if os.path.isdir(p) else os.path.getsize(p))
        print(f"  {name:42s} {size / 1024 / 1024:6.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
