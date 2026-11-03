@echo off
chcp 65001 >nul
title Sony-FTP- 发布到 GitHub
cd /d "%~dp0"

echo ==================================================
echo   Sony-FTP- 发布到 GitHub
echo ==================================================
echo.
set /p GHUSER=请输入你的 GitHub 用户名（例如 zhangsan）:

if "%GHUSER%"=="" (
    echo 没有输入用户名，已退出。
    pause
    exit /b 1
)

echo.
echo 即将发布到： https://github.com/%GHUSER%/Sony-FTP-
echo 请确认你在网页上已经创建了名为 Sony-FTP- 的 Public 空仓库（不要勾选 README）。
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish_github.ps1" -User "%GHUSER%" -Repo "Sony-FTP-" -PushUrl "https://github.com/%GHUSER%/Sony-FTP-.git"

echo.
echo 如果上面有报错，请把窗口内容或 publish_log.txt 发给作者。
echo.
pause
