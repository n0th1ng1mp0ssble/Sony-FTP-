## ShutterDrop 下载

| 文件 | 说明 |
| --- | --- |
| **ShutterDrop-Portable-Windows.zip** | **推荐**。解压后双击 `启动 ShutterDrop.bat`（或 `ShutterDrop.exe`）。整个文件夹要一起保留，`ShutterDrop.App.exe` 和 `_internal` 不能少。 |
| **ShutterDrop.exe** | 单文件版，复制到任何地方双击运行。首次启动会把运行库解压到 `%TEMP%\ShutterDrop`，约 2~5 秒。 |

两个版本都带一个小启动器：启动失败会弹出**中文提示**，并把原因写入 `shutterdrop-launcher.log` / `shutterdrop.log`。

### 首次使用
1. 相机与电脑连到同一个路由器（Wi-Fi 或 USB-C 转网口有线 LAN）。
2. 相机 `MENU → 网络 → FTP 传输 → FTP 传输功能 → 服务器设置 → 服务器1`：
   主机名 = 程序显示的本机 IP，端口 `2121`，安全协议 **关闭**，用户 `sony`，密码 `sony1234`。
3. 相机 `FTP 传输功能 → FTP 功能 → 开`，再打开 `自动 FTP 传输`。
4. 拍一张照片，电脑上会自动弹出大图与 EXIF，并保存到设置的目录。

首次运行若 Windows 提示「已保护你的电脑」→「更多信息 → 仍要运行」；
若弹出防火墙提示，请勾选「专用网络」并允许访问。

完整说明见仓库里的 `ShutterDrop 使用说明.docx` 或程序内「使用说明」页。
