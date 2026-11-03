"""清理临时文件与调试脚本。

保留：源码、tests/ 下的正式测试、构建脚本（build_exe.py / build_onedir.py /
make_docx.py / make_icon.py / build_preview.py）、README、交付物（dist/、
dist_onedir/ShutterDrop-Portable、zip、docx、html、preview_screens/）。
"""
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))

# 一次性调试 / 探测脚本
DROP_FILES = [
    "build_debug_exe.py", "fetch_wheels.py", "install_tools.py", "patch_ctypes.py",
    "cleanup_tmp.py", "_fix_port_mode.py", "_fix_open_data.py", "_make_portable.py",
    "_build_debug_spec.py", "_check_temp.py", "_check_temp2.py", "_clean_build.py",
    "_copy_exe.py", "_geom_check.py", "_inspect_spec.py", "_probe_loop.py",
    "_probe_ftp.py", "_probe_multi.py", "_probe_self.py", "_tcl_layout.py",
    "_run_debug.py", "_run_exe_tmp.py", "_run_exe_tmp2.py", "_run_onedir.py",
    "_run_onedir2.py", "_fix_tables.py", "_test_diag.py", "debug.log",
    "_test_out.txt", "_test_out2.txt", "_test_out3.txt", "_test_out4.txt",
    "_test_edge_log.txt", "_test_canvas_log.jsonl", "_test_setattr.log",
    "_probe_loop.py",
]
DROP_PREFIXES = ("_test_", "_test_badge", "_test_bisect", "_test_canvas", "_test_cw",
                 "_test_diag", "_test_kw", "_test_load", "_test_tk", "_test_trace",
                 "_test_w.py", "_test_palette", "_test_shots")

KEEP_TESTS = {"test_unit.py", "test_e2e.py", "test_port_client.py", "test_ui_smoke.py",
              "render_screens.py", "test_packaged.py", "test_port_mode_child.py",
              "__init__.py", "test_live.py"}


def main():
    removed = []
    for name in os.listdir(ROOT):
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            continue
        if name in DROP_FILES or name.startswith(DROP_PREFIXES):
            try:
                os.remove(path)
                removed.append(name)
            except OSError as exc:
                print("skip", name, exc)
    # tests 目录下的调试脚本
    tdir = os.path.join(ROOT, "tests")
    for name in os.listdir(tdir):
        path = os.path.join(tdir, name)
        if os.path.isdir(path) and name != "__pycache__":
            shutil.rmtree(path, ignore_errors=True)
            removed.append("tests/" + name)
            continue
        if name == "__pycache__":
            shutil.rmtree(path, ignore_errors=True)
            continue
        if name.startswith("dbg_") or name.startswith("debug_") or name.startswith("probe_"):
            try:
                os.remove(path)
                removed.append("tests/" + name)
            except OSError as exc:
                print("skip", name, exc)
    # 根目录缓存与一次性目录
    for name in ("__pycache__", ".dsh-office-" ):
        pass
    for name in os.listdir(ROOT):
        if name == "__pycache__" or name.startswith(".dsh-office-"):
            shutil.rmtree(os.path.join(ROOT, name), ignore_errors=True)
            removed.append(name + "/")
    # _test 下的临时产物
    tdir = os.path.join(ROOT, "_test")
    if os.path.isdir(tdir):
        for name in os.listdir(tdir):
            p = os.path.join(tdir, name)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
        try:
            os.rmdir(tdir)
            removed.append("_test/")
        except OSError:
            pass
    # 打包中间产物
    for name in ("_build", "_build_work", "_build_debug"):
        p = os.path.join(ROOT, name)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
            removed.append(name + "/")
    # 离线打包依赖（仅打包时需要）
    p = os.path.join(ROOT, "_tools")
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
        removed.append("_tools/ (离线打包依赖，可重新下载)")
    print("removed:", len(removed))
    for n in sorted(removed):
        print("  -", n)
    print()
    print("root now:", sorted(os.listdir(ROOT)))


if __name__ == "__main__":
    main()
