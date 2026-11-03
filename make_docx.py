"""生成《ShutterDrop 使用说明》Word 文档（初版，随后再加图片与目录）。"""
import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "ShutterDrop 使用说明.docx")
SHOTS = os.path.join(ROOT, "preview_screens")

ACCENT = RGBColor(0x25, 0x63, 0xEB)
TEXT = RGBColor(0x16, 0x18, 0x1D)
TEXT2 = RGBColor(0x5F, 0x65, 0x70)
EAST_ASIA = "微软雅黑"
LATIN = "Segoe UI"


def set_run_font(run, size=None, bold=None, color=None, east=EAST_ASIA, latin=LATIN):
    run.font.name = latin
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), latin)
    rfonts.set(qn("w:hAnsi"), latin)
    rfonts.set(qn("w:eastAsia"), east)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def style_document(doc):
    normal = doc.styles["Normal"]
    normal.font.name = LATIN
    normal.font.size = Pt(10.5)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), LATIN)
    rfonts.set(qn("w:hAnsi"), LATIN)
    rfonts.set(qn("w:eastAsia"), EAST_ASIA)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25
    for name, size, color in (("Title", 26, ACCENT), ("Heading 1", 16, TEXT),
                              ("Heading 2", 13, TEXT), ("Heading 3", 11.5, TEXT)):
        st = doc.styles[name]
        st.font.name = LATIN
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = color
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:ascii"), LATIN)
        rfonts.set(qn("w:hAnsi"), LATIN)
        rfonts.set(qn("w:eastAsia"), EAST_ASIA)
        st.paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
        st.paragraph_format.space_after = Pt(6)


def shade(cell, hex_color):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcpr.append(shd)


def add_table(doc, header, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(text)
        set_run_font(run, 10, True)
        shade(cell, "EEF0F4")
    for row in rows:
        cells = table.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(text))
            set_run_font(run, 9.5, False)
    if widths:
        table.autofit = False
        for i, w in enumerate(widths):
            for cell in table.columns[i].cells:
                cell.width = Inches(w)
    return table


def para(doc, text, size=10.5, color=TEXT, bold=False, space_after=6, align=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size, bold, color)
    p.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    return p


