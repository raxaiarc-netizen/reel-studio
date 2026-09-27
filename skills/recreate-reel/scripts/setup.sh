#!/bin/bash
# Idempotent preflight for the recreate-reel skill. Safe to run every time.
# Verifies bundled tools, re-downloads any that are missing, and builds the
# Python venv (numpy + opencv) used by the analysis/tracking scripts.
set -e
K="$(cd "$(dirname "$0")/.." && pwd)"

# yt-dlp standalone (Homebrew yt-dlp can break via Homebrew Python's pyexpat)
if [ ! -x "$K/bin/yt-dlp" ]; then
  echo "downloading yt-dlp standalone..."
  curl -sL -o "$K/bin/yt-dlp" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
  chmod +x "$K/bin/yt-dlp"
fi

# Static ffmpeg WITH libass (Homebrew ffmpeg is built without subtitle/text filters)
if [ ! -x "$K/bin/ffmpeg" ]; then
  echo "downloading static ffmpeg (libass build)..."
  curl -sL -o /tmp/rr_ffmpeg.zip "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip"
  unzip -o -q /tmp/rr_ffmpeg.zip -d "$K/bin" && rm /tmp/rr_ffmpeg.zip
  chmod +x "$K/bin/ffmpeg"
fi
"$K/bin/ffmpeg" -version >/dev/null 2>&1 || { echo "ERROR: bundled ffmpeg not runnable"; exit 1; }

# YuNet face detection model
if [ ! -f "$K/models/yunet.onnx" ]; then
  echo "downloading YuNet model..."
  curl -sL -o "$K/models/yunet.onnx" \
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi

# venv: /usr/bin/python3 (system CLT python), numpy + opencv + shazamio.
# Do NOT use mediapipe — its face detector crashes with a Metal error on this Mac.
# Order matters: shazamio pins numpy<2 in metadata (but runs fine on numpy 2),
# while opencv-python needs numpy>=2 — install shazamio first, then force numpy>=2.
if [ ! -x "$K/venv/bin/python" ]; then
  echo "creating venv..."
  /usr/bin/python3 -m venv "$K/venv"
  "$K/venv/bin/pip" -q install --upgrade pip
fi
"$K/venv/bin/python" -c "import numpy, cv2, shazamio" 2>/dev/null || {
  echo "installing numpy + opencv + shazamio..."
  "$K/venv/bin/pip" -q install shazamio opencv-python
  "$K/venv/bin/pip" -q install "numpy>=2" 2>/dev/null
}

echo "SETUP-OK"
echo "ffmpeg: $K/bin/ffmpeg"
echo "yt-dlp: $K/bin/yt-dlp"
echo "python: $K/venv/bin/python"
