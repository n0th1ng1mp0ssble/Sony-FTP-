"""ShutterDrop 启动入口（源码版直接运行，打包后即 ShutterDrop.exe）。

    python main.py                        # 正常启动
    python main.py --port 2121            # 临时指定 FTP 端口（不写入设置）
    python main.py --photo-dir D:\\Photos  # 临时指定保存目录
    python main.py --self-test            # 只启动 FTP 服务，不开界面（脚本联调用）

日志位置：优先写入程序所在目录的 shutterdrop.log（便携版 / 解压版可直接查看），
         程序目录不可写时回退到 %APPDATA%\\ShutterDrop\\shutterdrop.log。
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from shutterdrop import APP_NAME, APP_NAME_CN, VERSION          # noqa: E402
from shutterdrop import core                                    # noqa: E402
from shutterdrop.app import AppController                       # noqa: E402
from shutterdrop.core import Settings                           # noqa: E402

log = logging.getLogger("shutterdrop")


def _relaunch_with_utf8() -> None:
    """用 Python 的 UTF-8 模式重新拉起自己，避免极少数缺少代码页 65001 的系统启动即崩溃。

    只在「源码运行」时这样做。打包后的 exe 由 PyInstaller 引导程序接管参数，
    再传 -X utf8 会被忽略；打包版的 UTF-8 模式改由运行时钩子 pyi_utf8_hook.py 打开。
    """
    if getattr(sys, "frozen", False):
        return
    if sys.platform != "win32" or os.environ.get("SD_UTF8_OK") == "1":
        return
    env = dict(os.environ)
    env["SD_UTF8_OK"] = "1"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(APP_DIR, "main.py"),
                          *sys.argv[1:]], env=env, creationflags=flags)
    except OSError:
        return          # 拉不起来就按原模式继续运行
    os._exit(0)


def program_dir() -> str:
    """程序实际所在目录（打包成 exe 时是 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return APP_DIR


def pick_log_path() -> str:
    """日志优先放在程序目录（便携），不可写时用 %APPDATA%。"""
    candidate = os.path.join(program_dir(), "shutterdrop.log")
    try:
        with open(candidate, "a", encoding="utf-8"):
            pass
        return candidate
    except OSError:
        return core.LOG_PATH


def setup_logging(verbose: bool = False) -> str:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    path = pick_log_path()
    try:
        fh = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(fh)
    except OSError:
        pass
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
        sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(sh)
    logging.getLogger("shutterdrop.ftp").setLevel(logging.INFO)
    return path


def _attach_tk_error_handler(root) -> None:
    """把 Tk 回调里的异常写进日志，避免“界面没反应却查不到原因”。"""
    def report(exc, val, tb):
        logging.getLogger("shutterdrop.ui").error("界面回调出错", exc_info=(exc, val, tb))
    root.report_callback_exception = report


def self_test(settings: Settings) -> int:
    """不开界面，只开 FTP 服务，供脚本 / 自动化联调使用。"""
    ctl = AppController(settings)
    ok = ctl.start_server()
    print(f"FTP server {'started' if ok else 'FAILED'} on port {ctl.server.port}", flush=True)
    if not ok:
        print(ctl.server.error, flush=True)
        return 1
    try:
        import threading
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        ctl.stop()
    return 0


def main(argv=None) -> int:
    if argv is None and not getattr(sys, "frozen", False):
        _relaunch_with_utf8()
    parser = argparse.ArgumentParser(description=f"{APP_NAME}（{APP_NAME_CN}）· 索尼相机 FTP 照片实时接收")
    parser.add_argument("--port", type=int, default=None, help="本次运行的 FTP 端口（临时覆盖设置）")
    parser.add_argument("--photo-dir", type=str, default=None, help="本次运行的照片保存目录（临时覆盖）")
    parser.add_argument("--no-autostart", action="store_true", help="启动后不自动开启 FTP 服务")
    parser.add_argument("--self-test", action="store_true", help="只启动 FTP 服务、不开界面")
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    log_path = setup_logging(args.verbose)
    log.info("%s %s 启动（程序目录 %s，日志 %s）", APP_NAME, VERSION, program_dir(), log_path)

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # 高 DPI 清晰显示
    except Exception:
        pass

    settings = Settings().load()
    if args.port:
        settings.ftp_port = args.port
    if args.photo_dir:
        settings.photo_dir = os.path.abspath(args.photo_dir)
    settings.clamp()
    core.ensure_dir(settings.photo_dir)

    if args.self_test:
        return self_test(settings)

    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception:
        log.exception("无法创建界面")
        raise
    _attach_tk_error_handler(root)
    try:
        from shutterdrop.imaging import register_heif
        register_heif()
    except Exception:
        pass
    from shutterdrop.ui.main_window import MainWindow
    ctl = AppController(settings)
    win = MainWindow(root, ctl)
    ctl.start_detection()
    if settings.auto_start and not args.no_autostart:
        root.after(250, ctl.start_server)
    try:
        root.mainloop()
    finally:
        try:
            ctl.stop()
        except Exception:
            pass
        log.info("程序退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
