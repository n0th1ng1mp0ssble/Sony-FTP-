"""ShutterDrop —— 索尼相机 FTP 照片实时接收与预览工具（Windows 桌面程序）。

本文件生成 `ShutterDrop.html`，作为离线可打开的“项目介绍 + 界面预览”，
内容包含功能说明、相机设置步骤、常见问题与界面截图（内嵌为 base64）。
"""
from __future__ import annotations

import base64
import html
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "ShutterDrop.html")
SHOTS = os.path.join(ROOT, "preview_screens")

SHOWCASE = [
    ("01_dashboard.png", "仪表盘 · 相机已连接 / 照片已保存",
     "顶部状态胶囊实时显示相机连接状态；左侧「相机连接」卡片列出要填进相机的四项参数；"
     "右侧是传输进度与本次会话统计；底部是最近收到的照片缩略图。"),
    ("02_realtime_preview.png", "拍完即看 · 实时预览（倒计时 + EXIF）",
     "每张照片传完自动弹出：顶部倒计时条显示还剩几秒自动关闭（可暂停 / 全屏），"
     "右侧列出相机、镜头、光圈、快门、ISO、焦距、曝光补偿等参数。"),
    ("03_settings_ftp.png", "设置 · FTP 连接与照片保存位置",
     "端口、用户名、密码、本机 IP 一览无余，可一键复制；保存目录支持浏览、"
     "按日期分组、保留相机目录结构、同名不覆盖。"),
    ("04_settings_preview.png", "设置 · 拍完即看",
     "「每张展示时长」滑杆 + 3/5/10/20/30 秒快捷键，决定照片弹出后展示多少秒；"
     "还可以选窗口 / 全屏、EXIF 放在图片右侧 / 左侧 / 下方。"),
    ("05_settings_bottom.png", "设置 · 相机在线检测与外观",
     "除了 FTP 连接状态，程序还会扫描局域网里的相机端口，判断相机是否开机入网；"
     "支持浅色 / 深色 / 跟随系统与界面缩放。"),
    ("06_help_top.png", "使用说明 · 五分钟上手",
     "内置完整的相机端设置步骤（A7M4 / A7M5 菜单路径）、界面说明、设置项解释与常见问题。"),
]


def data_uri(path: str) -> str:
    with open(path, "rb") as f:
        b = base64.b64encode(f.read()).decode("ascii")
    return "data:image/png;base64," + b


def build() -> str:
    cards = []
    for i, (name, title, desc) in enumerate(SHOWCASE, 1):
        p = os.path.join(SHOTS, name)
        img = data_uri(p) if os.path.exists(p) else ""
        cards.append(f"""
      <figure class="shot">
        <div class="shot-head"><span class="num">{i:02d}</span><h3>{html.escape(title)}</h3></div>
        <img src="{img}" alt="{html.escape(title)}" loading="lazy">
        <figcaption>{html.escape(desc)}</figcaption>
      </figure>""")
    shots = "\n".join(cards)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShutterDrop · 索尼相机 FTP 照片实时接收</title>
