"""Generate Laneora logo.png and app.ico."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "resources"
OUT.mkdir(parents=True, exist_ok=True)

BG = (11, 18, 32, 255)
PANEL = (20, 28, 43, 255)
AMBER = (245, 165, 36, 255)
AMBER_DIM = (216, 144, 18, 255)
WHITE = (232, 238, 247, 255)


def make_mark(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = size // 12
    d.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 6,
        fill=PANEL,
    )
    # stylized dual-lane route
    lane_w = size // 14
    cx = size // 2
    top = size // 4
    bot = size - size // 4
    d.rounded_rectangle([cx - lane_w * 2, top, cx - lane_w // 2, bot], radius=lane_w // 2, fill=AMBER)
    d.rounded_rectangle([cx + lane_w // 2, top, cx + lane_w * 2, bot], radius=lane_w // 2, fill=AMBER_DIM)
    # horizon arc
    d.arc(
        [size // 5, size // 5, size - size // 5, size // 2],
        start=200,
        end=340,
        fill=WHITE,
        width=max(4, size // 48),
    )
    # accent node
    r = size // 18
    d.ellipse([cx - r, top - r, cx + r, top + r], fill=AMBER)
    return img


def main() -> None:
    mark = make_mark(512)
    # logo with wordmark area for splash
    logo = Image.new("RGBA", (720, 240), BG)
    logo.paste(mark.resize((200, 200), Image.Resampling.LANCZOS), (40, 20), mark.resize((200, 200), Image.Resampling.LANCZOS))
    d = ImageDraw.Draw(logo)
    d.text((270, 70), "LANEORA", fill=AMBER)
    d.text((270, 130), "DAT board streams", fill=WHITE)
    logo_path = OUT / "logo.png"
    mark_path = OUT / "mark.png"
    ico_path = OUT / "app.ico"
    logo.save(logo_path)
    mark.save(mark_path)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons = [mark.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    icons[0].save(ico_path, format="ICO", sizes=sizes, append_images=icons[1:])
    print("wrote", logo_path, mark_path, ico_path)


if __name__ == "__main__":
    main()
