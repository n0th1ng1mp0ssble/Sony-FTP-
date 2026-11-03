# Sony-FTP- 发布脚本（Windows PowerShell 5.1+ / PowerShell 7）
#
# 在 shutterdrop 目录里执行（一行）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish_github.ps1 -User 你的用户名 -Repo Sony-FTP- -PushUrl https://github.com/你的用户名/Sony-FTP-.git
#
# 做的事：
#   1. 整理“只进版本库的源码”到 ~\Sony-FTP-（dist/、publish/、_tools/ 等大文件一律不带）
#   2. 初始化仓库并提交
#   3. 推送到 GitHub；首次会弹出浏览器让你登录 GitHub
#   4. 失败时把完整日志写到本目录的 publish_log.txt，**窗口不会一闪而过**
#
# 本脚本不依赖系统 PATH 里的 git：会自动查找 Git 安装位置并补齐环境变量，
# 所以刚装完 Git 还没重开终端也能直接跑。

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$User,
    [Parameter(Mandatory = $true)][string]$Repo,
    [string]$PushUrl = "",
    [string]$Branch = "main",
    [switch]$Tag,
    [string]$TagName = "v1.0.0",
    [string]$OutDir = "",
    [switch]$NonInteractive
)

if ($NonInteractive) { $env:GIT_TERMINAL_PROMPT = "0" }
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $Root "publish_log.txt"
$script:Failed = $false

function Log([string]$text, [string]$color = "Gray") {
    Write-Host $text -ForegroundColor $color
    try { Add-Content -LiteralPath $LogFile -Value $text -Encoding UTF8 } catch { }
}

try { Remove-Item -LiteralPath $LogFile -Force -ErrorAction SilentlyContinue } catch { }

