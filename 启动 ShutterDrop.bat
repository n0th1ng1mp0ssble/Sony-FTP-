@echo off
chcp 65001 >nul
rem 源码版启动脚本：需要已安装 Python 3.9+ 与 Pillow（pip install pillow）
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw "%~dp0main.py" & exit /b)
where python >nul 2>nul && (start "" python "%~dp0main.py" & exit /b)
echo 没有找到 Python，请先安装 Python 3.9+，或直接使用 dist\ShutterDrop.exe。
pause
