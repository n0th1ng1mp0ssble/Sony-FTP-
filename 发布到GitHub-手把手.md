# 发布到 GitHub · 手把手版（仓库名：Sony-FTP-，公开）

> 目标：把这个项目推到 `https://github.com/你的GitHub用户名/Sony-FTP-`（公开仓库），
> 并把安装包放到 Releases 里供别人下载。
> 全程只需要三步：**装 Git → 网页建空仓库 → 跑一个脚本**。中途弹浏览器是正常的，登录一次就好。

---

## 第 1 步：安装 Git（约 2 分钟）

1. 打开 https://git-scm.com/download/win
2. 下载 **64-bit Git for Windows Setup** 并运行，安装时所有选项保持默认，一路点 **Next / Install**。
3. 安装完成后，**关闭所有 PowerShell 窗口再重新打开**，输入：

   ```powershell
   git --version
   ```

   看到类似 `git version 2.x.x.windows.1` 就说明装好了。

> 如果下载很慢，也可以下载「Portable」（免安装版），解压后在那个目录里右键 →「在终端中打开」再操作。

---

## 第 2 步：在 GitHub 网页创建一个空仓库（约 1 分钟）

1. 用浏览器打开 https://github.com/new （没登录会先让你登录）
2. **Repository name** 填：`Sony-FTP-`
3. 选择 **Public**（公开）
4. **下面的三个勾选都不要勾**：
   - `Add a README file`
   - `Add .gitignore`
   - `Choose a license`
5. 点绿色按钮 **Create repository**

创建成功后页面会显示一串地址，形如：

```
https://github.com/你的用户名/Sony-FTP-.git
```

**复制这一整串地址**（后面要用）。页面中间还有个 `yourname/Sony-FTP-`，那个不是地址，注意别复制错。

---

## 第 3 步：运行发布脚本（约 1 分钟）

1. 打开文件资源管理器，进入这个目录：
   ```
   C:\Users\bch84\Documents\deepseek-harness\default-workspace\shutterdrop
   ```
2. 在窗口**地址栏**（显示路径的那一栏）里输入 `powershell` 然后按回车 —— 会弹出一个蓝色/黑色的 PowerShell 窗口，路径就在 shutterdrop 里。
3. 在 PowerShell 里**一次性粘贴**下面这一整行（把 `你的用户名` 和 `仓库地址` 换成第 2 步的真实内容）：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish_github.ps1 -User 你的用户名 -Repo Sony-FTP- -PushUrl 仓库地址
   ```

   **例子（假设用户名是 zhangsan）：**

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish_github.ps1 -User zhangsan -Repo Sony-FTP- -PushUrl https://github.com/zhangsan/Sony-FTP-.git
   ```

4. 回车后会依次看到：
   ```
   1/4 准备干净目录： C:\Users\bch84\Sony-FTP-
       共 51 个文件，3.2 MB
   2/4 初始化仓库并提交
   3/4 推送到 https://github.com/你的用户名/Sony-FTP- (main)
   完成 ✓  仓库地址：https://github.com/你的用户名/Sony-FTP-
   ```
5. **第一次推送时会弹出一个窗口让你登录 GitHub**：
   - 选 **Sign in with your browser**（用浏览器登录）
   - 浏览器里点 **Authorize Git Credential Manager**
   - 回到 PowerShell，看到 `branch 'main' set up to track 'origin/main'` 就成功了。
   - 凭据会保存，以后不用再登录。

> 如果 PowerShell 提示「禁止运行脚本」，说明你直接执行了 `.ps1`；请严格按照上面第 3 条的**整行命令**执行（前面带了 `powershell -ExecutionPolicy Bypass`，不需要改系统设置）。

---

## 第 4 步：把安装包上传到 Releases（约 2 分钟）

源码推送成功后，仓库里还没有 exe/zip（这是故意的，仓库只放源码）。
安装包用「Release」发布：

1. 打开 `https://github.com/你的用户名/Sony-FTP-/releases/new`
2. 页面顶部 **Choose a tag** 输入 `v1.0.0` → 点 **Create new tag: v1.0.0 on publish**
3. **Release title** 填：`ShutterDrop v1.0.0`
4. 描述框里随便写一句，比如：`首个版本：索尼 A7M4/A7M5 FTP 照片实时接收、拍完即看、EXIF 一览`
5. 找到底部的 **Attach binaries by dropping them here or selecting them**，
   把下面两个文件拖进去：
   ```
   C:\Users\bch84\Documents\deepseek-harness\default-workspace\shutterdrop\publish\ShutterDrop-Portable-Windows.zip
   C:\Users\bch84\Documents\deepseek-harness\default-workspace\shutterdrop\publish\ShutterDrop.exe（单文件版）.exe
   ```
   上传进度条走完再继续（约 20 MB + 19 MB）。
6. 点绿色按钮 **Publish release**

完成后 Releases 页面就有下载链接了，别人点开仓库首页右上角也能看到。

---

## 第 5 步（可选）：让 GitHub 自动构建以后的新版本

仓库里已经带了 `.github/workflows/build.yml`。以后你想发新版本，只要：

1. 打开 GitHub 仓库 → **Settings → Actions → General**
2. 拉到最下面 **Workflow permissions** → 选 **Read and write permissions** → **Save**
3. 然后在本地执行（打完 tag 会自动构建 + 自动发布 Release，不用再手动传文件）：
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish_github.ps1 -User 你的用户名 -Repo Sony-FTP- -PushUrl https://github.com/你的用户名/Sony-FTP-.git -Tag v1.1.0
   ```

---

## 出问题怎么办（把 PowerShell 里的报错整段发我）

| 现象 | 原因 / 解决 |
| --- | --- |
| `git : 无法将"git"项识别为 cmdlet` | 没装 Git 或装完没重开窗口 → 重做第 1 步，然后**关掉 PowerShell 重新打开** |
| `remote: Repository not found` | 仓库名/用户名写错，或仓库还没创建 → 确认地址是 `https://github.com/你的用户名/Sony-FTP-.git` |
| `failed to push some refs` / `rejected` | 网页上创建仓库时勾了 README 等文件 → 删掉这个仓库重新建（不要勾任何选项）再跑脚本 |
| `Support for password authentication was removed` | 登录方式不对 → 重新执行脚本，弹出登录窗口时选「Sign in with your browser」 |
| 弹窗被关掉/找不到 | 再次执行脚本即可，会重新弹出 |
| `src refspec main does not match any` | 提交失败（通常是没有文件）→ 把输出发我 |

---

## 附：仓库内容说明（发给别人时可用）

- 仓库名：`Sony-FTP-`
- 简介（仓库页右上 **About** 里填）：
  `索尼 A7M4/A7M5 相机 FTP 照片实时接收与预览 · 拍完即看 · EXIF · Windows 桌面程序`
- Topics（About 旁边的齿轮里加）：`sony` `a7m4` `a7m5` `ftp` `photography` `python` `tkinter`
