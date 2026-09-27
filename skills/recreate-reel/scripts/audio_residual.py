#!/usr/bin/env python3
"""Does the reel have an added music bed? And what gain mirrors its levels?

For each segment: find the sample-exact lag between reel audio and source audio
(cross-correlation — REQUIRED because IG's AAC re-encode shifts audio by tens of
ms; naive subtraction at nominal offsets reads ~100% residual and lies to you),
then measure how much reel energy the source does NOT explain.

Reading the output:
  med_res < 0.15  -> that segment is pure source audio (just codec noise)
  med_res 0.3+    -> something added: music bed, SFX, or voiceover
  rms_gain        -> multiply source audio by this to mirror the reel's level
  hot windows     -> reel times where unexplained audio concentrates

Usage: audio_residual.py spec.json
Spec: {"reel": "reel_8k.wav",
       "segments": [{"name": "m2", "reel_t0": 2.3, "reel_t1": 25.43,
                     "src": "source_8k.wav", "src_t0": 7.69}]}
All wavs mono 16-bit 8kHz.
"""
import json, sys, wave
import numpy as np

def load(path):
    w = wave.open(path, 'rb')
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
    sr = w.getframerate()
    w.close()
    return x, sr

spec = json.load(open(sys.argv[1]))
reel, sr = load(spec['reel'])
cache = {}
W = int(0.5 * sr)
MAX_LAG = int(0.15 * sr)

print(f"{'seg':>4} {'lag_ms':>7} {'ncc':>5} {'rms_gain':>8} {'med_res':>7} {'p90_res':>7}  hot(>40%)")
for g in spec['segments']:
    if g['src'] not in cache:
        cache[g['src']] = load(g['src'])[0]
    src = cache[g['src']]
    r = reel[int(g['reel_t0'] * sr):int(g['reel_t1'] * sr)]
    s0 = int(g['src_t0'] * sr)
    s = src[max(0, s0 - MAX_LAG): s0 + len(r) + MAX_LAG]
    n = len(r)
    corr = np.correlate(s, r, mode='valid')
    cs = np.concatenate(([0.0], np.cumsum(s * s)))
    norm = cs[n:] - cs[:len(s) - n + 1]
    ncc = corr / np.sqrt(norm * np.dot(r, r) + 1e-9)
    k = int(np.argmax(ncc))
    lag_ms = (k - min(MAX_LAG, s0)) / sr * 1000.0
    sa = s[k:k + n]
    ratios, hot = [], []
    for i in range(0, n - W, W):
        rw, sw = r[i:i + W], sa[i:i + W]
        denom = float(np.dot(sw, sw))
        a = float(np.dot(rw, sw)) / denom if denom > 1e-6 else 0.0
        resid = rw - a * sw
        er = float(np.dot(rw, rw))
        ratio = float(np.dot(resid, resid)) / er if er > 1e-6 else 0.0
        ratios.append(ratio)
        if ratio > 0.4:
            hot.append(round(g['reel_t0'] + i / sr, 1))
    gain = float(np.sqrt(np.mean(r * r) / max(np.mean(sa * sa), 1e-9)))
    print(f"{g['name']:>4} {lag_ms:7.1f} {float(ncc[k]):5.2f} {gain:8.3f} "
          f"{np.median(ratios):7.2f} {np.percentile(ratios, 90):7.2f}  "
          f"{hot[:12]}{'...' if len(hot) > 12 else ''}")
