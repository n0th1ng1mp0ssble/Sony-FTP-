"""生成程序图标 assets/shutterdrop.ico（相机镜头 + 向下箭头，表示“照片落盘”）。"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "assets")
OUT = os.path.join(OUT_DIR, "shutterdrop.ico")

ACCENT = (37, 99, 235)
ACCENT_DARK = (30, 79, 190)
WHITE = (255, 255, 255)


def draw(size: int) -> Image.Image:
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(s * 0.22)
    # 圆角方形底
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=ACCENT + (255,))
    # 镜头外圈
    cx, cy = s * 0.5, s * 0.46
    R = s * 0.27
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=WHITE + (255,), width=max(2, int(s * 0.05)))
    d.ellipse([cx - R * 0.55, cy - R * 0.55, cx + R * 0.55, cy + R * 0.55], fill=(255, 255, 255, 70))
    d.ellipse([cx - R * 0.42, cy - R * 0.42, cx + R * 0.42, cy + R * 0.42], fill=ACCENT_DARK + (255,))
    d.ellipse([cx - R * 0.16, cy - R * 0.16, cx + R * 0.16, cy + R * 0.16], fill=WHITE + (230,))
    img = img.resize((size, size), Image.LANCZOS)
    return img


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(n) for n in sizes]
    imgs[-1].save(OUT, format="ICO", sizes=[(n, n) for n in sizes], append_images=imgs[:-1])
    # 顺便存一张 PNG 供文档使用
    imgs[-1].save(os.path.join(OUT_DIR, "icon.png"))
    print("icon ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