def bullet(doc, text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    set_run_font(run, size)
    p.paragraph_format.space_after = Pt(2)
    return p


def numbered(doc, text, size=10.5):
    p = doc.add_paragraph(style="List Number")
    run = p.add_run(text)
    set_run_font(run, size)
    p.paragraph_format.space_after = Pt(2)
    return p


def code(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.25)
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(text)
    set_run_font(run, 9.5, False, RGBColor(0x1F, 0x2A, 0x44), east="Consolas", latin="Consolas")


def page_break(doc):
    from docx.enum.text import WD_BREAK
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def figure(doc, filename, caption, width=6.2):
    path = os.path.join(SHOTS, filename)
    if not os.path.exists(path):
        return
    doc.add_picture(path, width=Inches(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cap.add_run(caption)
    set_run_font(run, 9, False, TEXT2)


TABLE_WIDTHS = {
    "项目": [1.3, 5.0],
    "形式": [1.4, 2.6, 2.3],
    "相机项目": [1.2, 2.4, 2.7],
    "设置项": [1.6, 4.7],
    "模块": [1.3, 5.0],
    "路径": [2.4, 3.9],
}


def fix_table_widths():
    from docx import Document as _Doc
    from docx.oxml.ns import qn
    d = _Doc(OUT)
    for t in d.tables:
        head = t.rows[0].cells[0].text.strip()
        widths = TABLE_WIDTHS.get(head)
        if not widths:
            continue
        t.autofit = False
        grid = t._tbl.find(qn("w:tblGrid"))
        if grid is not None:
            for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
                if i < len(widths):
                    gc.set(qn("w:w"), str(int(Inches(widths[i]).twips)))
        for row in t.rows:
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    d.save(OUT)


def main():
    doc = Document()
    style_document(doc)
    section = doc.sections[0]
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)

    # ---------------- 封面
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(80)
    run = p.add_run("ShutterDrop")
    set_run_font(run, 40, True, ACCENT)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("索尼 A7M4 / A7M5 相机 FTP 照片实时接收与预览工具")
    set_run_font(run, 14, False, TEXT2)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(16)
    run = p.add_run("使用说明书 · v1.0")
    set_run_font(run, 12, True, TEXT)
    figure(doc, "01_dashboard.png", "图 0  主界面：相机连接状态、传输进度、最近照片一览", width=5.9)

    # ---------------- 1 概述
    page_break(doc)
    doc.add_heading("1  产品概述", level=1)
    para(doc, "ShutterDrop 是一款运行在 Windows 电脑上的小工具：索尼相机（A7M4 / A7M5，以及其他支持「FTP 传输」"
              "功能的索尼机型）通过 Wi-Fi 或有线网把照片 FTP 推送到这台电脑，程序立即保存、显示大图、列出 EXIF 参数，"
              "让您在拍摄现场就能马上检查构图、对焦与曝光。")
    para(doc, "整个程序只在本机局域网内运行，不会向互联网上传任何内容；除 Python 自带的 Pillow 图形库外，"
              "核心功能不依赖任何第三方服务。")
    doc.add_heading("1.1  主要功能", level=2)
    for t in (
        "相机连接状态：顶部状态胶囊实时显示「等待相机连接 / 相机已连接 / 正在接收照片」，"
        "并额外扫描局域网内的相机端口，判断相机是否开机入网。",
        "传输进度：单张照片的进度条、已传/总大小、实时速度、剩余时间与排队数量。",
        "拍完即看：每张照片传完自动弹出大图，按设置展示 N 秒后自动关闭；可暂停倒计时、全屏展示。",
        "EXIF 参数：相机、镜头、光圈、快门、ISO、焦距、等效焦距、曝光补偿、白平衡、分辨率、方向、GPS 等。",
        "保存位置：任意文件夹、按日期分组、保留相机 DCIM 目录结构、同名自动加序号、磁盘剩余空间。",
        "简洁清晰：自绘圆角卡片与开关，浅色/深色/跟随系统主题，界面缩放，中文帮助页内置完整相机设置步骤。",
    ):
        bullet(doc, t)

    doc.add_heading("1.2  运行环境", level=2)
    add_table(doc, ["项目", "要求"], [
        ["操作系统", "Windows 10 / 11（64 位）"],
        ["硬件", "任何带 Tk 图形界面的普通电脑；与相机在同一个局域网"],
        ["相机", "索尼 A7M4（ILCE-7M4）、A7M5（ILCE-7M5），以及其他支持 FTP 传输的索尼机型"],
        ["网络", "Wi-Fi（同一路由器）或 USB-C 转网口的有线 LAN（推荐，更快更稳）"],
        ["端口", "TCP 2121（默认，可改）+ 随机被动端口；需要 Windows 防火墙放行"],
    ], widths=[1.3, 5.0])

    # ---------------- 2 安装与启动
    page_break(doc)
    doc.add_heading("2  安装与启动", level=1)
    doc.add_heading("2.1  三种启动方式", level=2)
    para(doc, "程序提供三种可用的形式，任选一种即可：")
    add_table(doc, ["形式", "位置", "适用场景"], [
        ["单文件版", "dist\\\\ShutterDrop.exe", "最方便：复制到任何地方双击运行（约 19 MB）"],
        ["便携文件夹版", "ShutterDrop-Portable-Windows.zip（或 dist_onedir\\\\ShutterDrop-Portable）",
         "解压后点「启动 ShutterDrop.bat」；启动速度更快，适合放在 U 盘或固定电脑上"],
        ["Python 源码版", "本目录 main.py（另有 启动 ShutterDrop.bat）",
         "已安装 Python 3.9+ 与 Pillow；方便修改与二次开发"],
    ], widths=[1.4, 2.6, 2.3])
    para(doc, "提示：第一次运行时如果 Windows 弹出「Windows 已保护你的电脑」，点「更多信息 → 仍要运行」即可；"
              "如果弹出防火墙提示，请勾选「专用网络」并点「允许访问」，否则相机会连不上。", color=TEXT2)

    doc.add_heading("2.2  启动后你会看到什么", level=2)
    figure(doc, "01_dashboard.png", "图 1  仪表盘（相机已连接、照片刚保存完成）")
    for t in (
        "顶部左侧：程序名与「相机连接状态」胶囊——灰色=等待相机、蓝色/绿色=已连接、橙色=正在接收。",
        "顶部右侧：「自动启动」开关与「启动 / 停止 FTP 服务」按钮。",
        "左侧「相机连接」卡片：需要填进相机的四行信息（主机名、端口、用户名、密码），并可一键复制。",
        "右侧「传输进度」：正在传输的文件名、百分比、大小、速度与剩余时间。",
        "右下「本次会话」：本次运行收到的照片数、当前速度、总流量、运行时长。",
        "底部「最近照片」：点任意缩略图即可放大并查看 EXIF。",
    ):
        bullet(doc, t, 10)

    # ---------------- 3 相机设置
    doc.add_heading("3  相机端设置（只需一次）", level=1)
    para(doc, "以下以 A7M4 / A7M5 的中文菜单为例（英文菜单在括号中标注）。")
    doc.add_heading("3.1  第一步：让相机和电脑连同一个网络", level=2)
    bullet(doc, "Wi-Fi：MENU → 网络 → Wi-Fi → 连接到访问点（WPS 或手动输入密码），连到和电脑同一个路由器。")
    bullet(doc, "有线 LAN（推荐）：用 USB-C 转网口适配器 + 网线接到同一个路由器；相机 MENU → 网络 → 有线 LAN "
                "设置为自动获取 IP。")
    bullet(doc, "在电脑上打开本程序，「设置 → 本机主机名」里会列出本机局域网 IP（默认路由网卡排在第一位）。")
    doc.add_heading("3.2  第二步：在相机里注册 FTP 服务器", level=2)
    para(doc, "MENU → 网络 → FTP 传输 → FTP 传输功能 → 服务器设置 → 服务器1，按下表填写：")
    add_table(doc, ["相机项目", "填写内容", "说明"], [
        ["显示名称", "如 PC", "任意，最长为 8 个字符"],
        ["主机名称", "程序显示的 IP，如 192.168.1.20", "电脑的局域网地址"],
        ["端口", "2121", "与程序「设置 → 端口」一致"],
        ["安全协议", "关闭", "本程序为局域网内普通 FTP；不要选 FTPES / SFTP"],
        ["用户 / 密码", "sony / sony1234", "与程序「设置」一致，建议改成自己的"],
        ["目录层级", "标准", "若想保留 DCIM 目录结构，程序里也能按原样保存"],
        ["同名文件", "不覆盖", "程序遇到同名也会自动加 _1、_2 后缀"],
    ], widths=[1.2, 2.4, 2.7])
    para(doc, "注意：A7M5 的服务器设置里如果出现「被动模式」，请保持开启；「安全协议」保持关闭。", color=TEXT2)
    doc.add_heading("3.3  第三步：打开 FTP 并开启自动传输", level=2)
    numbered(doc, "MENU → 网络 → FTP 传输 → FTP 传输功能 → FTP 功能 → 开。")
    numbered(doc, "MENU → 网络 → FTP 传输 → FTP 传输功能 → 自动 FTP 传输 → 开；自动 FTP 目标 → 静止影像 → 全部。")
    numbered(doc, "相机录制待机画面出现 FTP 连接图标，程序顶部变为绿色「相机已连接」，说明一切就绪。")
    para(doc, "不想开自动传输时：拍摄后在回放画面按自定义键「FTP Trans. (This Img.)」即可手动推送当前这张。")

    # ---------------- 4 界面说明
    page_break(doc)
    doc.add_heading("4  界面说明", level=1)
    doc.add_heading("4.1  仪表盘", level=2)
    para(doc, "仪表盘把「相机是否连接」「传输进度」「照片存到哪里」「最近拍的照片」放在同一屏，是最常用的页面。")
    doc.add_heading("4.2  实时预览（拍完即看）", level=2)
    figure(doc, "02_realtime_preview.png", "图 2  每张照片传完自动弹出：顶部倒计时，右侧 EXIF 参数")
    for t in (
        "顶部蓝色文字显示「N 秒后自动关闭」，下面的进度条同步倒计时。",
        "空格键：暂停 / 继续倒计时；F 键：切换全屏；Esc 或回车：立即关闭。",
        "右侧「照片参数」列出相机、镜头、光圈、快门、ISO、焦距、拍摄时间等；可在设置里改到左侧或下方。",
        "展示时长可在「设置 → 拍完即看 → 每张展示时长」里设定（0 表示一直显示）。",
    ):
        bullet(doc, t, 10)
    doc.add_heading("4.3  设置", level=2)
    figure(doc, "03_settings_ftp.png", "图 3  设置页：FTP 连接与照片保存位置")
    figure(doc, "04_settings_preview.png", "图 4  设置页：拍完即看（展示时长、展示方式、EXIF 位置）")
    figure(doc, "05_settings_bottom.png", "图 5  设置页：相机在线检测与外观")
    doc.add_heading("4.4  使用说明页", level=2)
    figure(doc, "06_help_top.png", "图 6  内置帮助页：五分钟上手、界面说明、常见问题")

    # ---------------- 5 设置项
    page_break(doc)
    doc.add_heading("5  设置项一览", level=1)
    add_table(doc, ["设置项", "说明"], [
        ["端口", "FTP 服务监听端口，默认 2121；21 端口需要管理员权限且常被占用，不建议使用。"],
        ["用户名 / 密码", "相机服务器设置里填同样的值，防止局域网内误连。"],
        ["本机主机名", "自动列出本机局域网 IP，相机里优先填第一个。"],
        ["启动时自动开启", "打开程序即自动运行 FTP 服务。"],
        ["保存目录", "照片落盘位置，可浏览选择；不存在时保存设置会自动创建。"],
        ["按日期建子文件夹", "例如 2026-10-26/DSC01234.JPG。"],
        ["保留相机目录结构", "相机发送 DCIM/100MSDCF/DSC01234.JPG 时原样保留子目录。"],
        ["同名文件覆盖", "关闭时遇到同名文件自动加 _1、_2 后缀，绝不覆盖旧照片。"],
        ["接收完打开文件夹", "每收到一张照片自动打开其所在文件夹。"],
        ["每张展示时长", "照片弹出后展示多少秒，0 = 一直显示；也可点 3/5/10/20/30 秒快捷键。"],
        ["展示方式", "窗口，或全屏（适合离相机稍远时回看）。"],
        ["EXIF 位置", "参数列表放在大图的右侧、左侧或下方。"],
        ["新照片自动弹出", "关闭后照片只出现在「最近照片」里，不自动弹窗。"],
        ["相机 IP（可选）", "填写后只检测该 IP；留空则自动扫描常见网段。"],
        ["检测间隔 / 离线判定", "多久扫描一次；多久没有任何连接算是断开。"],
        ["主题 / 界面缩放", "浅色、深色、跟随系统；0.8× ~ 1.6×，修改缩放需重启程序。"],
    ], widths=[1.6, 4.7])

    # ---------------- 6 常见问题
    page_break(doc)
    doc.add_heading("6  常见问题", level=1)
    qa = [
        ("相机一直显示「连接错误」",
         "① 确认电脑和相机在同一路由器下；② 相机「安全协议」设为关闭；端口与主机名按程序设置页填写；"
         "③ Windows 防火墙第一次运行时点「允许访问」，或在防火墙里手动放行程序；"
         "④ 电脑开了 VPN 或虚拟网卡时可能选错 IP，可在设置里换另一个 IP 试试。"),
        ("相机连上了，但拍照后没有自动上传",
         "确认相机菜单里「自动 FTP 传输」为开、「自动 FTP 目标 → 静止影像」为全部；"
         "若是 RAW+JPEG 双格式，可在「RAW+J/H 传输目标」里选择只传 JPEG，速度最快。"),
        ("传得很慢",
         "Wi-Fi 传一张 24MP JPEG 约 3~8 秒属正常。想要更快请改用 USB-C 转网口的有线 LAN，"
         "并确认网线、路由器 LAN 口都是千兆。"),
        ("RAW 照片没有预览图",
         "程序会显示占位图，但文件已完整保存且能显示 EXIF。想要画面预览，可在相机里设置「RAW+J/H 传输目标 → "
         "JPEG & HEIF」，让 JPEG 一起传。"),
        ("HEIF 照片没有画面",
         "程序会从 HEIF 文件里提取内嵌预览显示；如果仍为空白，说明该文件没有内嵌 JPEG，可用 "
         "pip install pillow-heif 后重启程序（便携版与单文件版已内置该解码器）。"),
        ("端口被占用 / 服务启动失败",
         "把端口改成 2121、2122 等 1024 以上的数字；同时确认没有运行其他 FTP 服务（如 FileZilla Server）。"),
        ("照片保存到哪里了",
         "在「设置 → 照片保存位置」里查看，点「打开」可直接打开文件夹；仪表盘上也有「打开文件夹」按钮。"),
        ("同时开多台电脑 / 多台相机",
         "每台电脑用一个端口即可；程序只接受图片、视频类文件，同名文件自动加序号，不会互相覆盖。"),
    ]
    for q, a in qa:
        p = doc.add_paragraph()
        run = p.add_run("问：" + q)
        set_run_font(run, 10.5, True, TEXT)
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p = doc.add_paragraph()
        run = p.add_run("答：" + a)
        set_run_font(run, 10, False, TEXT2)

    # ---------------- 7 技术说明
    page_break(doc)
    doc.add_heading("7  技术说明", level=1)
    add_table(doc, ["模块", "说明"], [
        ["FTP 服务器", "标准库实现的 FTP 服务：被动（PASV / EPSV）与主动（PORT / EPRT）双模式、断点续传（REST / APPE）、"
                  "UTF-8 中文文件名、目录创建、ASCII 模式换行还原；只接受图片/视频扩展名，路径不能越出保存目录。"],
        ["EXIF 解析", "JPEG / PNG 使用 Pillow；RAW（.ARW / .DNG）用内置 TIFF 解析器直接读取，即使没有缩略图也能显示参数。"],
        ["HEIF 预览", "从 HEIF 容器中解析 meta / iinf / iloc，提取内嵌 JPEG；附带 pillow-heif 时可直接解码主图。"],
        ["相机检测", "按设置间隔探测相机常见端口 21 / 15740 / 64321，任意端口可连通即认为相机入网。"],
        ["安全边界", "只监听本机网卡，不连接互联网，不执行相机发来的任何内容，只按文件名保存上传的文件。"],
    ], widths=[1.3, 5.0])
    doc.add_heading("7.1  命令行参数", level=2)
    code(doc, "ShutterDrop.exe --port 2121 --photo-dir \"D:\\\\Photos\\\\ShutterDrop\" --verbose")
    bullet(doc, "--port 本次运行临时指定 FTP 端口（不写入设置）", 10)
    bullet(doc, "--photo-dir 本次运行临时指定照片保存目录", 10)
    bullet(doc, "--no-autostart 启动后不自动开启 FTP 服务", 10)
    bullet(doc, "--verbose 输出详细日志（日志位置：%APPDATA%\\\\ShutterDrop\\\\shutterdrop.log）", 10)
    doc.add_heading("7.2  源码目录结构", level=2)
    add_table(doc, ["路径", "内容"], [
        ["main.py", "程序入口（启动窗口与服务）"],
        ["shutterdrop/core.py", "配置读写、目录与格式化工具"],
        ["shutterdrop/ftpserver.py", "FTP 服务器（被动/主动、续传、目录、配额限制）"],
        ["shutterdrop/detector.py", "相机在线检测"],
        ["shutterdrop/exif_reader.py", "EXIF 读取（Pillow + 内置 TIFF 解析）"],
        ["shutterdrop/imaging.py", "图片解码、缩略图、HEIF 内嵌预览提取"],
        ["shutterdrop/app.py", "业务层：状态、传输、照片库、设置应用"],
        ["shutterdrop/ui/", "界面层：主题、自绘控件、主窗口、预览窗、设置页、帮助页"],
        ["shutterdrop/mock.py", "仿真照片生成与模拟相机（测试用）"],
        ["tests/", "单元测试、端到端 FTP 测试、界面冒烟测试、截图脚本"],
        ["build_exe.py", "打包单文件 exe；build_onedir.py 打包文件夹版"],
    ], widths=[2.0, 4.3])

    # ---------------- 附录
    page_break(doc)
    doc.add_heading("附录 A  快速检查清单", level=1)
    for t in (
        "电脑与相机连在同一个路由器（或同一 Wi-Fi）。",
        "程序已启动，顶部显示「启动 FTP 服务 / 停止 FTP 服务」可按，端口无报错。",
        "相机服务器设置：主机名 = 程序显示的 IP，端口 = 程序端口，安全协议 = 关闭，用户名密码一致。",
        "相机「FTP 功能」= 开，「自动 FTP 传输」= 开。",
        "防火墙已放行程序（专用网络）。",
        "拍一张 JPEG，程序在几秒内弹出预览并保存到设置的目录。",
    ):
        bullet(doc, "□ " + t, 10)

    # 重新检查所有表格列宽（前一步保存后再统一修正一次，避免列宽被自动调整）
    fix_table_widths()
    doc.save(OUT)
    print("saved:", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
