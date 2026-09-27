#!/usr/bin/env python
"""Deliver Canva exports — one call: download, verify, QA sheet, Masters + final.

usage: export_dl.py "SUBJECT" URL [URL ...]          (run from the job/work dir)
       export_dl.py "SUBJECT" --from-dir post          (files already in post/)

Downloads each URL (in order) to post/slide_NN.jpg untouched (Canva's metadata
stays), checks every file is 1080x1350, builds qa/pair_NN.jpg (source | post)
and qa/pairs_1.jpg... contact sheets of those pairs, then copies to
<BASE>/Masters/Posts/SUBJECT/ and ./final/. BASE is the SSD if mounted, else
~/ReelStudio. Exit 1 on a bad download or wrong dimensions.
"""
import os
import shutil
import subprocess
import sys
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STORAGE = os.path.expanduser("~/ReelStudio")


def base():
    return os.environ.get("REELSTUDIO_DIR", DEFAULT_STORAGE)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    subject = sys.argv[1]
    os.makedirs("post", exist_ok=True)
    os.makedirs("qa", exist_ok=True)
    os.makedirs("final", exist_ok=True)
    if sys.argv[2] == "--from-dir":
        files = sorted(f for f in os.listdir("post") if f.endswith(".jpg"))
    else:
        files = []
        for i, url in enumerate(sys.argv[2:], 1):
            name = f"slide_{i:02d}.jpg"
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=120) as r, open(os.path.join("post", name), "wb") as f:
                f.write(r.read())
            files.append(name)
    bad = []
    for name in files:
        p = os.path.join("post", name)
        try:
            im = Image.open(p)
            im.load()
            ok = im.size == (1080, 1350)
        except Exception:
            ok = False
        print(f"{name}: {os.path.getsize(p)} bytes {'1080x1350' if ok else 'BAD'}")
        if not ok:
            bad.append(name)
    if bad:
        print("BAD exports:", " ".join(bad))
        sys.exit(1)
    pairs = []
    for name in files:
        nn = name[6:8]
        src = f"source/slide_{nn}.jpg"
        out = f"qa/pair_{nn}.jpg"
        if os.path.exists(src) and os.path.exists(FFMPEG):
            subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", src, "-i", os.path.join("post", name),
                            "-filter_complex", "[0]scale=540:675[a];[1]scale=540:675[b];[a][b]hstack", out], check=False)
            if os.path.exists(out):
                pairs.append(out)
    if pairs:
        subprocess.run([sys.executable, os.path.join(HERE, "sheet.py"), "qa/pairs", *pairs, "--per", "4", "--cell", "1080"],
                       check=False)
    dest = os.path.join(base(), "Masters", "Posts", subject)
    os.makedirs(dest, exist_ok=True)
    for name in files:
        shutil.copy2(os.path.join("post", name), os.path.join(dest, name))
        shutil.copy2(os.path.join("post", name), os.path.join("final", name))
    if os.path.exists("status.txt"):
        with open("status.txt", "w") as f:
            f.write(f"6/6|delivered {len(files)} slides")
    print(f"delivered {len(files)} slides → {dest} and ./final/ ; QA sheets: qa/pairs_*.jpg")


if __name__ == "__main__":
    main()
