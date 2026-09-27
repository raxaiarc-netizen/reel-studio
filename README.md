# Reel Studio 🎬

> **Automated AI studio to reconstruct Instagram Reels, TikToks, YouTube Shorts, and multi-slide carousels from original high-fidelity source footage.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20WSL-brightgreen.svg)]()
[![Claude Skills](https://img.shields.io/badge/Claude%20Code-Skills%20Included-purple.svg)]()

Reel Studio is an autonomous content reconstruction workstation powered by **Claude Code** and a lightweight local web control panel. Rather than re-encoding or re-filtering low-quality compressed uploads, Reel Studio hunts down the original online video and audio sources (interviews, movies, podcasts, concerts), extracts the exact matching segments, aligns the audio to the millisecond, performs intelligent face-tracking crops (9:16), generates broadcast-quality subtitles, applies a cinematic film grade, and outputs master videos.

---

## ✨ Key Features

- **High-Fidelity Reconstruction**: Never re-encodes compressed reels. Finds the original 4K/1080p source clips online and rebuilds the edit from scratch.
- **Real-Time Web Panel**: Clean, modern dark UI with an 11-step filmstrip progress tracker, live terminal inspector, and instant video preview.
- **Source Clip Origin Tracker**: The instant the original clip source (YouTube URL, title, uploader) is identified, it is recorded and displayed live on the UI card so you always know where footage originated.
- **Apify Integration for Posts**: Built-in UI configuration to set your Apify API key to fetch Instagram posts, carousels, and high-resolution slides without needing browser sessions.
- **Face-Tracking Smart Crop**: Uses OpenCV and the YuNet deep learning neural net (`yunet.onnx`) to compute optimal 9:16 crops centered on speakers without jumpy framing.
- **Audio Alignment & Stem Residual**: Cross-correlation audio alignment fits speed and offsets to ~1% precision, while Shazam stem separation identifies and rebuilds original music beds.
- **Resumable Background Sessions**: Every job runs inside an isolated, detached `tmux` session with pinned state. Pause, resume, restart, or reboot your machine without losing progress.
- **Zero Heavy Servers**: Pure Python standard library HTTP server + lightweight HTML/JS frontend. Fast, zero-bloat, and runs on any modern machine.

---

## 🚀 One-Prompt Setup with Claude

If you are using **Claude Code** or Claude with shell access, simply give Claude the repository link:

```
https://github.com/raxaiarc-netizen/reel-studio.git
```

and say:

> **"Set this up!"**

Claude will read `CLAUDE.md`, run `bash setup.sh`, install all dependencies, register the skills, and launch Reel Studio for you automatically.

---

## 💻 Manual Quickstart (Any Device)

### 1. Clone the Repository
```bash
git clone https://github.com/raxaiarc-netizen/reel-studio.git
cd reel-studio
```

### 2. Run the Universal Setup Script
```bash
bash setup.sh
```

The script automatically:
1. Verifies Python 3.9+ and `tmux`.
2. Downloads standalone `yt-dlp` and static `ffmpeg` with `libass` (customized for your OS and architecture).
3. Downloads the YuNet face-detection ONNX model.
4. Prepares the Python virtual environment with `opencv-python`, `numpy`, and `shazamio`.
5. Links `recreate-reel` and `recreate-post` to `~/.claude/skills/`.
6. Prepares local workspace storage at `~/ReelStudio/`.
7. (On macOS) Creates a double-clickable **Reel Studio.app** shortcut on your Desktop.

### 3. Launch Reel Studio
```bash
./start.sh
```
Open **http://127.0.0.1:7799** in your browser.

---

## 🎨 Using Reel Studio

### Studio Mode
1. **Paste Links**: Paste one or more Instagram Reel URLs, post links (`/p/`), TikToks, or YouTube Shorts into the input box.
2. **Add Custom Notes**: (Optional) Add creative notes (e.g. `no scrim`, `warmer grade`, `custom font`).
3. **Select AI Model**: Choose Claude Opus, Sonnet, Haiku, or default.
4. **Click "Recreate"**: The job enters the lane queue and runs automatically.
5. **Watch Real-Time Progress**:
   - The 11-cell filmstrip tracks the active step.
   - The **Source Clip Origin** box displays the found YouTube URL and clip title the moment it's discovered.
   - Click **Live view** to see the raw Claude terminal output in real time.
   - Click **Preview** once rendered to watch the final video directly in the browser.

### Configuring Apify API Key
1. Click the **Apify Key** button in the top right of the Reel Studio header.
2. Paste your Apify API Token (`apify_api_...`).
3. Click **Save Token**.
4. Reel Studio now uses Apify to scrape multi-slide Instagram carousels and posts with 100% reliability.

---

## 🛠️ The 11-Step Reconstruction Pipeline

| Step | Phase | Action |
|:---:|:---|:---|
| **0** | Preflight | Verifies environment, static ffmpeg (libass), standalone yt-dlp, and YuNet model. |
| **1** | Reel Ingest | Downloads target reel, extracts exact framerate, metadata, and mono 8kHz audio. |
| **2** | Visual Study | Generates contact sheets; maps cuts, speakers, and title/dialogue text. |
| **3** | Source Hunt | Finds highest resolution original source (up to 4K); logs **Source Origin** to UI. |
| **4** | Audio Alignment | Cross-correlates source audio against reel audio to determine precise offsets and speed drift. |
| **5** | Segment Mapping | Builds 30fps cut schedule with letterbox cropdetect and zoom matching. |
| **6** | Face Tracking | Runs YuNet face detector to calculate smooth, centered 9:16 crop coordinates. |
| **7** | Subtitle Engine | Compiles styled white Montserrat italic subtitles with positioning and blur. |
| **8** | Audio Rebuild | Slices high-fidelity audio from sources; identifies & mixes background music. |
| **9** | Parallel Render | Encodes intermediate video segments concurrently with ffmpeg. |
| **10** | Assembly & QA | Concatenates segments, applies 50% cinematic grade + 13% scrim, encodes final MP4. |

---

## 📁 Repository Structure

```
reel-studio/
├── CLAUDE.md                   # Automated AI agent setup guide
├── README.md                   # Documentation & overview
├── setup.sh                    # Cross-platform autonomous installer
├── start.sh                    # Launcher (background server + browser)
├── LICENSE                     # MIT License
├── panel/                      # Web application
│   ├── server.py               # Panel server & tmux session supervisor
│   ├── panel.html              # Responsive dark-theme UI
│   ├── research.py             # Curated account scanner
│   ├── settings.json           # Default settings
│   └── start.sh                # Panel background launcher
└── skills/                     # Claude AI Skills
    ├── recreate-reel/          # Video reel recreation engine
    │   ├── SKILL.md            # Skill prompt & step definitions
    │   ├── scripts/            # align.py, facetrack_crop.py, identify_music.py, etc.
    │   ├── models/             # yunet.onnx face detection model
    │   ├── references/         # recipe.md, gotchas.md
    │   └── assets/fonts/       # Montserrat typography
    └── recreate-post/          # Instagram carousel & post recreation
        ├── SKILL.md            # Post recreation prompt & gates
        ├── scripts/            # fetch_post.py, compose.py, export_dl.py, etc.
        └── assets/             # Fonts & logos
```

---

## 🔒 Privacy & Local Storage

- All jobs, downloaded source footage, and delivered masters are saved locally on your device in `~/ReelStudio/` (configurable via `REELSTUDIO_DIR`).
- Your API keys (Apify, etc.) and credentials remain local on your machine and are never uploaded or committed.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
