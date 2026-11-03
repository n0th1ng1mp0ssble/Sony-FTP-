"""帮助页：使用说明、相机设置、常见问题、功能与安全说明。"""
from __future__ import annotations

import tkinter as tk

from .theme import Fonts
from .widgets import Button


SG = "→"


def build_help(parent, ctl, palette: dict, fonts: Fonts, on_goto_settings=None) -> None:
    p = palette
    wrap = tk.Frame(parent, bg=p["bg"])
    wrap.pack(fill="both", expand=True)
    canvas = tk.Canvas(wrap, bg=p["bg"], highlightthickness=0, bd=0)
    bar = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    body = tk.Frame(canvas, bg=p["bg"])
    win = canvas.create_window((0, 0), window=body, anchor="nw")
    body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

    def wheel(evt):
        try:
            canvas.yview_scroll(int(-evt.delta / 120), "units")
        except tk.TclError:
            pass
    body.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
    body.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    def title(text: str) -> None:
        tk.Label(body, text=text, bg=p["bg"], fg=p["text"], font=fonts.get("display"),
                 anchor="w").pack(fill="x", pady=(0, 2))

    def lead(text: str) -> None:
        tk.Label(body, text=text, bg=p["bg"], fg=p["text2"], font=fonts.get("small"),
                 anchor="w", justify="left", wraplength=860).pack(fill="x", pady=(0, 16))

    def card(heading: str) -> tk.Frame:
        box = tk.Frame(body, bg=p["surface"], highlightthickness=1, highlightbackground=p["border"])
        box.pack(fill="x", pady=(0, 14))
        inner = tk.Frame(box, bg=p["surface"])
        inner.pack(fill="x", padx=22, pady=18)
        tk.Label(inner, text=heading, bg=p["surface"], fg=p["text"], font=fonts.get("h2"),
                 anchor="w").pack(fill="x", pady=(0, 8))
        return inner

    def para(parent, text: str, color: str = None, font_key: str = "body", gap: int = 6) -> None:
        tk.Label(parent, text=text, bg=p["surface"], fg=color or p["text2"], font=fonts.get(font_key),
                 anchor="w", justify="left", wraplength=820).pack(fill="x", pady=(0, gap))

    def step(parent, n: int, head: str, detail: str) -> None:
        row = tk.Frame(parent, bg=p["surface"])
        row.pack(fill="x", pady=(2, 8))
        num = tk.Canvas(row, width=24, height=24, bg=p["surface"], highlightthickness=0)
        num.create_oval(1, 1, 23, 23, fill=p["accent_soft"], outline="")
        num.create_text(12, 12, text=str(n), fill=p["accent"], font=fonts.get("tiny"))
        num.pack(side="left", anchor="n", pady=1)
        txt = tk.Frame(row, bg=p["surface"])
        txt.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(txt, text=head, bg=p["surface"], fg=p["text"], font=fonts.get("body_bold"),
                 anchor="w").pack(fill="x")
        tk.Label(txt, text=detail, bg=p["surface"], fg=p["text2"], font=fonts.get("small"),
                 anchor="w", justify="left", wraplength=760).pack(fill="x")

    def kv_table(parent, rows: list) -> None:
        for k, v in rows:
            row = tk.Frame(parent, bg=p["surface"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=k, bg=p["surface"], fg=p["text3"], font=fonts.get("small"),
                     width=12, anchor="w").pack(side="left")
            tk.Label(row, text=v, bg=p["surface"], fg=p["text"], font=fonts.get("mono"),
                     anchor="w", justify="left", wraplength=640).pack(side="left", fill="x", expand=True)

    title("帮助 & 使用说明")
    lead("ShutterDrop 是一款「拍完即看」的小工具：相机通过 Wi-Fi 把照片 FTP 推送到这台电脑，"
         "程序立刻保存、显示大图、列出 EXIF 参数，方便你在拍摄现场马上检查构图和对焦。"
         "支持索尼 A7M4（ILCE-7M4）与 A7M5（ILCE-7M5），也兼容其他支持「FTP 传输」的索尼相机。")

    c = card("一分钟上手")
    ips = ctl.hosts_for_camera()
    ip_text = " 或 ".join(ips) if ips else "（先在设置里确认本机 IP）"
    step(c, 1, "让相机和电脑连同一个网络",
         "Wi-Fi：相机 MENU → 网络 → Wi-Fi → 连接到访问点，连到和电脑同一个路由器。"
         "有线 LAN：用 USB-C 转网口适配器 + 网线接到同一个路由器（最稳、最快，推荐）。")
    step(c, 2, "在相机里填写本程序的 FTP 服务器",
         f"MENU → 网络 → FTP 传输 → FTP 传输功能 → 服务器设置 → 服务器1：\n"
         f"　　主机名：{ip_text}\n"
         f"　　端口：{ctl.settings.ftp_port}　　安全协议：关闭\n"
         f"　　用户：{ctl.settings.ftp_user}　　密码：{ctl.settings.ftp_password}\n"
         f"　　目录层级：标准　　同名文件：不覆盖（程序也会自动避免覆盖）")
    step(c, 3, "打开相机的 FTP 功能",
         "FTP 传输 → FTP 传输功能 → FTP 功能 → 开。相机屏幕上出现 FTP 连接图标就成功了，"
         "程序顶部会变成绿色的「相机已连接」。")
    step(c, 4, "开启自动传输（拍一张传一张）",
         "FTP 传输 → FTP 传输功能 → 自动 FTP 传输 → 开；自动 FTP 目标 → 静止影像 → 全部。\n"
         "也可以不开自动传输：拍摄后按回放键，用自定义键「FTP (This Img.) 传输本张」手动推送。")
    step(c, 5, "拍照",
         "每张照片传完后，程序会弹出「实时预览」窗口展示 N 秒（N 在设置里改），"
         "并列出光圈、快门、ISO、镜头等 EXIF 参数，倒计时结束自动关闭。")
    if on_goto_settings:
        b = Button(c, "去设置里查看 / 修改连接参数", command=on_goto_settings, kind="primary",
                   palette=p, fonts=fonts, padx=18, pady=8)
        b._resize()
        b.pack(anchor="w", pady=(10, 0))

    c = card("界面怎么看")
    para(c, "顶部状态条：左边是相机连接状态（灰=等待、绿=已连接、橙=正在接收），右边是 FTP 服务开关。")
    para(c, "顶部右侧统计：本次会话接收的照片数量、累计流量、当前上传速度。")
    para(c, "实时预览：收到照片立即弹出，按 空格 暂停/继续倒计时，F 全屏，Esc 或回车关闭。")
    para(c, "最近照片：主界面左侧列表，点任意一张即可再次打开大图与 EXIF 参数。")
    para(c, "传输进度：有文件正在上传时，主界面会显示文件名、进度条、速度与剩余文件数。")
    c_dummy = c

    c = card("设置项说明")
    kv_table(c, [
        ("端口", "FTP 服务监听端口，默认 2121（21 端口需要管理员权限且常被占用，不建议改）。"),
        ("用户名 / 密码", "相机服务器设置里要填同样的值，防止局域网里其他人误连。"),
        ("本机主机名", "自动列出本机局域网 IP，相机里优先填第一个。"),
        ("保存目录", "照片落盘位置，可浏览选择；不存在时保存设置会自动创建。"),
        ("按日期分文件夹", "例如 2026-10-26/DSC01234.JPG，适合连续多天拍摄。"),
        ("保留目录结构", "相机发送 DCIM/100MSDCF/DSC01234.JPG 时，在保存目录下也建同样的子目录。"),
        ("同名覆盖", "关闭时遇到同名文件自动加 _1、_2 后缀，绝不覆盖旧照片。"),
        ("展示时长", "每张照片弹出后显示多少秒；0 表示一直显示，需要手动关闭。"),
        ("展示方式", "窗口（普通窗口）或全屏（适合离相机较远时回看）。"),
        ("EXIF 位置", "参数列表放在大图的右侧、左侧或下方。"),
        ("相机 IP", "可选。填写后只检测该 IP；留空则自动扫描常见网段。"),
    ])
    del c_dummy

    c = card("支持的相机与文件")
    para(c, "索尼 A7M4（ILCE-7M4）与 A7M5（ILCE-7M5）均可使用，还兼容 A1、A7S3、A7R5、A9 III 等"
            "带 FTP 传输功能的机型。A7M5 的服务器设置里如果看到「被动模式」，请保持开启（FTPES/SFTP 请关闭）。")
    para(c, "可接收：JPEG（.JPG）、HEIF（.HIF/.HEIC，会尝试显示内嵌预览）、RAW（.ARW/.DNG，显示 EXIF）、"
            "视频文件（会保存，但不预览）。相机设置「对焦区域只传 JPEG」时体积最小、速度最快。")
    para(c, "安全协议请选「关闭」：本程序提供的是局域网内的普通 FTP，不加密、不联网；"
            "不要在公共网络上使用，用户名密码也不要与其他账号相同。")

    c = card("常见问题")
    problems = [
        ("相机一直显示「连接错误」",
         "1) 确认电脑和相机在同一路由器下（手机热点也可以）；\n"
         "2) 关闭「安全协议」；端口与主机名按设置页填写；\n"
         "3) Windows 防火墙第一次运行时点「允许访问」；或在防火墙里放行程序；\n"
         "4) 电脑若开了 VPN / 虚拟网卡，可能选错 IP，可在设置里换另一个 IP 试试。"),
        ("传得很慢",
         "Wi-Fi 上传一张 24MP JPEG 约 3~8 秒属正常。想要更快要换用 USB-C 转网口的有线 LAN，"
         "并确认网线是千兆、路由器 LAN 口也是千兆。"),
        ("RAW 照片没有预览图",
         "程序会显示占位图但保留 EXIF；RAW 文件本体已经完整保存。想要画面预览请在相机里设置同时传 JPEG。"),
        ("HEIF 没有画面",
         "安装 pillow-heif（可选）：pip install pillow-heif 后重启程序即可解码 HEIF 主图。"),
        ("端口被占用 / 服务启动失败",
         "把端口改成 2121、2122 等 1024 以上的数字；同时确认没有运行其他 FTP 服务（如 FileZilla Server）。"),
        ("照片保存到哪里了",
         "在「设置 → 照片保存位置」里查看，点「打开」可直接打开文件夹；主界面也可以一键打开。"),
    ]
    for q, a in problems:
        para(c, q, color=p["text"], font_key="body_bold", gap=2)
        para(c, a, gap=10)

    c = card("功能一览")
    for line in (
        "• FTP 服务器：被动/主动模式、EPSV、断点续传、UTF-8 中文文件名、目录创建全部支持",
        "• 相机连接状态：控制连接实时状态 + 局域网端口扫描双重判断",
        "• 传输进度：单文件进度、实时速度、剩余时间、队列数量",
        "• 拍完即看：N 秒倒计时大图预览，可暂停、全屏，手动切换",
        "• EXIF：相机、镜头、光圈、快门、ISO、焦距、曝光补偿、白平衡、方向、GPS 等",
        "• 保存设置：目录、日期分组、保留结构、同名策略、自动打开文件夹",
        "• 外观：浅色/深色/跟随系统、界面缩放、EXIF 布局位置",
    ):
        para(c, line, gap=3)

    tk.Label(body, text="ShutterDrop 1.0 · 仅在本机局域网内运行，不会上传任何数据到互联网。",
             bg=p["bg"], fg=p["text3"], font=fonts.get("tiny"), anchor="w").pack(fill="x", pady=(4, 28))
