"""界面冒烟测试：真实创建窗口，模拟相机上传，检查各页面能否正常渲染/刷新。

没有显示器时会自动跳过（退出码 0）。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    import tkinter as tk
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError as exc:
        print("SKIP 无可用的图形界面：", exc)
        return 0

    from shutterdrop.core import Settings
    from shutterdrop.app import AppController
    from shutterdrop.ui.main_window import MainWindow
    from shutterdrop.mock import make_photo
    from shutterdrop.ftpserver import TransferStarted, TransferProgress, TransferFinished

    work = os.path.join(ROOT, "_test", "ui_" + str(os.getpid()))
    photos = os.path.join(work, "photos")
    src = os.path.join(work, "src")
    os.makedirs(photos, exist_ok=True)
    os.makedirs(src, exist_ok=True)
    sample = make_photo(os.path.join(src, "DSC01001.JPG"), seed=1, size=(1600, 1067))

    cfg = Settings(ftp_port=24567, photo_dir=photos, preview_seconds=3, auto_open=True)
    root = tk.Tk()
    ctl = AppController(cfg)
    win = MainWindow(root, ctl)
    root.update()
    print("PASS 主窗口创建")

    # 各页面切换
    for page in ("settings", "help", "dashboard"):
        win.show_page(page)
        root.update()
        time.sleep(0.05)
        print("PASS 页面渲染：", page)

    # 模拟上传事件
    dest = os.path.join(photos, "DSC01001.JPG")
    import shutil
    shutil.copyfile(sample, dest)
    ctl._on_event(TransferStarted("x1", "/DSC01001.JPG", "DSC01001.JPG", dest, "192.168.1.50", 120000))
    ctl._on_event(TransferProgress("x1", 60000, 120000))
    root.update()
    win.events_apply_transfer()
    root.update()
    print("PASS 传输进度刷新：", win.lbl_tx_main.cget("text"))
    ctl._on_event(TransferFinished("x1", "/DSC01001.JPG", "DSC01001.JPG", dest,
                                   os.path.getsize(dest), 0.8, "192.168.1.50",
                                   started=time.time() - 0.8))
    for _ in range(30):
        root.update()
        time.sleep(0.05)
    print("PASS 照片入库，预览窗口：", win.preview.is_open(), "最近照片：", len(ctl.photos))
    if win.preview.is_open():
        win.preview._fill_exif(win.preview.entry)
        root.update()
        print("PASS 预览 EXIF 面板渲染")
    win.refresh_recent_from_disk()
    root.update()
    print("PASS 最近照片列表：", len(win._thumb_widgets))

    ok = True
    if not ctl.photos:
        ok = False
        print("FAIL 照片没有入库")
    if not win._thumb_widgets:
        ok = False
        print("FAIL 最近照片为空")
    try:
        win.preview.close()
    except Exception:
        pass
    try:
        win.on_close()
    except tk.TclError:
        pass
    import shutil as _sh
    _sh.rmtree(work, ignore_errors=True)
    if ok:
        print("✅ UI 冒烟测试通过")
        return 0
    print("❌ UI 冒烟测试失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
