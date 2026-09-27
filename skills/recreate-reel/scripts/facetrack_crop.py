#!/usr/bin/env python3
"""YuNet face tracking -> per-frame ffmpeg crop-x sendcmd files.

For each segment in a JSON spec: detect the largest face per sampled source
frame, interpolate gaps, smooth with a dead-zone + damped follow (reset at
known shot cuts so the crop JUMPS at cuts instead of gliding across them),
clamp, and emit cmds_<name>.txt for ffmpeg's `sendcmd=f=...,crop=...` filters.

Usage:
  facetrack_crop.py spec.json           # track -> cmds files
  facetrack_crop.py spec.json --probe   # no cmds; report face size/position
                                        # stats per segment to pick crop_w
                                        # (zoom match: crop_w = face_w_src /
                                        #  face_fraction_measured_on_the_reel)

Spec (times in SOURCE seconds; crop_w/active_* in source pixels):
{
  "out_dir": "/abs/path",               # where cmds_*.txt land
  "stride": 1,                          # detect every Nth frame (2 = ~2x faster,
                                        #   still smooth; skipped frames use grab())
  "segments": [
    {"name": "m2",
     "src": "/abs/path/scene.mp4",
     "start": 7.69, "dur": 23.4,        # source in-point and duration to scan
     "crop_w": 900,                     # crop width (the 9:16 window width)
     "active_x": 0, "active_w": 3840,   # letterboxed active picture (x range)
     "cuts": [1.80, 3.60],              # shot cuts, seconds relative to start
     "fallback": [925, 375, 960],       # per-shot crop-x if detection is too low
     "prefer_x": [null, 1200, null],    # optional: per-shot speaker hint — pick the
                                        #   face NEAREST this x instead of the largest
                                        #   (two-shot scenes; a number applies to all shots)
     "stride": 2}                       # optional per-segment override
  ]
}
Run with the skill's venv python. Do not use mediapipe here — its face detector
graph crashes with a Metal 'Service is unavailable' abort on this machine.
"""
import json, os, sys
import cv2
import numpy as np

K = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = json.load(open(sys.argv[1]))
PROBE = '--probe' in sys.argv
out_dir = spec.get('out_dir', os.path.dirname(os.path.abspath(sys.argv[1])))

yunet = cv2.FaceDetectorYN_create(os.path.join(K, 'models', 'yunet.onnx'), "", (960, 540), 0.6, 0.3, 500)

def detect_faces(frame_bgr):
    """All faces as [(center_x, width), ...] in full-frame coords.
    Falls back to a center crop so small faces (wide shots) still register."""
    h, w = frame_bgr.shape[:2]
    dw, dh = 960, int(960 * h / w)
    small = cv2.resize(frame_bgr, (dw, dh))
    yunet.setInputSize((dw, dh))
    faces = yunet.detect(small)[1]
    if faces is not None and len(faces):
        sc = w / dw
        return [((f[0] + f[2] / 2) * sc, f[2] * sc) for f in faces]
    cx0, cy0 = int(w * 0.3), int(h * 0.1)
    center = np.ascontiguousarray(frame_bgr[cy0:int(h * 0.9), cx0:int(w * 0.7)])
    ch, cw = center.shape[:2]
    yunet.setInputSize((cw, ch))
    faces = yunet.detect(center)[1]
    if faces is not None and len(faces):
        return [(cx0 + f[0] + f[2] / 2, f[2]) for f in faces]
    return []

def pick_face(faces, hint_x):
    """The speaker: nearest to hint_x when a hint is given (two-shot scenes
    where the largest face is the wrong person), else the largest face."""
    if not faces:
        return None
    if hint_x is not None:
        return min(faces, key=lambda f: abs(f[0] - hint_x))
    return max(faces, key=lambda f: f[1])

