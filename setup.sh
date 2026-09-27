#!/usr/bin/env bash
# ==============================================================================
# Reel Studio — Universal Cross-Platform Setup & Installer
# Works on macOS (Apple Silicon & Intel), Linux (Debian/Ubuntu/Fedora/Arch), & WSL.
# Idempotent: safe to run multiple times.
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$REPO_DIR/skills"
PANEL_DIR="$REPO_DIR/panel"
REEL_SKILL="$SKILLS_DIR/recreate-reel"
POST_SKILL="$SKILLS_DIR/recreate-post"
BIN_DIR="$REEL_SKILL/bin"
MODELS_DIR="$REEL_SKILL/models"
VENV_DIR="$REEL_SKILL/venv"
STORAGE_DIR="${REELSTUDIO_DIR:-$HOME/ReelStudio}"

echo "===================================================="
echo "🎬 Reel Studio — Automated Setup"
echo "===================================================="
echo "Platform: $(uname -s) ($(uname -m))"
echo "Directory: $REPO_DIR"
echo "Storage:   $STORAGE_DIR"
echo "===================================================="

OS="$(uname -s)"
ARCH="$(uname -m)"

mkdir -p "$BIN_DIR" "$MODELS_DIR" "$STORAGE_DIR/Jobs" "$STORAGE_DIR/Masters/Posts" "$STORAGE_DIR/Thumbs" "$STORAGE_DIR/Work" "$STORAGE_DIR/PostIdeas"

# ── 1. Python 3 detection ──────────────────────────────────────────────────
echo "Checking Python 3..."
PYTHON_BIN=""
for cmd in python3.11 python3.12 python3.10 python3.9 /usr/bin/python3 python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    VER="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    MAJOR="${VER%%.*}"
    MINOR="${VER##*.}"
    if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 9 ] && [ "$MINOR" -le 13 ]; then
      PYTHON_BIN="$(command -v "$cmd")"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "❌ Python 3.9+ is required but was not found."
  echo "Please install Python 3.9 or higher and rerun setup.sh."
  exit 1
fi
echo "✓ Using Python: $PYTHON_BIN ($VER)"

# ── 2. Tmux detection ──────────────────────────────────────────────────────
echo "Checking tmux..."
if ! command -v tmux >/dev/null 2>&1; then
  echo "Installing tmux..."
  if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    brew install tmux
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y tmux
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y tmux
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm tmux
  else
    echo "⚠️ tmux not found. Please install tmux for background session support."
  fi
else
  echo "✓ tmux is installed ($(tmux -V))"
fi

# ── 3. yt-dlp standalone ───────────────────────────────────────────────────
echo "Checking yt-dlp..."
if [ ! -x "$BIN_DIR/yt-dlp" ]; then
  echo "Downloading standalone yt-dlp..."
  if [ "$OS" = "Darwin" ]; then
    curl -sL -o "$BIN_DIR/yt-dlp" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
  else
    curl -sL -o "$BIN_DIR/yt-dlp" "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
  fi
  chmod +x "$BIN_DIR/yt-dlp"
fi
echo "✓ yt-dlp: $("$BIN_DIR/yt-dlp" --version)"

# ── 4. ffmpeg with libass ──────────────────────────────────────────────────
echo "Checking ffmpeg with libass (required for subtitle styling)..."
NEED_FFMPEG=0
if [ -x "$BIN_DIR/ffmpeg" ]; then
  if ! "$BIN_DIR/ffmpeg" -filters 2>&1 | grep -q "ass"; then
    NEED_FFMPEG=1
  fi
else
  NEED_FFMPEG=1
fi

if [ "$NEED_FFMPEG" -eq 1 ]; then
  echo "Downloading static ffmpeg build with libass..."
  if [ "$OS" = "Darwin" ]; then
    if [ "$ARCH" = "arm64" ]; then
      curl -sL -o /tmp/rs_ffmpeg.zip "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip"
    else
      curl -sL -o /tmp/rs_ffmpeg.zip "https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip"
    fi
    unzip -o -q /tmp/rs_ffmpeg.zip -d "$BIN_DIR" && rm -f /tmp/rs_ffmpeg.zip
    chmod +x "$BIN_DIR/ffmpeg"
  else
    # Linux static build
    TMP_FF_DIR="/tmp/rs_ffmpeg_static"
    mkdir -p "$TMP_FF_DIR"
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
      curl -sL "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz" | tar -xJ -C "$TMP_FF_DIR" --strip-components=1
    else
      curl -sL "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" | tar -xJ -C "$TMP_FF_DIR" --strip-components=1
    fi
    cp "$TMP_FF_DIR/ffmpeg" "$BIN_DIR/ffmpeg"
    cp "$TMP_FF_DIR/ffprobe" "$BIN_DIR/ffprobe" 2>/dev/null || true
    chmod +x "$BIN_DIR/ffmpeg"
    rm -rf "$TMP_FF_DIR"
  fi
