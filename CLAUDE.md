# Reel Studio — Claude AI Setup & Assistant Guide

This repository contains **Reel Studio** and its specialized AI skills:
- **`recreate-reel`**: Rebuilds short-form videos (Instagram Reels, TikToks, YouTube Shorts) from their original source clips at maximum quality with face-tracked 9:16 crops, white Montserrat italic subtitles, cinematic grade, and audio rebuilt for lip-sync.
- **`recreate-post`**: Recreates Instagram posts and multi-slide carousels (`/p/` links) slide-by-slide via Apify and image generation, stripped of metadata and exported with Canva.
- **`panel`**: A real-time Web UI panel running background resumable Claude sessions inside detached tmux panes.

---

## When the user says "Set this up", "Install", or points Claude to this repository:

### 1. Run the Setup Script
Execute:
```bash
bash setup.sh
```
This script will autonomously:
1. Detect Python 3.9+ and tmux.
2. Download standalone `yt-dlp` and static `ffmpeg` with `libass` (customized per OS/architecture: macOS Apple Silicon/Intel or Linux x86_64/arm64).
3. Download the YuNet face detection ONNX model.
4. Create the Python virtual environment and install dependencies (`opencv-python`, `numpy>=2`, `shazamio`, `pillow`, `requests`).
5. Register the skills into `~/.claude/skills/` (`recreate-reel` and `recreate-post`).
6. Create the storage folders at `~/ReelStudio/` (`Jobs`, `Masters`, `Thumbs`, `Work`, `PostIdeas`).
7. On macOS, automatically create the `Reel Studio.app` on the Desktop.

### 2. Start Reel Studio
Once `setup.sh` completes, launch Reel Studio:
```bash
./start.sh
```

### 3. Report to the User
Confirm the following to the user:
- **Status**: Reel Studio is installed and running at **http://127.0.0.1:7799**.
- **Skills Activated**: `recreate-reel` and `recreate-post` are linked in `~/.claude/skills/`.
- **Apify API Key**: Remind them they can click the **Apify Key** button in the header of the Reel Studio panel to configure their Apify token (needed for fetching Instagram posts and carousels).
- **Source Clip Origin**: When recreating reels, the panel will automatically write down and display the original source clip (YouTube URL, title, creator) in a dedicated real-time box on the UI card so they can watch progress live.

---

## Repository Layout
```
reel-studio/
├── CLAUDE.md               # Claude agent automated instructions
├── README.md               # Overview, quickstart, and feature docs
├── setup.sh                # Universal cross-platform installer
├── start.sh                # Launcher (background server + browser)
├── panel/                  # Web application panel
│   ├── server.py           # HTTP server + tmux session manager
│   ├── panel.html          # Web UI with real-time filmstrip, Apify modal, & origin box
│   ├── research.py         # Account research & candidate discovery
│   ├── settings.json       # Configurable server & lane settings
│   └── start.sh            # Panel start script
└── skills/                 # AI Skills
    ├── recreate-reel/      # Short-form video recreation skill
    │   ├── SKILL.md
    │   ├── scripts/        # align.py, facetrack_crop.py, identify_music.py, etc.
    │   ├── models/         # yunet.onnx
    │   ├── references/     # recipe.md, gotchas.md
    │   └── assets/fonts/   # Montserrat fonts
    └── recreate-post/      # Multi-slide post/carousel recreation skill
        ├── SKILL.md
        ├── scripts/        # fetch_post.py, compose.py, export_dl.py, etc.
        └── assets/         # Fonts & overlays
```

## Running Jobs Manually
- To recreate a reel via Claude CLI directly:
  `claude "Recreate this reel end-to-end using the recreate-reel skill: <URL>"`
- To recreate an Instagram post/carousel:
  `claude "Recreate this Instagram post end-to-end using the recreate-post skill: <URL>"`