def smooth_shot(targets, sampled, fallback_x, xmin, xmax):
    n = len(targets)
    idx = [i for i, v in enumerate(targets) if v is not None]
    if len(idx) < max(3, sampled * 0.25):
        return [int(fallback_x)] * n
    filled = np.interp(np.arange(n), idx, [targets[i] for i in idx])
    k = 7
    pad = np.pad(filled, (k // 2, k // 2), mode='edge')
    filled = np.convolve(pad, np.ones(k) / k, mode='valid')[:n]
    out, x = [], float(np.median(filled[:min(8, n)]))
    DZ, ALPHA = 60.0, 0.12  # px dead-zone; damped follow rate per frame
    for tx in filled:
        err = tx - x
        if abs(err) > DZ:
            x += (err - np.sign(err) * DZ) * ALPHA
        out.append(int(round(min(max(x, xmin), xmax))))
    return out

for seg in spec['segments']:
    stride = max(1, int(seg.get('stride', spec.get('stride', 1))))
    cap = cv2.VideoCapture(seg['src'])
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ax = seg.get('active_x', 0)
    aw = seg.get('active_w', frame_w)
    crop_w = seg.get('crop_w', aw)
    xmin, xmax = ax, ax + aw - crop_w
    cap.set(cv2.CAP_PROP_POS_MSEC, seg['start'] * 1000.0)
    cuts = seg.get('cuts', [])
    prefer = seg.get('prefer_x')          # number, or per-shot list aligned with cuts
    if isinstance(prefer, (int, float)) or prefer is None:
        prefer = [prefer] * (len(cuts) + 1)
    targets, times, widths = [], [], []
    n_frames = int(seg['dur'] * fps) + 1
    si = 0
    for i in range(n_frames):
        if not cap.grab():
            break
        t = i / fps
        times.append(t)
        while si < len(cuts) and t >= cuts[si]:
            si += 1
        if i % stride == 0:
            ok, frame = cap.retrieve()
            hint = prefer[si] if si < len(prefer) else prefer[-1]
            det = pick_face(detect_faces(frame), hint) if ok else None
            if det is None:
                targets.append(None)
            else:
                cx, fw = det
                targets.append(min(max(cx - crop_w / 2, xmin), xmax))
                widths.append(fw)
        else:
            targets.append(None)
    cap.release()
    sampled = (len(times) + stride - 1) // stride
    det_rate = len(widths) / max(1, sampled)

    if PROBE:
        if widths:
            med_w = float(np.median(widths))
            centers = [t + crop_w / 2 for t in targets if t is not None]
            print(f"{seg['name']}: face_w median {med_w:.0f}px (p10 {np.percentile(widths,10):.0f},"
                  f" p90 {np.percentile(widths,90):.0f}), center_x median {np.median(centers):.0f},"
                  f" detection {det_rate*100:.0f}% of {sampled} sampled")
        else:
            print(f"{seg['name']}: no faces detected in {sampled} sampled frames")
        continue

    bounds = [0] + [next((i for i, t in enumerate(times) if t >= c), len(times)) for c in cuts] + [len(times)]
    fb = seg.get('fallback', [(xmin + xmax) // 2])
    xs = []
    for si in range(len(bounds) - 1):
        shot = targets[bounds[si]:bounds[si + 1]]
        shot_sampled = (len(shot) + stride - 1) // stride
        fx = fb[si] if si < len(fb) else fb[-1]
        xs.extend(smooth_shot(shot, shot_sampled, fx, xmin, xmax))

    path = os.path.join(out_dir, f"cmds_{seg['name']}.txt")
    with open(path, 'w') as f:
        for t, x in zip(times, xs):
            f.write(f"{t:.4f} crop x {x};\n")
    print(f"{seg['name']}: {len(xs)} frames (stride {stride}), detection {det_rate*100:.0f}%,"
          f" x {min(xs)}-{max(xs)} -> {path}")
print("PROBE-OK" if PROBE else "TRACK-OK")