<style>
  :root {{
    --bg: #f5f6f8; --surface: #ffffff; --surface2: #eef0f4; --border: #e2e5ea;
    --text: #16181d; --text2: #5f6570; --text3: #9aa0aa; --accent: #2563eb;
    --accent-soft: #e8efff; --ok: #16a34a; --ok-soft: #e7f6ec; --warn: #d97706;
    --warn-soft: #fdf3e3; --radius: 16px;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#121417; --surface:#1a1d22; --surface2:#22262d; --border:#2a2f37;
      --text:#f1f3f6; --text2:#a3aab5; --text3:#737a85; --accent:#4f8ef7;
      --accent-soft:#1d2a44; --ok:#3ecf7a; --ok-soft:#17301f; --warn:#f2a53c; --warn-soft:#33260f; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font-family:"Microsoft YaHei UI","PingFang SC","Hiragino Sans GB",system-ui,sans-serif;
    line-height:1.7; }}
  .wrap {{ max-width:1120px; margin:0 auto; padding:48px 24px 80px; }}
  header.hero {{ display:flex; gap:28px; align-items:flex-start; flex-wrap:wrap;
    background:var(--surface); border:1px solid var(--border); border-radius:24px;
    padding:36px 36px 32px; margin-bottom:28px; }}
  .logo {{ width:64px; height:64px; border-radius:18px; background:var(--accent);
    display:grid; place-items:center; color:#fff; font-size:30px; font-weight:700; flex:none; }}
  .hero h1 {{ margin:0 0 6px; font-size:34px; letter-spacing:-0.5px; }}
  .hero .sub {{ margin:0; color:var(--text2); font-size:15px; }}
  .pills {{ margin-top:16px; display:flex; gap:8px; flex-wrap:wrap; }}
  .pill {{ font-size:12px; padding:4px 12px; border-radius:999px; background:var(--accent-soft);
    color:var(--accent); }}
  .pill.ok {{ background:var(--ok-soft); color:var(--ok); }}
  .pill.warn {{ background:var(--warn-soft); color:var(--warn); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px;
    margin:28px 0; }}
  .card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
    padding:22px 22px 18px; }}
  .card h3 {{ margin:0 0 8px; font-size:16px; }}
  .card p {{ margin:0; color:var(--text2); font-size:13.5px; }}
  .icon {{ width:36px; height:36px; border-radius:10px; display:grid; place-items:center;
    background:var(--accent-soft); color:var(--accent); margin-bottom:12px; font-size:18px; }}
  section {{ margin-top:44px; }}
  section > h2 {{ font-size:24px; margin:0 0 6px; letter-spacing:-0.3px; }}
  section > .lead {{ margin:0 0 22px; color:var(--text2); font-size:14.5px; }}
  .steps {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
    padding:26px 28px; }}
  .step {{ display:flex; gap:16px; padding:12px 0; border-bottom:1px dashed var(--border); }}
  .step:last-child {{ border-bottom:0; }}
  .step .n {{ flex:none; width:26px; height:26px; border-radius:50%; background:var(--accent-soft);
    color:var(--accent); font-size:13px; display:grid; place-items:center; font-weight:700;
    margin-top:2px; }}
  .step b {{ display:block; font-size:15px; }}
  .step span {{ color:var(--text2); font-size:13.5px; }}
  code {{ background:var(--surface2); padding:2px 7px; border-radius:6px;
    font-family:"Cascadia Mono",Consolas,monospace; font-size:12.5px; }}
  pre {{ background:var(--surface2); padding:14px 16px; border-radius:12px; overflow:auto;
    font-family:"Cascadia Mono",Consolas,monospace; font-size:12.5px; line-height:1.6; }}
  .shot {{ margin:0 0 34px; background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); overflow:hidden; }}
  .shot-head {{ display:flex; align-items:center; gap:12px; padding:18px 22px 6px; }}
  .shot-head .num {{ color:var(--accent); font-weight:700; font-family:"Cascadia Mono",monospace; }}
  .shot-head h3 {{ margin:0; font-size:17px; }}
  .shot img {{ width:100%; display:block; border-top:1px solid var(--border);
    border-bottom:1px solid var(--border); background:var(--surface2); }}
  .shot figcaption {{ padding:14px 22px 18px; color:var(--text2); font-size:13.5px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--surface);
    border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; font-size:13.5px; }}
  th, td {{ text-align:left; padding:11px 16px; border-bottom:1px solid var(--border); }}
  th {{ background:var(--surface2); font-weight:600; }}
  td:first-child {{ white-space:nowrap; color:var(--text2); }}
  .qa {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
    padding:8px 26px; }}
  details {{ padding:14px 0; border-bottom:1px dashed var(--border); }}
  details:last-child {{ border-bottom:0; }}
  summary {{ cursor:pointer; font-weight:600; font-size:14.5px; }}
  details p {{ margin:8px 0 0; color:var(--text2); font-size:13.5px; white-space:pre-line; }}
  footer {{ margin-top:56px; color:var(--text3); font-size:12.5px; text-align:center; }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  @media (max-width:760px) {{ .cols {{ grid-template-columns:1fr; }} .hero {{ padding:26px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <div class="logo">◉</div>
    <div style="flex:1;min-width:260px">
      <h1>ShutterDrop</h1>
      <p class="sub">索尼 A7M4 / A7M5 相机 FTP 照片实时接收 · 拍完即看 · 自动存盘 · EXIF 一览<br>
      纯 Python + Tkinter 桌面程序，零第三方依赖，双击即用，只在本机局域网内运行。</p>
      <div class="pills">
        <span class="pill ok">相机连接状态</span>
        <span class="pill">实时传输进度</span>
        <span class="pill">N 秒大图预览</span>
        <span class="pill">EXIF 参数</span>
        <span class="pill">保存位置设置</span>
        <span class="pill warn">仅局域网</span>
      </div>
    </div>
  </header>

  <div class="grid">
    <div class="card"><div class="icon">◎</div><h3>相机是否已连接</h3>
      <p>顶部状态胶囊 + FTP 控制连接实时状态；同时扫描局域网中的相机端口（21 / 15740 / 64321），
      相机开机入网就会在「本机主机名」旁边提示。</p></div>
    <div class="card"><div class="icon">⇣</div><h3>传输进度</h3>
      <p>单文件进度条、已传 / 总大小、实时速度、剩余时间和队列数量，一眼看到正在传哪张、还要多久。</p></div>
    <div class="card"><div class="icon">▣</div><h3>拍一张看一张</h3>
      <p>每张照片传完自动弹出大图，按设置展示 N 秒后自动关闭；可按空格暂停、F 全屏，也可在「最近照片」里回看。</p></div>
    <div class="card"><div class="icon">⚙</div><h3>EXIF 参数</h3>
      <p>相机、镜头、光圈、快门、ISO、焦距、等效焦距、曝光补偿、白平衡、分辨率、方向、GPS 等。</p></div>
    <div class="card"><div class="icon">▤</div><h3>保存位置</h3>
      <p>任意目录、按日期建子文件夹、保留相机 DCIM 结构、同名文件自动加序号（绝不覆盖）、磁盘剩余空间。</p></div>
    <div class="card"><div class="icon">☾</div><h3>简洁清晰</h3>
      <p>自绘圆角卡片与开关，浅色 / 深色 / 跟随系统，界面缩放；中文帮助页内置完整相机设置步骤。</p></div>
  </div>

  <section>
    <h2>一分钟上手</h2>
    <p class="lead">相机端只需要填一次服务器设置，之后每次拍照自动上传。</p>
    <div class="steps">
      <div class="step"><div class="n">1</div><div><b>让相机和电脑连同一个网络</b>
        <span>Wi-Fi：相机 MENU → 网络 → Wi-Fi → 连接到访问点。更快更稳的做法是用 USB-C 转网口适配器 + 网线接到同一个路由器。</span></div></div>
      <div class="step"><div class="n">2</div><div><b>在相机里填写 FTP 服务器</b>
        <span>MENU → 网络 → FTP 传输 → FTP 传输功能 → 服务器设置 → 服务器1</span>
        <pre>主机名   本程序「设置 → 本机主机名」里的 IP（例 192.168.1.20）
端口     2121（默认，可改）
安全协议   关闭
用户     sony       密码  sony1234（可改）
目录层级   标准</pre></div></div>
      <div class="step"><div class="n">3</div><div><b>打开相机的 FTP 功能</b>
        <span>FTP 传输 → FTP 传输功能 → FTP 功能 → 开。相机屏幕出现 FTP 连接图标，程序顶部变绿「相机已连接」。</span></div></div>
      <div class="step"><div class="n">4</div><div><b>开启自动传输</b>
        <span>FTP 传输 → FTP 传输功能 → 自动 FTP 传输 → 开；自动 FTP 目标 → 静止影像 → 全部。（也可不开，回放时用自定义键手动推送）</span></div></div>
      <div class="step"><div class="n">5</div><div><b>拍照</b>
        <span>每张传完，程序自动弹出大图并展示 N 秒（N 在「设置 → 拍完即看」里改），同时列出 EXIF。</span></div></div>
    </div>
  </section>

  <section>
    <h2>界面预览</h2>
    <p class="lead">以下截图由程序真实渲染（Windows，1336×899 窗口 / 预览窗 1456×956）。</p>
    {shots}
  </section>

  <section>
    <h2>设置项一览</h2>
    <p class="lead">设置页分五组：FTP 连接、照片保存位置、拍完即看、相机在线检测、外观。</p>
    <table>
      <tr><th style="width:180px">设置项</th><th>说明</th></tr>
      <tr><td>端口</td><td>FTP 服务监听端口，默认 2121；21 端口需要管理员权限且常被占用，不建议用。</td></tr>
      <tr><td>用户名 / 密码</td><td>相机服务器设置里填同样的值，防止局域网误连。</td></tr>
      <tr><td>本机主机名</td><td>自动列出本机局域网 IP（默认路由网卡优先），相机优先填第一个。</td></tr>
      <tr><td>启动时自动开启</td><td>打开程序即自动运行 FTP 服务（右上角也可以随时手动启停）。</td></tr>
      <tr><td>保存目录</td><td>照片落盘位置；不存在时保存设置会自动创建，可一键打开。</td></tr>
      <tr><td>按日期建子文件夹</td><td>例如 2026-10-26/DSC01234.JPG。</td></tr>
      <tr><td>保留相机目录结构</td><td>相机传 DCIM/100MSDCF/DSC01234.JPG 时原样保留子目录。</td></tr>
      <tr><td>同名文件覆盖</td><td>关闭时遇到同名文件自动加 _1、_2 后缀，绝不覆盖旧照片。</td></tr>
      <tr><td>每张展示时长</td><td>照片弹出后展示多少秒（0 = 一直显示）；滑杆 + 3/5/10/20/30 快捷键。</td></tr>
      <tr><td>展示方式</td><td>窗口，或全屏（适合离相机稍远时回看）。</td></tr>
      <tr><td>EXIF 位置</td><td>参数列表放在大图的右侧、左侧或下方。</td></tr>
      <tr><td>相机 IP（可选）</td><td>填写后只检测该 IP；留空自动扫描常见网段。</td></tr>
      <tr><td>检测间隔 / 离线判定</td><td>多久扫描一次、多久没有连接算是断开。</td></tr>
      <tr><td>主题 / 界面缩放</td><td>浅色、深色、跟随系统；0.8× ~ 1.6×。</td></tr>
    </table>
  </section>

  <section>
    <h2>技术说明</h2>
    <div class="cols">
      <div class="card"><h3>FTP 服务器</h3><p>标准库手写实现：被动（PASV / EPSV）与主动（PORT / EPRT）双模式、断点续传（REST / APPE）、
        UTF-8 中文文件名、目录创建、ASCII 模式换行还原；只接受图片 / 视频扩展名，路径不能越出保存目录。</p></div>
      <div class="card"><h3>EXIF 解析</h3><p>JPEG / PNG 用 Pillow；RAW（.ARW/.DNG）用内置 TIFF 解析器直接读，
        即使没有缩略图也能显示完整拍摄参数。</p></div>
      <div class="card"><h3>HEIF 预览</h3><p>A7M5 拍 HEIF 时，程序会从 HEIF 容器中提取内嵌 JPEG 显示画面；
        额外安装 pillow-heif 可解码 HEIF 主图。</p></div>
      <div class="card"><h3>安全边界</h3><p>只监听本机网卡，不连接互联网；不会执行相机的任何“指令”，
        只是按文件名保存上传内容。</p></div>
    </div>
  </section>

  <section>
    <h2>常见问题</h2>
    <div class="qa">
      <details open><summary>相机一直显示「连接错误」</summary>
        <p>1) 确认电脑和相机在同一路由器下；2) 安全协议设为「关闭」，端口与主机名按设置页填写；
3) Windows 防火墙第一次运行时点「允许访问」；4) 电脑开了 VPN / 虚拟网卡时可能选错 IP，试试另一个 IP。</p></details>
      <details><summary>传得很慢</summary>
        <p>Wi-Fi 传一张 24MP JPEG 约 3~8 秒属正常。需要更快要换 USB-C 转网口的有线 LAN，并确认网线、路由器 LAN 口都是千兆。</p></details>
      <details><summary>RAW 照片没有预览图</summary>
        <p>RAW 会显示占位图，但文件已完整保存且能读 EXIF。想要画面预览可在相机里设置同时传 JPEG（RAW+J/H 传输目标 → JPEG &amp; HEIF）。</p></details>
      <details><summary>HEIF 没有画面</summary>
        <p>程序会自动找 HEIF 里的内嵌预览；如果还是空白，安装 pillow-heif 后重启程序即可。</p></details>
      <details><summary>端口被占用 / 服务启动失败</summary>
        <p>改成 2121、2122 等 1024 以上的端口，并确认没有运行其他 FTP 服务（如 FileZilla Server）。</p></details>
    </div>
  </section>

  <footer>ShutterDrop v1.0 · 纯 Python 桌面程序 · 仅在本机局域网运行 · 本页面为离线说明文档</footer>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    content = build()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    print("written:", OUT, len(content), "chars")
