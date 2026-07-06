from pathlib import Path
import sys

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    svg = root / 'dist' / 'xuantao.svg'
    png = root / 'dist' / 'xuantao.png'
    if not svg.exists():
        print('SVG not found:', svg)
        return 2
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg), write_to=str(png), output_width=512, output_height=512)
        print('Converted to PNG:', png)
        return 0
    except Exception as e:
        print('cairosvg conversion failed:', e)
    try:
        from PIL import Image
        # fallback: try to open as XML and rasterize? not implemented
    except Exception:
        pass
    print('Conversion failed. Install cairosvg or Inkscape.')
    return 3

if __name__ == '__main__':
    raise SystemExit(main())
