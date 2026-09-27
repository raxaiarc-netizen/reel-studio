---
name: recreate-reel
description: Recreate a short-form video (Instagram reel/post, TikTok, YouTube Short) from its ORIGINAL source clips — higher quality than the reel itself, with face-tracked 9:16 crops, white Montserrat/Gotham-style italic subtitles, polished cinematic finishing look (13% scrim + 50% cinematic grade), and audio rebuilt from the sources for perfect lip-sync. Use this whenever someone pastes a reel/short-video link and wants it recreated, remade, rebuilt, "same but better", "make this reel", or asks to recreate a video from its original clips — even if they just post a link with the word "recreate".
---

# Recreate Reel

Rebuild a reel from the original clips it was cut from — never by re-filtering
the reel itself. The recreation should match the reel's cuts, framing, timing
and loudness, at higher fidelity than the reel (original sources beat
Instagram's re-compress), finished with the standing look in
`references/recipe.md`.

**Three hard gates — STOP and ask the user, never silently improvise:**
1. A segment's source video cannot be found online.
2. A music bed exists but can't be identified.
3. A segment's audio exists in no source (creator voiceover, unfound clip).

Everything else runs full-auto to a finished draft; iterate afterward.

Read `references/gotchas.md` before debugging anything — every known trap
(broken Homebrew ffmpeg/Python, zsh word-splitting, IG cookies, speed-shifted
reels, letterboxing, burned-in banners) is documented there with the fix.

## Speed — one session, no subagents

Run the whole pipeline in THIS session. Do **not** spawn subagents (Agent
tool) for any lane — source hunting, subtitles, audio, renders. It was tried
and it is slower: agent startup, re-establishing the reel's context in each
one, and report round-trips cost more than the lanes save, and the main
session ends up re-verifying the work anyway.

Wall-clock actually comes from these, in order:

1. **Background the downloads.** Start every source download with
   `run_in_background` the moment you know its URL, then keep studying the
   reel and planning segments while they land. Downloads are the longest
   serial wait in the pipeline and nothing else needs to block on them.
2. **Render segments concurrently** (Step 9) — independent ffmpeg jobs, 3–4
   at a time with `&` then `wait`; roughly halves render time.
3. **Batch the cheap scripts.** align.py, words.py and audio_residual.py are
   sub-second — run them back-to-back in one bash call, never one round-trip
   each.
4. **Contact sheets, not per-frame Reads** (Step 2) — the single biggest
   token and latency cost in the pipeline.

The dependency chain is genuinely sequential anyway: reel download → study →
sources (per source: find, download, align, verify) → segment plan → crops +
subs + audio → assembly → QA. Walk it in order, keeping the long jobs in the
background.

## Step 0 — Preflight

```bash
bash ~/.claude/skills/recreate-reel/scripts/setup.sh
```

Idempotent; prints SETUP-OK plus tool paths. Always use the bundled
`bin/ffmpeg` (has libass; Homebrew's doesn't) and `bin/yt-dlp` (standalone;
Homebrew's Python is broken). `venv/bin/python` runs every script.

**Storage rule.** Work in `<BASE>/Work/<reel-name>/`, never in /tmp or the
scratchpad. `<BASE>` is `~/ReelStudio` (or `$REELSTUDIO_DIR`).
Define `K=~/.claude/skills/recreate-reel` (or repo `skills/recreate-reel`) for tools.

## Step 1 — Download the reel

```bash
"$K/bin/yt-dlp" --cookies-from-browser brave --write-info-json \
  -o "reel/video.%(ext)s" "<link>"        # brave cookies: needed for IG only
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate \
  -of csv=p=0 reel/video.mp4              # note exact duration too
"$K/bin/ffmpeg" -y -i reel/video.mp4 -vn -c:a copy reel_audio.m4a \
  -vn -ac 1 -ar 8000 reel_8k.wav
```

If IG says login required, retry with `--cookies-from-browser chrome`, or open instagram.com in browser.

Read the caption from `video.info.json` — reel captions usually name the film,
event, and people, which is most of the source-hunting work done for free.

## Step 2 — Study the reel

- Default to contact sheets, not per-frame Reads: `fps=4,scale=135:240,tile=8x7`
  shows ~14s of reel per image (one Read each). Read individual frames only to
  fine-check a specific moment — per-frame Reads are the pipeline's single
  biggest token/latency cost.
- Scene cuts: `-vf "select='gt(scene,0.22)',showinfo"` → cut timestamps.

Produce a segment map: what's on screen when, every on-screen text (title +
dialogue subs, their wording and censoring style), and where cuts fall.

## Step 3 — Find the sources (gate #1)

Identify each clip (caption + frames), then work the sources one at a time —
per source: hunt it, `-F` check, download (in the background), extract the 8k
wav, align (Step 4), cropdetect the letterbox, verify the mapping visually:
- `"$K/bin/yt-dlp" --flat-playlist --print "%(id)s | %(title)s | %(uploader)s | %(duration)s" "ytsearchN:<query>"`
- WebSearch for archival/interview clips; check official channels first.
- **Always `yt-dlp -F` before downloading** — take the highest resolution
  that exists (4K halves the blur of a 9:16 crop vs 1080p). Download with
  `-f "bv*[height<=2160]+ba[ext=m4a]/b"` plus
  `--write-auto-subs --sub-langs en --sub-format json3`.
- **Start every source download in the background immediately**
  (`run_in_background`) and keep studying the reel / planning while they land —
  downloads were the longest serial waits in the original run.
- Extract each source's mono 8k wav like the reel's.

**CRITICAL: Write down the source origin immediately:**
The moment you find/identify each source clip origin, IMMEDIATELY write or append it to `./source_origin.txt` in your cwd:
```
Title: <Source Video Title>
URL: <https://www.youtube.com/watch?v=...>
Origin: <Channel or Creator Name>
```
The Reel Studio UI panel automatically detects this file and renders it live in the **Source Clip Origin** box on the job card so the user sees work progress!

If any segment's source can't be found after a genuine hunt (try alternate
uploads, archives, vertical/official variants): **stop, show what was found,
and ask the user** — options usually include substituting similar footage or reusing
the reel's own frames, but that's the user's call, not a default.

## Step 4 — Align audio (the ground truth for every cut)

```bash
"$K/venv/bin/python" "$K/scripts/align.py" reel_8k.wav source_8k.wav
```

The script ends with a **CHUNKS summary** — contiguous reel spans lifted from
that source, each with fitted `src_in` and `speed` (least-squares over the
offset drift; ~1% speed-shifts are common content-ID dodges). Use those
numbers directly for the segment table; the per-row table above it is for
diagnosing weak zones (music-dominant audio or content not from this source).
Repeat per source. Then **verify visually**: extract source frames at mapped
times and compare against reel frames — reels sometimes lay audio over
unrelated visuals, so audio offsets alone don't prove the video mapping.

## Step 5 — Plan the video segments

Build a frame-exact table on the 30fps grid: for each segment —
reel in/out, source file, source in-point, speed, crop geometry, `-frames:v`
count (counts must sum to `round(total_duration*30)`).

- Letterbox first: `cropdetect` per source → active area (e.g. 2.39:1 film in
  16:9 = 1920x800@y140; same upload in 4K = 3840x1600@y280).
- Crop width = the 9:16 window in source pixels. Match the reel's zoom by
  arithmetic, not eyeballing: run `facetrack_crop.py spec.json --probe` to get
  each segment's median face width in source pixels, measure the face's
  fraction of frame width in a reel frame, then
  `crop_w = face_w_src / face_fraction_reel`. Keep burned-in
  captions/banners/watermarks OUT of frame (check frame edges; the reel's own
  tight zoom often exists precisely to hide these).
- Split segments at broadcast cuts when crop position must change (a crop
  change at a real cut is invisible; mid-shot it's a jerk).

## Step 6 — Face-tracked crops

Write a spec (source-relative times, cuts relative to each segment start,
per-shot fallback x) and run:

```bash
"$K/venv/bin/python" "$K/scripts/facetrack_crop.py" spec.json
```

It emits per-frame `cmds_<name>.txt` for `sendcmd=f=...,crop=...`. Sanity:
detection ≥80% on face-visible footage; large x-jumps only at declared cuts.
Set `"stride": 2` in the spec for near-2x tracking speed (skipped frames are
grab()-only and interpolated) — safe default; stride 1 only for fast motion.
In two-person shots where the LARGEST face isn't the speaker (OTS shots,
side-by-side interviews), set `"prefer_x"` (per-shot list or one number) to
the speaker's approximate source-x — the tracker then follows the face
nearest that hint. Never mediapipe (crashes on this Mac — see gotchas).

Steps 6–8 are independent of each other. Face tracking is the slow one —
launch it in the background (`run_in_background`) and write the subtitles
(Step 7) and rebuild the audio (Step 8) while it runs.

## Step 7 — Subtitles

White Montserrat Italic only, styles and rules verbatim from
`references/recipe.md`. Timing: map caption word times
(`"$K/venv/bin/python" "$K/scripts/words.py" src.json3 t0 t1`) into reel time
via each chunk's offset/speed. Text: the reel's own wording and censoring
(fix only outright typos). Title: static text, positioned so it NEVER covers
a face — check frames per section and split into repositioned events at hard
cuts when needed. Sync subs to the audio even if the source reel's subs lag.

## Step 8 — Audio rebuild (gates #2, #3)

```bash
"$K/venv/bin/python" "$K/scripts/audio_residual.py" audio_spec.json
```

- Low residual everywhere (<0.15) → no music bed: rebuild the track purely
  from source audio — per-segment `atrim` at the video cut points (lip-sync by
  construction), `volume=` from each rms_gain, 8ms fades at joins, concat,
  `alimiter=limit=0.97:level=false`, `aac -b:a 256k`. Verify integrated
  loudness lands within ~0.5 LU of the reel (`ebur128`).
- Music bed present (structured residual) → identify it:
  `"$K/venv/bin/python" "$K/scripts/identify_music.py" reel_audio.m4a [start] [dur]`
  (probes 3 windows; a MATCH also reports the track offset ≈ where in the
  track the reel starts). Fetch the track via yt-dlp, refine the offset by
  cross-correlation, gain-match in low-speech windows, mix under the speech.
  **All windows UNIDENTIFIED → stop and ask (gate #2).**
- Segment audio with no source (voiceover, unfound clip) →
  **stop and ask (gate #3).**

## Step 9 — Render

Write a `build.sh` and run it with `bash` (zsh var-splitting breaks inline
ffmpeg — gotchas). **Render the segments concurrently** — they are independent;
launch each as a background job (`... seg/X.mp4 & `) and `wait` before
verifying frame counts, then assemble. 3–4 parallel ffmpegs are fine on this
machine and cut render wall-time roughly in half. Pattern per segment, then
assembly:

```bash
"$K/bin/ffmpeg" -loglevel error -y -ss <src_in> -i SRC -t <dur+slack> \
  -vf "sendcmd=f=cmds_X.txt,crop=<w>:<h>:<x0>:<y>,scale=1080:1920:flags=lanczos,setpts=(PTS-STARTPTS)/<speed>,fps=30" \
  -frames:v <N> -c:v libx264 -preset medium -crf 12 -pix_fmt yuv420p -an seg/X.mp4

"$K/bin/ffmpeg" -loglevel warning -y -f concat -safe 0 -i list.txt -i mix.m4a \
  -map 0:v -map 1:a -map_metadata -1 \
  -vf "<grade>,<scrim>,ass=subs.ass:fontsdir=$K/assets/fonts" \
  -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -c:a copy \
  -movflags +faststart -t <duration> final.mp4
```

Grade/scrim strings, CAS-sharpening rule for 1080p-capped sources, and every
encode value: `references/recipe.md`.

## Step 10 — QA before delivering

Extract ~8 frames across the result and actually look: faces centered, no
banner/caption/watermark leakage, title off faces, sub timing sane, grade not
crushing. For a full audit, build side-by-side sheets (recreation | reel every
0.5s, hstack + tile). Fix issues and re-render before the user sees a draft —
sendcmd/crop/subtitle bugs are all cheap to fix pre-delivery.

## Step 11 — Deliver

- Master → `~/Desktop/<Subject>_reel_recreation.mp4`.
- Chat preview → crf 24 re-encode under 30 MB, SendUserFile (retry once on
  timeout; the Desktop copy is the deliverable).
- Report: sources used (with links), resolutions, any substitutions or open
  questions, loudness match, and which knobs are one-command tweaks.

## Iterating

Layers are independent — don't rebuild the world for a dial change:
- Grade/scrim/title position/sub text → re-run only the final assembly.
- Crop/zoom of one segment → re-render that segment, then assembly.
- Audio levels → rebuild mix + assembly (`-c:a copy` elsewhere).
Keep the workdir until the reel is signed off.
