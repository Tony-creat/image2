from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def find_font(preferred=('Microsoft YaHei UI','Segoe UI','Arial')):
    from PIL import ImageFont
    for name in preferred:
        try:
            return ImageFont.truetype(name, 10)
        except Exception:
            continue
    return ImageFont.load_default()

def generate(output: Path, text='xuantao'):
    w, h = 900, 120
    base = Image.new('RGBA', (w, h), (18, 18, 20, 255))

    # gradient
    for i in range(h):
        a = int(24 + (i / h) * 32)
        ImageDraw.Draw(base).line([(0,i),(w,i)], fill=(18,18+a,24+a,255))

    draw = ImageDraw.Draw(base)
    font = None
    for size in (72,64,56,48):
        try:
            font = ImageFont.truetype('msyh.ttf', size)
            break
        except Exception:
            try:
                font = ImageFont.truetype('arial.ttf', size)
                break
            except Exception:
                font = ImageFont.load_default()

    # text shadow / glow
    txt = Image.new('RGBA', base.size, (0,0,0,0))
    d = ImageDraw.Draw(txt)
    tw, th = d.textsize(text, font=font)
    x = 24
    y = (h - th) // 2

    # shadow
    d.text((x+4, y+6), text, font=font, fill=(0,0,0,180))
    # main text with subtle gradient
    # draw layered fills
    d.text((x+0, y+0), text, font=font, fill=(240,240,242,255))
    d.text((x, y), text, font=font, fill=(220,220,224,220))

    blurred = txt.filter(ImageFilter.GaussianBlur(2))
    base = Image.alpha_composite(base, blurred)
    base = Image.alpha_composite(base, txt)

    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output)
    print('Generated title image at', output)

if __name__ == '__main__':
    out = Path(__file__).resolve().parents[1] / 'dist' / 'xuantao_title.png'
    generate(out)
