"""一键打包：生成「便携文件夹版 + 单文件版」，两者都带 C# 启动器与友好错误提示。

    python prepare_build_tools.py   # 首次打包前执行一次（下载 PyInstaller 等依赖）
    python build_exe.py

产物：
    dist_onedir/ShutterDrop-Portable/   ShutterDrop.exe（启动器）+ ShutterDrop.App.exe + _internal\\
    dist/ShutterDrop.exe               单文件版：启动器 + 压缩包，启动时解压到临时目录
"""
import os
import shutil
import struct
import zipfile
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "_tools", "site"))

import PyInstaller.__main__  # noqa: E402

sys.path.insert(0, ROOT)
from build_launcher import build_launcher  # noqa: E402

BUILD = os.path.join(ROOT, "_build")
ICON = os.path.join(ROOT, "assets", "shutterdrop.ico")
LAUNCH_LOG = "shutterdrop-launcher.log"


def base_args(heif: bool, console: bool) -> list:
    args = [
        os.path.join(ROOT, "main.py"),
        "--name", "ShutterDrop.App",
        "--noconfirm",
        "--clean",
        "--console" if console else "--windowed",
        "--hidden-import", "PIL._tkinter_finder",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pytest",
        "--exclude-module", "IPython",
        "--exclude-module", "setuptools",
        "--optimize", "1",
        "--paths", ROOT,
        "--collect-submodules", "shutterdrop",
    ]
    if heif:
        args += ["--hidden-import", "pillow_heif", "--collect-binaries", "pillow_heif"]
    if os.path.exists(ICON):
        args += ["--icon", ICON]
    # 运行时钩子：打包后的进程里启用 UTF-8 模式（命令行 -X utf8 对引导程序无效）
    args += ["--runtime-hook", os.path.join(ROOT, "pyi_utf8_hook.py")]
    # ttk 主题等 tcl 包脚本（PyInstaller 只带 .tm）
    tk = os.path.join(sys.base_prefix, "tcl", "tk8.6")
    if os.path.isdir(tk):
        for sub in ("ttk", "msgs", "images"):
            src = os.path.join(tk, sub)
            if os.path.isdir(src):
                args += ["--add-data", f"{src}{os.pathsep}_tk_data/{sub}"]
    return args


def collect_binaries(onedir_root: str) -> list:
    internal = os.path.join(onedir_root, "ShutterDrop.App", "_internal")
    bins = []
    if not os.path.isdir(internal):
        return []
    for name in os.listdir(internal):
        full = os.path.join(internal, name)
        if os.path.isfile(full) and os.path.splitext(name)[1].lower() in (".dll", ".pyd"):
            bins.append((full, "."))
    return bins


def copy_dir(src: str, dst: str) -> None:
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)


def write_readme(folder: str) -> None:
    with open(os.path.join(folder, "启动 ShutterDrop.bat"), "w", encoding="gbk", newline="\r\n") as f:
        f.write("@echo off\r\nchcp 65001 >nul\r\nrem ShutterDrop 便携版：双击运行（支持中文路径）\r\n")
        f.write('cd /d "%~dp0"\r\nstart "" "%~dp0ShutterDrop.exe"\r\n')
    with open(os.path.join(folder, "启动说明.txt"), "w", encoding="utf-8") as f:
        f.write(
            "ShutterDrop 便携版（文件夹版）\n============================\n\n"
            "1. 双击「启动 ShutterDrop.bat」或 ShutterDrop.exe 运行。\n"
            "   整个文件夹可以复制到别的 Windows 电脑，不需要安装任何东西。\n"
            "   ShutterDrop.exe（启动器）、ShutterDrop.App.exe（程序本体）、_internal 目录必须放在一起。\n"
            "2. 如果 Windows 提示「已保护你的电脑」，点「更多信息 → 仍要运行」。\n"
            "3. 第一次运行若弹出防火墙提示，请勾选「专用网络」并允许访问，否则相机会连不上。\n"
            "4. 默认 FTP 端口 2121，用户名 sony，密码 sony1234，可在程序「设置」里修改。\n"
            "5. 运行日志：shutterdrop.log；启动失败时还会写 shutterdrop-launcher.log，把日志发给作者即可。\n"
            "6. 详细使用说明见《ShutterDrop 使用说明.docx》或程序里的「使用说明」页面。\n")


def main() -> int:
    os.makedirs(BUILD, exist_ok=True)
    try:
        import pillow_heif  # noqa: F401
        heif = True
        print("[build] 打包 pillow-heif（HEIF 主图解码）")
    except Exception:
        heif = False
        print("[build] 未安装 pillow-heif，HEIF 只显示内嵌预览")
    console = bool(os.environ.get("SD_CONSOLE"))

    # 1) 程序本体 onedir
    print("[build] 1/4 收集依赖（onedir）")
    PyInstaller.__main__.run(base_args(heif, console) + [
        "--onedir", "--distpath", os.path.join(BUILD, "out"),
        "--workpath", os.path.join(BUILD, "onedir"), "--specpath", os.path.join(BUILD, "onedir")])

    # 2) 便携版目录 + C# 启动器
    print("[build] 2/4 生成便携文件夹版（带启动器）")
    portable = os.path.join(ROOT, "dist_onedir", "ShutterDrop-Portable")
    copy_dir(os.path.join(BUILD, "out", "ShutterDrop.App"), portable)
    write_readme(portable)
    build_launcher(portable, ICON)

    # 3) 单文件：压缩包 + 启动器（启动器把自身尾部的 zip 解压到临时目录再运行）
    print("[build] 3/4 生成单文件版（带启动器）")
    zip_dir = os.path.join(BUILD, "zip")
    zip_path = os.path.join(zip_dir, "payload.zip")
    os.makedirs(zip_dir, exist_ok=True)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    out_app = os.path.join(BUILD, "out", "ShutterDrop.App")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _dn, fs in os.walk(out_app):
            for fn in fs:
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, out_app))
    append_launcher(zip_path, os.path.join(ROOT, "dist", "ShutterDrop.exe"), portable)

    exe = os.path.join(ROOT, "dist", "ShutterDrop.exe")
    print(f"[build] 4/4 完成：{exe}  ({os.path.getsize(exe) / 1024 / 1024:.1f} MB)")
    print(f"[build]         {portable}\\ShutterDrop.exe")
    return 0


def append_launcher(payload_zip: str, out_exe: str, launcher_dir: str) -> None:
    """把启动器 exe 与 zip 压缩包拼成单个文件，启动器运行时把尾部 zip 解压再启动。

    文件布局：[C# 启动器][zip 内容][b"SD1P" + 8 字节 zip 长度]。
    用 zip 而不是 PyInstaller 的单文件 exe：启动器可以用 .NET 自带的
    System.IO.Compression 解压，不需要临时目录里的额外进程，也不依赖机器上是否有 Python。
    """
    os.makedirs(os.path.dirname(out_exe), exist_ok=True)
    with open(os.path.join(launcher_dir, "ShutterDrop.exe"), "rb") as f:
        launcher = f.read()
    with open(payload_zip, "rb") as f:
        payload = f.read()
    with open(out_exe, "wb") as f:
        f.write(launcher)
        f.write(payload)
        f.write(b"SD1P" + struct.pack("<Q", len(payload)))


if __name__ == "__main__":
    sys.exit(main())
