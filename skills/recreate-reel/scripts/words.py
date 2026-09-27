#!/usr/bin/env python3
"""Dump word-level timings from a yt-dlp json3 auto-caption file.

Usage: words.py captions.en.json3 [start_s] [end_s]

Get the file with:  yt-dlp --skip-download --write-auto-subs --sub-langs en \
                            --sub-format json3 -o "name" <url>
Map a word time into reel time via the chunk's offset/speed from align.py:
  reel_t = reel_anchor + (word_t - src_anchor) / speed
Auto-captions garble names and profanity ([ __ ]) — trust the timing, not the text.
"""
import json, sys

data = json.load(open(sys.argv[1]))
t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
t1 = float(sys.argv[3]) if len(sys.argv) > 3 else 1e9
out = []
for ev in data.get('events', []):
    base = ev.get('tStartMs', 0)
    for seg in ev.get('segs', []) or []:
        w = seg.get('utf8', '').strip()
        if not w:
            continue
        ts = (base + seg.get('tOffsetMs', 0)) / 1000.0
        if t0 <= ts <= t1:
            out.append((ts, w))
out.sort()
for ts, w in out:
    print(f"{ts:8.2f}  {w}")
