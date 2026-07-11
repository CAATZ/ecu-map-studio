from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        Path("C:/Windows/Fonts/seguisb.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
    ):
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def build_icon() -> None:
    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (36, 36, size - 36, size - 36),
        radius=220,
        fill=(8, 13, 24, 255),
        outline=(42, 57, 82, 255),
        width=22,
    )
    draw.rounded_rectangle(
        (112, 112, size - 112, size - 112),
        radius=178,
        fill=(53, 208, 223, 255),
    )

    font = _font(510)
    bounds = draw.textbbox((0, 0), "M", font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        ((size - width) / 2, (size - height) / 2 - bounds[1] - 12),
        "M",
        font=font,
        fill=(4, 16, 20, 255),
    )

    ASSETS.mkdir(parents=True, exist_ok=True)
    png_path = ASSETS / "ECUMapStudio.png"
    ico_path = ASSETS / "ECUMapStudio.ico"
    image.resize((512, 512), Image.Resampling.LANCZOS).save(png_path)
    image.save(
        ico_path,
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    print(png_path)
    print(ico_path)


if __name__ == "__main__":
    build_icon()
