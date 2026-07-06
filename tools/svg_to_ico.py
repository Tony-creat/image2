import os
import subprocess
import sys
import tempfile
from pathlib import Path


def svg_to_png_with_cairosvg(svg_path: Path, png_path: Path) -> bool:
    try:
        import cairosvg

        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=1024, output_height=1024)
        return True
    except Exception:
        return False


def svg_to_png_with_inkscape(svg_path: Path, png_path: Path) -> bool:
    inkscape_cmd = shutil_which("inkscape")
    if not inkscape_cmd:
        return False
    try:
        subprocess.run([inkscape_cmd, "-w", "1024", "-h", "1024", "-o", str(png_path), str(svg_path)], check=True)
        return True
    except Exception:
        return False


def shutil_which(name: str):
    from shutil import which

    return which(name)


def convert(svg_file: Path, ico_file: Path) -> int:
    if not svg_file.exists():
        print(f"SVG not found: {svg_file}")
        return 2

    with tempfile.TemporaryDirectory(prefix="svg2ico_") as td:
        png_path = Path(td) / "temp.png"

        ok = svg_to_png_with_cairosvg(svg_file, png_path)
        if not ok:
            ok = svg_to_png_with_inkscape(svg_file, png_path)

        if not ok or not png_path.exists():
            print("无法自动将 SVG 转为 PNG。请安装 Python 包 'cairosvg' 或在系统中安装 Inkscape，然后重试。")
            return 3

        try:
            from PIL import Image

            im = Image.open(png_path).convert("RGBA")
            sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
            im.save(ico_file, format="ICO", sizes=sizes)
            print(f"生成 ICO 成功：{ico_file}")
            return 0
        except Exception as e:
            print(f"生成 ICO 失败：{e}")
            return 4


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    svg = root / "dist" / "xuantao.svg"
    ico = root / "dist" / "xuantao.ico"
    return convert(svg, ico)


if __name__ == "__main__":
    raise SystemExit(main())
