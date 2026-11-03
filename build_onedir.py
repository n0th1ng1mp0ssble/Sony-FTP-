"""生成 onedir 版本：ShutterDrop/ShutterDrop.exe + 依赖目录（放在包里，方便在受限环境里运行）。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "_tools", "site"))

import PyInstaller.__main__  # noqa: E402


def main() -> int:
    try:
        import pillow_heif  # noqa: F401
        heif = True
    except Exception:
        heif = False
    args = [
        os.path.join(ROOT, "main.py"),
        "--name", "ShutterDrop",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--console" if os.environ.get("SD_CONSOLE") else "--windowed",
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
        "--distpath", os.path.join(ROOT, "dist_onedir"),
        "--workpath", os.path.join(ROOT, "_build", "onedir"),
        "--specpath", os.path.join(ROOT, "_build", "onedir"),
        "--icon", os.path.join(ROOT, "assets", "shutterdrop.ico"),
    ]
    if heif:
        args += ["--hidden-import", "pillow_heif", "--collect-binaries", "pillow_heif"]
    # ttk 主题等 tcl 包脚本：PyInstaller 只带了 .tm，ttk 的 .tcl 需要手动补
    tclroot = os.path.join(sys.base_prefix, "tcl")
    tk = os.path.join(tclroot, "tk8.6")
    if os.path.isdir(tk):
        for sub in ("ttk", "msgs", "images"):
            src = os.path.join(tk, sub)
            if os.path.isdir(src):
                args += ["--add-data", f"{src}{os.pathsep}_tk_data/{sub}"]
    PyInstaller.__main__.run(args)
    exe = os.path.join(ROOT, "dist_onedir", "ShutterDrop", "ShutterDrop.exe")
    print("onedir:", exe, os.path.exists(exe))
    return 0 if os.path.exists(exe) else 1


if __name__ == "__main__":
    sys.exit(main())
