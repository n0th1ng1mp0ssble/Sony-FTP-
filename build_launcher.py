"""用 MSBuild 把 C# 启动器编译成独立的 exe（只要目标机器有 .NET Framework 4.x 就能跑）。

启动器负责：
  * 启动程序本体 ShutterDrop.App.exe（同目录，或从自身尾部解压出来的单文件包）；
  * 任何启动失败都用中文弹窗说明原因，并把细节写入日志，不再出现
    “Failed to create parent directory structure” 这种看不懂的提示。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(ROOT, "assets", "shutterdrop.ico")

SOURCE = r'''
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

static class Program
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    const uint MB_ICONERROR = 0x10;
    const string PAYLOAD_MAGIC = "SD1P";
    const string APP_NAME = "ShutterDrop.App.exe";

    [STAThread]
    static int Main(string[] args)
    {
        string exePath = Process.GetCurrentProcess().MainModule.FileName;
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string logPath = Path.Combine(dir, "shutterdrop-launcher.log");
        Log(logPath, "启动器运行：" + exePath);
        try
        {
            string app = Path.Combine(dir, APP_NAME);
            if (!File.Exists(app))
            {
                if (HasAppendedPayload(exePath))
                    app = ExtractSelf(exePath, logPath);
                else
                {
                    Fail(logPath, "找不到程序本体 " + APP_NAME + "。\n\n"
                        + "请把整个文件夹（含 _internal 目录）一起复制，不要只拿 ShutterDrop.exe。");
                    return 1;
                }
            }

            var psi = new ProcessStartInfo(app);
            foreach (string a in args) psi.Arguments += " " + Quote(a);
            psi.WorkingDirectory = dir;
            psi.UseShellExecute = false;
            Process p = Process.Start(psi);
            if (p == null) throw new Exception("无法创建进程");
            p.WaitForExit();
            int code = p.ExitCode;
            Log(logPath, "程序退出，代码 " + code);
            if (code != 0)
            {
                Fail(logPath, "ShutterDrop 启动后异常退出（代码 " + code + "）。\n\n"
                    + "日志：" + logPath + " 与 " + Path.Combine(dir, "shutterdrop.log")
                    + "\n把日志发给作者即可定位问题。");
            }
            return code;
        }
        catch (Exception ex)
        {
            Fail(logPath, "ShutterDrop 无法启动：" + ex.Message);
            return 1;
        }
    }

    static bool HasAppendedPayload(string exePath)
    {
        try
        {
            using (var fs = new FileStream(exePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            {
                if (fs.Length < 12) return false;
                fs.Seek(-12, SeekOrigin.End);
                var tail = new byte[12];
                fs.Read(tail, 0, 12);
                return Encoding.ASCII.GetString(tail, 0, 4) == PAYLOAD_MAGIC;
            }
        }
        catch { return false; }
    }

    static string ExtractSelf(string exePath, string logPath)
    {
        string baseDir = Path.Combine(Path.GetTempPath(), "ShutterDrop");
        string target = Path.Combine(baseDir, "app-" + Hash(exePath));
        string app = Path.Combine(target, APP_NAME);
        if (!File.Exists(app))
        {
            Directory.CreateDirectory(baseDir);
            string tmp = target + "-" + Guid.NewGuid().ToString("N") + ".zip";
            Log(logPath, "正在解压到 " + target);
            try
            {
                using (var fs = new FileStream(exePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                {
                    fs.Seek(-8, SeekOrigin.End);
                    var lenBuf = new byte[8];
                    fs.Read(lenBuf, 0, 8);
                    long len = BitConverter.ToInt64(lenBuf, 0);
                    fs.Seek(-12 - len, SeekOrigin.End);
                    using (var outFs = new FileStream(tmp, FileMode.Create, FileAccess.Write))
                    {
                        var buf = new byte[1 << 20];
                        long left = len;
                        while (left > 0)
                        {
                            int n = fs.Read(buf, 0, (int)Math.Min(buf.Length, left));
                            if (n <= 0) break;
                            outFs.Write(buf, 0, n);
                            left -= n;
                        }
                    }
                }
                string staging = target + "-tmp-" + Guid.NewGuid().ToString("N");
                ZipFile.ExtractToDirectory(tmp, staging);
                try { Directory.Move(staging, target); }
                catch (IOException)
                {
                    try { Directory.Delete(staging, true); } catch { }
                }
            }
            finally
            {
                try { if (File.Exists(tmp)) File.Delete(tmp); } catch { }
            }
        }
        if (!File.Exists(app))
            throw new Exception("解压后找不到 " + APP_NAME + "，请检查临时目录权限或杀毒软件是否拦截。");
        return app;
    }

    static string Hash(string s)
    {
        using (var md5 = System.Security.Cryptography.MD5.Create())
        {
            var bytes = md5.ComputeHash(Encoding.UTF8.GetBytes(s));
            var sb = new StringBuilder();
            for (int i = 0; i < 6; i++) sb.Append(bytes[i].ToString("x2"));
            return sb.ToString();
        }
    }

    static void Log(string path, string line)
    {
        try
        {
            File.AppendAllText(path, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + line + Environment.NewLine,
                Encoding.UTF8);
        }
        catch { }
    }

    static void Fail(string logPath, string message)
    {
        Log(logPath, message);
        MessageBoxW(IntPtr.Zero, message, "ShutterDrop 启动失败", MB_ICONERROR);
    }

    static string Quote(string s)
    {
        if (s.Length > 0 && s.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0) return s;
        return "\"" + s.Replace("\"", "\\\"") + "\"";
    }
}
'''

CS_PROJ = r'''<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Configuration>Release</Configuration>
    <Platform>AnyCPU</Platform>
    <OutputType>WinExe</OutputType>
    <OutputPath>{outdir}\</OutputPath>
    <AssemblyName>ShutterDrop</AssemblyName>
    <TargetFrameworkVersion>v4.0</TargetFrameworkVersion>
    <ApplicationIcon>{icon}</ApplicationIcon>
    <Optimize>true</Optimize>
    <DebugType>none</DebugType>
    <WarningLevel>0</WarningLevel>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="Program.cs" />
    <Reference Include="System" />
    <Reference Include="System.Windows.Forms" />
    <Reference Include="System.IO.Compression" />
    <Reference Include="System.IO.Compression.FileSystem" />
  </ItemGroup>
  <Import Project="$(MSBuildToolsPath)\Microsoft.CSharp.targets" />
</Project>
'''

MSBUILD_CANDIDATES = [
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe",
]


def build_launcher(out_dir: str, icon: str = ICON) -> str:
    os.makedirs(out_dir, exist_ok=True)
    # 只产出 exe；编译中间文件放在独立的 _launcher_src 里，结束后删除
    work = os.path.join(out_dir, "_launcher_src")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    try:
        with open(os.path.join(work, "Program.cs"), "w", encoding="utf-8") as f:
            f.write(SOURCE)
        with open(os.path.join(work, "Launcher.csproj"), "w", encoding="utf-8") as f:
            f.write(CS_PROJ.format(outdir=out_dir, icon=icon if os.path.exists(icon) else ""))
        msbuild = next((p for p in MSBUILD_CANDIDATES if os.path.exists(p)), None)
        if not msbuild:
            raise RuntimeError("找不到 MSBuild（需要 .NET Framework 4.x）")
        r = subprocess.run([msbuild, os.path.join(work, "Launcher.csproj"),
                            "/p:Configuration=Release", "/nologo", "/v:minimal"],
                           capture_output=True, timeout=300,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            sys.stderr.write(r.stdout.decode("gbk", "replace")[-3000:])
            raise RuntimeError("MSBuild 编译启动器失败")
        exe = os.path.join(out_dir, "ShutterDrop.exe")
        if not os.path.exists(exe):
            raise RuntimeError("没有生成启动器 exe")
        # MSBuild 会把 .NET 的引用程序集复制到输出目录，清掉，只留启动器本身
        for name in os.listdir(out_dir):
            full = os.path.join(out_dir, name)
            if name in ("mscorlib.dll", "zh-Hans") or name.startswith("norm") and name.endswith(".nlp"):
                if os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
                else:
                    os.remove(full)
        return exe
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
    print("built:", build_launcher(target))