Log "=== Sony-FTP- 发布脚本 ===" "Cyan"
Log ("时间：" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Log "日志文件：$LogFile"
Log "工作目录：$Root"

try {
    # ---------- 1. 找到 Git ----------
    Log ""
    Log "1/4 查找 Git" "Cyan"
    $gitExe = $null
    $g = Get-Command git -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($g) { $gitExe = $g.Source }
    if (-not $gitExe -or -not (Test-Path $gitExe)) {
        $gitExe = $null
        foreach ($c in @(
                "C:\Program Files\Git\cmd\git.exe",
                "C:\Program Files (x86)\Git\cmd\git.exe",
                "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe",
                "$env:ProgramFiles\Git\bin\git.exe")) {
            if (Test-Path $c) { $gitExe = $c; break }
        }
    }
    if (-not $gitExe) {
        $script:Failed = $true
        Log "没有找到 git.exe，请先安装 Git：https://git-scm.com/download/win" "Red"
        Log "装完后重新运行本脚本即可。" "Red"
    } else {
        Log "    git: $gitExe" "Green"
        Log ("    版本：" + ((& $gitExe --version) 2>&1))

        # 把 git 加进 PATH，并补上 GIT_EXEC_PATH（正式安装后通常自动有，这里兜底）
        $gitCmdDir = Split-Path $gitExe -Parent
        $gitRoot = Split-Path $gitCmdDir -Parent
        $env:PATH = "$gitCmdDir;" + ($env:PATH -replace [regex]::Escape("$gitCmdDir;"), "")
        foreach ($core in @("mingw64\libexec\git-core", "libexec\git-core")) {
            $p = Join-Path $gitRoot $core
            if (Test-Path $p) { $env:GIT_EXEC_PATH = $p; break }
        }
        Log "    GIT_EXEC_PATH: $env:GIT_EXEC_PATH"

        if (-not $OutDir) { $OutDir = Join-Path $env:USERPROFILE $Repo }
        if (-not $PushUrl) { $PushUrl = "https://github.com/$User/$Repo.git" }

        # ---------- 2. 整理源码 ----------
        Log ""
        Log "2/4 整理要发布的源码 -> $OutDir" "Cyan"
        $Include = @(
            "main.py", "README.md", "LICENSE", ".gitignore", ".gitattributes", ".editorconfig",
            "启动 ShutterDrop.bat", "pyi_utf8_hook.py",
            "build_exe.py", "build_launcher.py", "build_onedir.py", "build_preview.py",
            "make_docx.py", "make_icon.py", "make_release.py", "prepare_build_tools.py", "cleanup.py",
            "publish_github.ps1", "发布到GitHub-手把手.md",
            "ShutterDrop.html", "ShutterDrop 使用说明.docx",
            "assets", "preview_screens"
        )
        $IncludeDirs = @("shutterdrop", "tests", ".github")
        $ExcludeNames = @("__pycache__", "*.pyc", "*.log", "*.bak")

        function Copy-Tree([string]$source, [string]$dest) {
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            Get-ChildItem -LiteralPath $source -Force -ErrorAction SilentlyContinue | Where-Object {
                $skip = $false
                foreach ($pat in $ExcludeNames) { if ($_.Name -like $pat) { $skip = $true } }
                -not $skip
            } | ForEach-Object {
                $target = Join-Path $dest $_.Name
                if ($_.PSIsContainer) { Copy-Tree $_.FullName $target }
                else { Copy-Item -LiteralPath $_.FullName -Destination $target -Force -ErrorAction SilentlyContinue }
            }
        }

        if (-not (Test-Path (Join-Path $OutDir ".git"))) {
            if (Test-Path $OutDir) {
                Remove-Item -LiteralPath $OutDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

        foreach ($item in $Include) {
            $src = Join-Path $Root $item
            if (-not (Test-Path $src)) { continue }
            $dst = Join-Path $OutDir $item
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
            Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction SilentlyContinue
        }
        foreach ($dir in $IncludeDirs) {
            $src = Join-Path $Root $dir
            if (Test-Path $src) { Copy-Tree $src (Join-Path $OutDir $dir) }
        }
        $shots = Join-Path $Root "preview_screens"
        if (Test-Path $shots) {
            New-Item -ItemType Directory -Force -Path (Join-Path $OutDir ".github\assets") | Out-Null
            Copy-Item (Join-Path $shots "*.png") (Join-Path $OutDir ".github\assets") -Force -ErrorAction SilentlyContinue
        }
        New-Item -ItemType Directory -Force -Path (Join-Path $OutDir "publish") | Out-Null
        $pubignore = Join-Path $Root "publish\.gitignore"
        if (Test-Path $pubignore) { Copy-Item $pubignore (Join-Path $OutDir "publish\.gitignore") -Force }

        $files = Get-ChildItem $OutDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch "\\\.git\\" }
        $sizeMB = 0
        if ($files) { $sizeMB = ($files | Measure-Object Length -Sum).Sum / 1MB }
        Log ("    共 {0} 个文件，{1:N1} MB" -f @($files).Count, $sizeMB) "Green"

        # ---------- 3. 提交 ----------
        Log ""
        Log "3/4 初始化仓库并提交" "Cyan"
        Push-Location $OutDir
        try {
            if (-not (Test-Path ".git")) {
                & $gitExe init -b $Branch 2>&1 | ForEach-Object { Log "    $_" }
            } else {
                Log "    （复用已有仓库，更新文件）"
            }
            & $gitExe add -A 2>&1 | ForEach-Object { Log "    $_" }
            & $gitExe -c user.name=$User -c user.email="$User@users.noreply.github.com" commit -m "Sony-FTP- v1.0.0：索尼相机 FTP 照片实时接收与预览" 2>&1 | ForEach-Object { Log "    $_" }
            Log ("    当前分支：" + (& $gitExe rev-parse --abbrev-ref HEAD 2>&1))

            # ---------- 4. 推送 ----------
            Log ""
            Log "4/4 推送到 $PushUrl" "Cyan"
            Log "    首次推送会弹出 GitHub 登录窗口：" "Yellow"
            Log "    选「Sign in with your browser」→ 浏览器里点 Authorize Git Credential Manager" "Yellow"
            & $gitExe remote remove origin 2>$null | Out-Null
            & $gitExe remote add origin $PushUrl 2>&1 | ForEach-Object { Log "    $_" }
            Log "    正在推送（约 3 MB，通常几秒；等待登录时请不要关窗口）……"
            $pushOut = & $gitExe push -u origin $Branch 2>&1
            $pushCode = $LASTEXITCODE
            if ($pushOut) { $pushOut | ForEach-Object { Log "    $_" } }
            if ($pushCode -ne 0) {
                $script:Failed = $true
                Log "推送失败（git 退出码 $pushCode）。常见原因：" "Red"
                Log "  · 网页上还没创建仓库 $Repo（Public，不要勾 README/.gitignore/license）" "Red"
                Log "  · 地址不对：当前是 $PushUrl" "Red"
                Log "  · 登录窗口被关掉：重新运行脚本即可再次弹出" "Red"
                return
            }
            if ($Tag) {
                & $gitExe tag -f $TagName 2>&1 | Out-Null
                & $gitExe push -f origin $TagName 2>&1 | ForEach-Object { Log "    $_" }
                Log "    已推送标签 $TagName：GitHub Actions 会自动构建并发布 Release（约 5~10 分钟）" "Green"
            }
        }
        finally {
            Pop-Location
        }
    }
}
catch {
    $script:Failed = $true
    Log ("异常：" + $_.Exception.Message) "Red"
    Log ("位置：" + $_.InvocationInfo.PositionMessage) "DarkGray"
}
finally {
    Log ""
    if ($script:Failed) {
        Log "出错了，完整日志：$LogFile" "Red"
        Log "请把这份日志整段发给我。" "Red"
    } else {
        Log "完成 ✓  仓库地址：https://github.com/$User/$Repo" "Green"
    }
    Log ""
    if (-not $NonInteractive) {
        Log "（按回车关闭窗口）" "DarkGray"
        try { [void](Read-Host) } catch { Start-Sleep -Seconds 5 }
    }
}
