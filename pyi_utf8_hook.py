"""PyInstaller 运行时钩子：在任何模块导入之前启用 Python 的 UTF-8 模式。

打包后的程序无法通过命令行参数 `-X utf8` 交给 Python 解释器（引导程序不理解它），
所以把 sys.flags.utf8_mode 打开，让 io / 编解码器都不依赖系统代码页，
避免少数缺少代码页 65001 的 Windows 上一启动就报 LookupError。
"""
import sys

if sys.platform == "win32" and not sys.flags.utf8_mode:
    try:
        sys.flags.utf8_mode = 1
    except (AttributeError, TypeError):
        pass
