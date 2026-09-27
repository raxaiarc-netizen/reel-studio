#!/usr/bin/env python3
"""Compose one post slide from a JSON spec: background + image layers + crisp text.

Usage: compose.py spec.json

Spec:
{
 "canvas": [1080, 1350],
 "background": "gen/slide_01_bg.png",     // path, or "#101014" solid, or omit for black
 "bg_fit": "cover",                       // cover (default) | stretch
 "darken": 0.25,                          // optional 0-1 black scrim over the background
 "images": [                              // optional layers, drawn in order
   {"path": "logo.png", "pos": [540, 90], "anchor": "mm", "width": 220, "opacity": 1.0}
 ],
 "texts": [
   {"text": "THE REAL COST\nOF COMFORT",
    "font": "Montserrat-Bold",            // family name (bundled) or absolute .ttf path
    "size": 64, "color": "#FFFFFF",
    "pos": [540, 620], "anchor": "mm",    // Pillow anchors: mm, ma, md, lm, rm...
    "align": "center",
    "max_width": 900,                     // wrap to this pixel width (omit = no wrap)
    "line_spacing": 1.25,
    "tracking": 0,                        // extra px between characters
    "variation": 700,                     // variable-font weight axis (Playfair)
    "shadow": {"offset": [0, 3], "blur": 8, "color": "#000000", "opacity": 0.55}
 ],
 "out": "post/slide_01.jpg",
 "quality": 95
}
Bundled families resolve from assets/fonts (Montserrat-* statics,
PlayfairDisplay-Variable + -Italic-Variable).
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'assets', 'fonts')


def font_path(name):
    if os.path.sep in name or name.endswith('.ttf') or name.endswith('.otf'):
        return name
    p = os.path.join(FONTS, name + '.ttf')
    if os.path.exists(p):
        return p
    sys.exit(f"compose: no font '{name}' — bundled: "
             + ', '.join(sorted(f[:-4] for f in os.listdir(FONTS))))


def load_font(t):
    f = ImageFont.truetype(font_path(t.get('font', 'Montserrat-SemiBold')),
                           int(t.get('size', 48)))
    if t.get('variation'):
        f.set_variation_by_axes([t['variation']])
    return f


def text_w(draw, s, font, tracking):
    w = draw.textlength(s, font=font)
    return w + tracking * max(0, len(s) - 1)


def wrap(draw, text, font, max_w, tracking):
    lines = []
    for para in text.split('\n'):
        words, cur = para.split(' '), ''
        for w in words:
            t = (cur + ' ' + w).strip()
            if cur and text_w(draw, t, font, tracking) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
    return lines


def draw_line(draw, xy, s, font, fill, tracking):
    if not tracking:
        draw.text(xy, s, font=font, fill=fill)
        return
    x, y = xy
    for ch in s:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def render_text(base, t):
    font = load_font(t)
    tracking = t.get('tracking', 0)
    meas = ImageDraw.Draw(base)
    lines = wrap(meas, t['text'], font, t['max_width'], tracking) \
        if t.get('max_width') else t['text'].split('\n')
    asc, desc = font.getmetrics()
    lh = (asc + desc) * t.get('line_spacing', 1.2)
    block_h = lh * len(lines)
    x, y = t['pos']
    anchor = t.get('anchor', 'mm')
    ha, va = anchor[0], anchor[1]
    top = y - block_h / 2 if va == 'm' else y - block_h if va in 'ds' else y
    align = t.get('align', 'center' if ha == 'm' else 'left' if ha == 'l' else 'right')

    layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, s in enumerate(lines):
        lw = text_w(d, s, font, tracking)
        lx = x - lw / 2 if align == 'center' else x - lw if align == 'right' else x
        draw_line(d, (lx, top + i * lh), s, font, t.get('color', '#FFFFFF'), tracking)

    sh = t.get('shadow')
    if sh:
        shadow = Image.new('RGBA', base.size, (0, 0, 0, 0))
        alpha = layer.split()[3].point(
            lambda a: int(a * sh.get('opacity', 0.55)))
        tint = Image.new('RGBA', base.size, sh.get('color', '#000000'))
        shadow.paste(tint, (0, 0), alpha)
        shadow = shadow.transform(
            base.size, Image.AFFINE,
            (1, 0, -sh.get('offset', [0, 3])[0], 0, 1, -sh.get('offset', [0, 3])[1]))
        if sh.get('blur'):
            shadow = shadow.filter(ImageFilter.GaussianBlur(sh['blur']))
        base.alpha_composite(shadow)
    base.alpha_composite(layer)


def main():
    spec = json.load(open(sys.argv[1]))
    W, H = spec.get('canvas', [1080, 1350])
    bg = spec.get('background', '#000000')
    if isinstance(bg, str) and bg.startswith('#'):
        img = Image.new('RGBA', (W, H), bg)
    else:
        src = Image.open(bg).convert('RGBA')
        if spec.get('bg_fit', 'cover') == 'stretch':
            img = src.resize((W, H), Image.LANCZOS)
        else:
            scale = max(W / src.width, H / src.height)
            src = src.resize((round(src.width * scale), round(src.height * scale)),
                             Image.LANCZOS)
            img = src.crop(((src.width - W) // 2, (src.height - H) // 2,
                            (src.width - W) // 2 + W, (src.height - H) // 2 + H))
    if spec.get('darken'):
        img.alpha_composite(Image.new(
            'RGBA', (W, H), (0, 0, 0, int(255 * spec['darken']))))

    for layer in spec.get('images', []):
        im = Image.open(layer['path']).convert('RGBA')
        if layer.get('width'):
            r = layer['width'] / im.width
            im = im.resize((layer['width'], round(im.height * r)), Image.LANCZOS)
        if layer.get('opacity', 1) < 1:
            a = im.split()[3].point(lambda v: int(v * layer['opacity']))
            im.putalpha(a)
        x, y = layer['pos']
        anchor = layer.get('anchor', 'mm')
        if anchor[0] == 'm':
            x -= im.width // 2
        elif anchor[0] == 'r':
            x -= im.width
        if anchor[1] == 'm':
            y -= im.height // 2
        elif anchor[1] in 'ds':
            y -= im.height
        img.alpha_composite(im, (int(x), int(y)))

    for t in spec.get('texts', []):
        render_text(img, t)

    out = spec['out']
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    img.convert('RGB').save(out, quality=spec.get('quality', 95),
                            subsampling=0, optimize=True)
    print(f"COMPOSED: {out} ({W}x{H})")


if __name__ == '__main__':
    main()
