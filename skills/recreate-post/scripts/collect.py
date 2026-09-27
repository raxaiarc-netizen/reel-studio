#!/usr/bin/env python
"""Collect a wave of ChatGPT downloads, strip them, and report — one call per wave.

usage: collect.py SLUG NN:SIZE [NN:SIZE ...]        (run from the job/work dir)
   e.g. collect.py lm-brics-us-panic 06:1491134 07:877152 08:931335

For each slide NN it takes ~/Downloads/SLUG_NN.png if present (the download
name is the post slug, so two posts running at once never collide), else the
newest file in ~/Downloads whose byte size equals SIZE (Brave parks interrupted
downloads as ~/Downloads/.com.brave.Browser.XXXXXX with the full bytes), moves it
to raw/slide_NN.png, then runs strip_meta.py → gen/SLUG_NN.png. Deletes the
0-byte "Unconfirmed *.crdownload" stubs Brave leaves behind. Updates status.txt
(panel jobs) if it exists. Prints one line per slide and a final MISSING list;
exit 1 if anything is missing so the caller retries those in fresh tabs.
"""
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DL = os.path.expanduser("~/Downloads")


def find_by_size(size, newer_than):
    hits = []
    for f in glob.glob(os.path.join(DL, "*")) + glob.glob(os.path.join(DL, ".com.brave.Browser.*")):
        try:
            st = os.stat(f)
        except OSError:
            continue
        if st.st_size == size and st.st_mtime >= newer_than and os.path.isfile(f):
            hits.append((st.st_mtime, f))
    return max(hits)[1] if hits else None


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    slug, specs = sys.argv[1], sys.argv[2:]
    os.makedirs("raw", exist_ok=True)
    os.makedirs("gen", exist_ok=True)
    recent = time.time() - 3600
    missing, done = [], []
    for spec in specs:
        nn, size = spec.split(":")
        size = int(size)
        raw = f"raw/slide_{nn}.png"
        src = None
        if os.path.exists(raw) and os.path.getsize(raw) == size:
            src = raw
        else:
            named = os.path.join(DL, f"{slug}_{nn}.png")
            if os.path.exists(named) and os.path.getsize(named) == size:
                src = named
            else:
                src = find_by_size(size, recent)
            if src:
                os.replace(src, raw)
        if not src:
            print(f"slide {nn}: MISSING ({size} bytes not in ~/Downloads)")
            missing.append(nn)
            continue
        out = f"gen/{slug}_{nn}.png"
        r = subprocess.run([PY, os.path.join(HERE, "strip_meta.py"), raw, out], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"slide {nn}: STRIP-FAILED {r.stderr.strip()}")
            missing.append(nn)
        else:
            print(f"slide {nn}: ok → {out}")
            done.append(nn)
    for stub in glob.glob(os.path.join(DL, "Unconfirmed *.crdownload")):
        if os.path.getsize(stub) == 0:
            os.remove(stub)
    have = len(glob.glob("gen/*.png"))
    total = len(glob.glob("source/slide_*.jpg")) or "?"
    if os.path.exists("status.txt"):
        with open("status.txt", "w") as f:
            f.write(f"3/6|generating imagery ({have} of {total} slides)")
    print(f"collected {len(done)}, gen has {have}/{total}" + (f", MISSING: {' '.join(missing)}" if missing else ""))
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
