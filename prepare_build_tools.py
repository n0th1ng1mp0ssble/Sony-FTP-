"""把 PyInstaller 打包所需的依赖下载并解压到 _tools/site（离线可用）。"""
import os
import ssl
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
WHEELS = os.path.join(ROOT, "_tools", "wheels")
SITE = os.path.join(ROOT, "_tools", "site")
INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
BASE = "https://pypi.tuna.tsinghua.edu.cn/"

PICK = {
    "pyinstaller": "pyinstaller-6.22.3-py3-none-win_amd64.whl",
    "pyinstaller-hooks-contrib": "pyinstaller_hooks_contrib-2025.11-py3-none-any.whl",
    "altgraph": "altgraph-0.13-py2.py3-none-any.whl",
    "pefile": "pefile-2023.2.7-py3-none-any.whl",
    "pywin32-ctypes": "pywin32_ctypes-0.2.0-py2.py3-none-any.whl",
    "packaging": "packaging-25.0-py3-none-any.whl",
    "pillow-heif": "pillow_heif-1.3.0-cp312-cp312-win_amd64.whl",
    "setuptools": "setuptools-80.9.0-py3-none-any.whl",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pip/26.2.1"})
    return urllib.request.urlopen(req, timeout=120, context=CTX).read()


def wheel_url(name: str) -> str:
    html = fetch(f"{INDEX}/{name}/").decode("utf-8", "replace")
    want = PICK[name]
    for line in html.splitlines():
        if want in line and 'href="' in line:
            href = line.split('href="')[1].split('"')[0].split("#")[0]
            return href if href.startswith("http") else BASE + href.lstrip("./")
    raise RuntimeError(f"找不到 {want}")


def patch_win32ctypes() -> None:
    """win32ctypes 0.2.0 用了 Python 3.12 已删除的 find_module，这里换成 find_spec。"""
    path = os.path.join(SITE, "win32ctypes", "core", "__init__.py")
    src = open(path, encoding="utf-8").read()
    if "def find_spec(self" in src:
        return
    start = src.index("    def find_module(self, fullname, path=None):")
    end = src.index("sys.meta_path.append(BackendFinder([")
    new = """    def find_spec(self, fullname, path=None, target=None):
        import importlib.util as _ilu
        if fullname not in self.redirected_modules:
            return None
        module_name = fullname.split('.')[-1]
        prefix = 'win32ctypes.core.ctypes.' if _backend == 'ctypes' else 'win32ctypes.core.cffi.'
        real_spec = _ilu.find_spec(prefix + module_name)
        if real_spec is None:
            return None
        return _ilu.spec_from_loader(fullname, BackendLoader(prefix + module_name))

"""
    open(path, "w", encoding="utf-8").write(src[:start] + new + src[end:])


def main() -> int:
    os.makedirs(WHEELS, exist_ok=True)
    os.makedirs(SITE, exist_ok=True)
    for name, fname in PICK.items():
        path = os.path.join(WHEELS, fname)
        if not os.path.exists(path):
            url = wheel_url(name)
            print("下载", fname)
            data = fetch(url)
            open(path, "wb").write(data)
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                fn = info.filename
                if fn.endswith("RECORD") or (".data/" in fn and ".data/scripts/" not in fn):
                    continue
                if fn.endswith("/"):
                    continue
                target = (os.path.join(SITE, fn.split(".data/scripts/", 1)[1])
                          if ".data/scripts/" in fn else os.path.join(SITE, fn))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
        print("解压", name)
    patch_win32ctypes()
    print("完成 ->", SITE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
