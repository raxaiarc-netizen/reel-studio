#!/usr/bin/env python
"""Contact sheets: read many slides in one Read instead of one Read each.

usage: sheet.py OUT_PREFIX FILE [FILE ...]   [--per 4] [--cell 800]

Writes OUT_PREFIX_1.jpg, OUT_PREFIX_2.jpg, ... each holding --per images in a
2-column grid, every cell --cell px wide (4:5 aspect), labelled with the file's
stem in the corner so a slide can be referenced by name. 4 per sheet at 800px
keeps tweet-sized body text legible in the Read tool; use --per 6 --cell 640
for headline-only slides.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--per", type=int, default=4)
    ap.add_argument("--cell", type=int, default=800)
    a = ap.parse_args()
    first = Image.open(a.files[0])
    cw, gap = a.cell, 16
    ch = int(a.cell * first.height / first.width)            # cell aspect follows the first image (4:5 slides or 2:1.25 QA pairs)
    cols = 2
    files = [Path(f) for f in a.files]
    del first
    for si in range(0, len(files), a.per):
        chunk = files[si:si + a.per]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw + (cols + 1) * gap, rows * ch + (rows + 1) * gap), (24, 24, 24))
        d = ImageDraw.Draw(sheet)
        for i, f in enumerate(chunk):
            im = Image.open(f).convert("RGB")
            s = min(cw / im.width, ch / im.height)
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
            x = gap + (i % cols) * (cw + gap)
            y = gap + (i // cols) * (ch + gap)
            sheet.paste(im, (x, y))
            d.rectangle((x, y, x + 12 + 9 * len(f.stem), y + 24), fill=(0, 0, 0))
            d.text((x + 6, y + 5), f.stem, fill=(255, 255, 0))
        out = f"{a.prefix}_{si // a.per + 1}.jpg"
        sheet.save(out, quality=88)
        print(out, [f.stem for f in chunk])


if __name__ == "__main__":
    main()
