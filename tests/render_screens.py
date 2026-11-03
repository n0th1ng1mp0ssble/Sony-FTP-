"""把各页面渲染成 PNG，便于在没有人工看屏幕的情况下检查界面效果。

    python tests/render_screens.py

使用 Windows 的 PrintWindow + BitBlt 抓取窗口（不需要第三方库）。
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "preview_screens")
os.makedirs(OUT, exist_ok=True)


def grab(hwnd, path):
    """用 PrintWindow + BitBlt 把窗口渲染成图片。"""
    from PIL import Image
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    try:
        user32.AllowSetForegroundWindow(-1)
    except Exception:
        pass
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False
    hdc_screen = user32.GetDC(0)
    hdc = gdi32.CreateCompatibleDC(hdc_screen)
    bmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc, bmp)
    if not user32.PrintWindow(hwnd, hdc, 2):
        user32.PrintWindow(hwnd, hdc, 0)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(0, hdc_screen)
    return True


def main():
    import shutil
    import tkinter as tk
    from shutterdrop.core import Settings
    from shutterdrop.app import AppController, ActiveTransfer, PhotoEntry
    from shutterdrop.ui.main_window import MainWindow
    from shutterdrop.mock import make_photo

    work = os.path.join(ROOT, "_test", "shots")
    photos = os.path.join(work, "photos")
    os.makedirs(photos, exist_ok=True)
    sample = make_photo(os.path.join(work, "DSC01024.JPG"), seed=1, size=(1600, 1067))
    dest = os.path.join(photos, "DSC01024.JPG")
    shutil.copyfile(sample, dest)

    cfg = Settings(ftp_port=2121, photo_dir=photos, preview_seconds=8)
    root = tk.Tk()
    ctl = AppController(cfg)
    win = MainWindow(root, ctl)
    root.update()
    root.deiconify()
    root.attributes("-topmost", True)
    time.sleep(1.0)
    root.update()

    # 演示：已收到一张照片 + 传输完成
    entry = PhotoEntry(path=dest, filename="DSC01024.JPG", size=os.path.getsize(dest),
                       origin="192.168.1.42", received=time.time())
    ctl.photos.appendleft(entry)
    win.add_thumb(entry, first=True)
    t = ActiveTransfer("demo", "/DCIM/100MSDCF/DSC01024.JPG", "DSC01024.JPG", dest,
                       "192.168.1.42", total=os.path.getsize(dest), received=os.path.getsize(dest))
    t.started = time.time() - 1.3
    t.finished = time.time()
    ctl.transfers = [t]
    win.events_apply_transfer()
    win._apply_status("相机已连接", "ok")
    root.update()
    time.sleep(0.5)
    root.update()
    hwnd = int(root.wm_frame(), 16)
    grab(hwnd, os.path.join(OUT, "01_dashboard.png"))
    print("saved 01_dashboard")

    # 实时预览窗
    win.preview.show(entry, 8, "window")
    for _ in range(20):
        root.update()
        time.sleep(0.05)
    win.preview._fit_image()
    win.preview.remaining = win.preview.total * 0.62
    win.preview._update_countdown()
    root.update()
    time.sleep(0.4)
    root.update()
    grab(int(win.preview.win.wm_frame(), 16), os.path.join(OUT, "02_realtime_preview.png"))
    print("saved 02_realtime_preview")
    win.preview.close()
    root.update()

    # 设置页
    win.show_page("settings")
    root.update()
    time.sleep(0.5)
    root.update()
    grab(hwnd, os.path.join(OUT, "03_settings_ftp.png"))
    sp = win.pages["settings"]
    sp.canvas.yview_moveto(0.42)
    root.update()
    time.sleep(0.5)
    root.update()
    grab(hwnd, os.path.join(OUT, "04_settings_preview.png"))
    sp.canvas.yview_moveto(1.0)
    root.update()
    time.sleep(0.5)
    root.update()
    grab(hwnd, os.path.join(OUT, "05_settings_bottom.png"))
    print("saved settings pages")

    # 帮助页
    win.show_page("help")
    root.update()
    time.sleep(0.5)
    root.update()
    grab(hwnd, os.path.join(OUT, "06_help_top.png"))
    hp = win.pages["help"]
    canvases = [w for w in hp.winfo_children() if isinstance(w, tk.Canvas)]
    if canvases:
        canvases[0].yview_moveto(0.30)
        root.update()
        time.sleep(0.5)
        root.update()
        grab(hwnd, os.path.join(OUT, "07_help_bottom.png"))
    print("saved help pages")
    ctl.stop()
    root.destroy()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
