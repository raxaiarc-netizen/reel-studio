#!/usr/bin/env python3
"""Map a reel's audio timeline onto a source clip's timeline.

Slides 2s windows of the reel over the source via normalized cross-correlation
(FFT). Constant offset runs = continuous chunks lifted from that source; offset
jumps = edit points; a slowly drifting offset = the reel is speed-shifted
(offset drift of +0.3s over 30s ~= a 1% speed-up, a common content-ID dodge).

Usage: align.py reel_8k.wav source_8k.wav [--start S] [--end S] [--step 0.5]
Both wavs must be mono 16-bit at the same rate (8000 Hz recommended:
  ffmpeg -i in.mp4 -vn -ac 1 -ar 8000 out_8k.wav)
"""
import argparse
import wave
import numpy as np

def load(path):
    w = wave.open(path, 'rb')
    assert w.getsampwidth() == 2 and w.getnchannels() == 1, f"{path}: need mono 16-bit"
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    sr = w.getframerate()
    w.close()
    return x, sr

p = argparse.ArgumentParser()
p.add_argument('reel')
p.add_argument('source')
p.add_argument('--start', type=float, default=0.0)
p.add_argument('--end', type=float, default=None)
p.add_argument('--step', type=float, default=0.5)
args = p.parse_args()

reel, sr = load(args.reel)
src, sr2 = load(args.source)
assert sr == sr2, "sample rates differ"
end = args.end if args.end is not None else len(reel) / sr

W = int(2.0 * sr)
N = len(src)
nfft = 1 << (N + W).bit_length()
SRC_F = np.fft.rfft(src, nfft)
src_energy = np.concatenate(([0.0], np.cumsum(src * src)))

rows = []
print(f"{'reel_t':>7} {'src_t':>8} {'offset':>8} {'ncc':>6}")
prev = None
t = args.start
while t + 2.0 <= end + 1e-9:
    a = int(t * sr)
    win = reel[a:a + W]
    if len(win) < W:
        break
    win = win - win.mean()
    we = float(np.dot(win, win))
    if we > 1e-6:
        c = np.fft.irfft(SRC_F * np.conj(np.fft.rfft(win, nfft)), nfft)[:N - W]
        le = src_energy[W:N] - src_energy[:N - W]
        ncc = c / np.sqrt(np.maximum(le * we, 1e-9))
        k = int(np.argmax(ncc))
        st, score = k / sr, float(ncc[k])
        off = st - t
        jump = "" if prev is None or abs(off - prev) < 0.08 else "  <-- JUMP"
        flag = " (weak)" if score < 0.22 else ""
        print(f"{t:7.1f} {st:8.2f} {off:8.2f} {score:6.3f}{flag}{jump}")
        if score >= 0.22:
            prev = off
        rows.append((t, st, off, score))
    t += args.step

# Auto chunk summary: runs of near-constant offset -> continuous lifts,
# with a least-squares speed fit (offset drift = speed shift).
strong = [r for r in rows if r[3] >= 0.35]
chunks, cur = [], []
for r in strong:
    if cur and (abs(r[2] - cur[-1][2]) > 0.15 or r[0] - cur[-1][0] > 3 * args.step + 1e-9):
        chunks.append(cur)
        cur = []
    cur.append(r)
if cur:
    chunks.append(cur)
printable = [c for c in chunks if len(c) >= 3]
if printable:
    print("\nCHUNKS (contiguous spans lifted from this source; boundaries +-1 window):")
    for ch in printable:
        ts = [r[0] for r in ch]
        ss = [r[1] for r in ch]
        b, a0 = np.polyfit(ts, ss, 1)
        reel_in, reel_out = ts[0], ts[-1] + 2.0
        print(f"  reel {reel_in:6.1f}-{reel_out:6.1f}  src_in {a0 + b * reel_in:8.2f}"
              f"  speed {b:.4f}  (n={len(ch)}, ncc~{np.median([r[3] for r in ch]):.2f})")
    print("  speed = d(src)/d(reel): video setpts=(PTS-STARTPTS)/speed, audio atempo=speed")
else:
    print("\nCHUNKS: none with ncc >= 0.35 -- this source may only be under music,"
          " or isn't in the reel")