fi

if [ -x "$BIN_DIR/ffmpeg" ]; then
  echo "✓ ffmpeg: $("$BIN_DIR/ffmpeg" -version | head -n 1)"
else
  echo "⚠️ Warning: Bundled ffmpeg not found, using system ffmpeg."
fi

# ── 5. YuNet face detection model ──────────────────────────────────────────
echo "Checking YuNet face detection model..."
if [ ! -f "$MODELS_DIR/yunet.onnx" ]; then
  echo "Downloading YuNet ONNX model..."
  curl -sL -o "$MODELS_DIR/yunet.onnx" \
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi
echo "✓ YuNet model present ($(ls -lh "$MODELS_DIR/yunet.onnx" | awk '{print $5}'))"

# ── 6. Python Virtual Environment ──────────────────────────────────────────
echo "Setting up Python virtual environment..."
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Creating venv in $VENV_DIR..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" -q install --upgrade pip setuptools wheel
fi

echo "Verifying Python dependencies (opencv-python, numpy, shazamio, pillow, requests)..."
"$VENV_DIR/bin/python" -c "import numpy, cv2, shazamio, PIL, requests" 2>/dev/null || {
  echo "Installing Python packages..."
  "$VENV_DIR/bin/pip" -q install shazamio opencv-python pillow requests
  "$VENV_DIR/bin/pip" -q install "numpy>=2" 2>/dev/null || true
}
echo "✓ Python venv ready: $("$VENV_DIR/bin/python" --version)"

# ── 7. Link / Register Claude Skills ───────────────────────────────────────
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
echo "Registering skills in $CLAUDE_SKILLS_DIR..."
mkdir -p "$CLAUDE_SKILLS_DIR"

for skill in recreate-reel recreate-post; do
  TARGET="$CLAUDE_SKILLS_DIR/$skill"
  SOURCE="$SKILLS_DIR/$skill"
  if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
    echo "Backing up existing skill at $TARGET to ${TARGET}.bak..."
    mv "$TARGET" "${TARGET}.bak"
  fi
  rm -f "$TARGET"
  ln -s "$SOURCE" "$TARGET"
  echo "✓ Linked $skill -> $SOURCE"
done

# ── 8. Create macOS Desktop App (if on macOS) ──────────────────────────────
if [ "$OS" = "Darwin" ]; then
  DESKTOP_APP="$HOME/Desktop/Reel Studio.app"
  echo "Creating Desktop launcher at $DESKTOP_APP..."
  mkdir -p "$DESKTOP_APP/Contents/MacOS" "$DESKTOP_APP/Contents/Resources/Scripts"
  
  cat <<'EOF' > "$DESKTOP_APP/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleExecutable</key>
	<string>applet</string>
	<key>CFBundleIconFile</key>
	<string>applet</string>
	<key>CFBundleIdentifier</key>
	<string>com.reelstudio.app</string>
	<key>CFBundleName</key>
	<string>Reel Studio</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
</dict>
</plist>
EOF

  cat <<EOF > "$DESKTOP_APP/Contents/MacOS/applet"
#!/bin/bash
exec "$REPO_DIR/start.sh" >/dev/null 2>&1 &
EOF
  chmod +x "$DESKTOP_APP/Contents/MacOS/applet"

  # Copy icon if available
  if [ -f "$REPO_DIR/assets/applet.icns" ]; then
    cp "$REPO_DIR/assets/applet.icns" "$DESKTOP_APP/Contents/Resources/applet.icns"
  elif [ -f "$HOME/Desktop/Reel Studio.app/Contents/Resources/applet.icns" ]; then
    cp "$HOME/Desktop/Reel Studio.app/Contents/Resources/applet.icns" "$DESKTOP_APP/Contents/Resources/applet.icns" 2>/dev/null || true
  fi
  echo "✓ Desktop launcher created"
fi

# ── 9. Make scripts executable ─────────────────────────────────────────────
chmod +x "$REPO_DIR/start.sh" 2>/dev/null || true
chmod +x "$PANEL_DIR/start.sh" 2>/dev/null || true
chmod +x "$PANEL_DIR/server.py" 2>/dev/null || true
chmod +x "$REEL_SKILL/scripts/"*.sh 2>/dev/null || true
chmod +x "$REEL_SKILL/scripts/"*.py 2>/dev/null || true
chmod +x "$POST_SKILL/scripts/"*.py 2>/dev/null || true

echo ""
echo "===================================================="
echo "✅ Reel Studio setup complete!"
echo "===================================================="
echo ""
echo "To start the Reel Studio web panel:"
echo "  ./start.sh"
echo ""
echo "Or open: http://127.0.0.1:7799"
echo "Skills installed for Claude Code: recreate-reel, recreate-post"
echo "===================================================="
