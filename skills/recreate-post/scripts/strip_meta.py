#!/usr/bin/env python
"""Strip ALL metadata from a generated image and write it under a clean name.

usage: strip_meta.py IN OUT      (OUT extension picks the format: .png / .jpg)

Two passes, because ChatGPT PNGs carry a C2PA/JUMBF manifest (caBX chunk),
XMP and tEXt that a single tool can miss:
  1. Pillow re-encode: pixels only — unknown chunks (caBX), text chunks, EXIF,
     XMP and ICC are all dropped because nothing is passed to save().
  2. exiftool -all= on the result, then a verification read: anything left
     outside the File/PNG/JPEG structure groups is a failure (exit 1).
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

# Tags that describe the container itself, never provenance. Everything else
# (PNG:Software, XMP, EXIF, JUMBF/C2PA, ICC_Profile ...) means the strip failed.
ALLOWED = {
    "SourceFile", "ExifTool", "File", "Composite",
    "PNG:ImageWidth", "PNG:ImageHeight", "PNG:BitDepth", "PNG:ColorType",
    "PNG:Compression", "PNG:Filter", "PNG:Interlace",
    "JFIF:JFIFVersion", "JFIF:ResolutionUnit", "JFIF:XResolution", "JFIF:YResolution",
}


def is_allowed(tag: str) -> bool:
    return tag in ALLOWED or tag.split(":")[0] in ALLOWED


def main(src: str, dst: str) -> int:
    out = Path(dst)
    out.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src)
    im.load()
    clean = Image.new("RGB", im.size)
    clean.paste(im.convert("RGB"))          # fresh image object: no .info carried over
    if out.suffix.lower() in (".jpg", ".jpeg"):
        clean.save(out, "JPEG", quality=95, subsampling=0)
    else:
        clean.save(out, "PNG", compress_level=6)

    subprocess.run(["exiftool", "-all=", "-overwrite_original", "-q", str(out)], check=True)

    tags = json.loads(subprocess.check_output(["exiftool", "-j", "-G", str(out)]))[0]
    leftover = sorted(k for k in tags if not is_allowed(k))
    if leftover:
        print(f"STRIP-FAILED {out}: leftover tags {leftover}", file=sys.stderr)
        return 1
    print(f"{out}  {clean.size[0]}x{clean.size[1]}  clean")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
