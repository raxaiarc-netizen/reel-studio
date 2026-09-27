# Gotchas — every trap this pipeline has actually hit

Read this before debugging anything; most "mysterious" failures below cost
real time the first time around.

## Environment / tools

- **Homebrew ffmpeg has no libass and no drawtext** — `ass=` fails with a
  confusing "No option name near ..." parse error, not "no such filter".
  Always use the bundled static build at `bin/ffmpeg` for anything involving
  subtitles. Homebrew `ffprobe` is fine for probing.
- **ffmpeg 9 (the static build) hard-errors on options placed after the output
  file** ("At least one output file must be specified"). Put `-loglevel` and
  friends before `-y`, never trailing.
- **The Bash tool runs zsh, which does NOT word-split unquoted `$vars`** — an
  `enc="-c:v libx264 ..."` var expands as ONE argument and ffmpeg dies with
  "At least one output file must be specified". Write multi-command renders as
  `build.sh` files and run them with `bash`.
- **Homebrew Python's `pyexpat` is broken on this machine** (libexpat symbol
  mismatch) — it kills Homebrew yt-dlp on some extractors mid-extraction. Use
  the bundled standalone `bin/yt-dlp`.
- **mediapipe crashes on this Mac** — its face-detector graph aborts with a
  Metal "Service is unavailable" check failure even with the CPU delegate.
  Use YuNet via opencv (`facetrack_crop.py`); it hit 86–100% detection.
- **`bc` prints `.5` without a leading zero** — ffmpeg rejects `-ss .5`.
  Use `awk '{printf "%.2f", ...}'` for fractional seconds in shell loops.

## Downloading

- **Instagram needs login cookies**: plain yt-dlp gets "login required", and
  Chrome's cookies didn't have an IG session — **Brave's did**. Use
  `--cookies-from-browser brave`, fall back to `chrome`, then ask the user to
  log into instagram.com in browser. TikTok/YouTube need no cookies.
- **shazamio pins `numpy<2` in its metadata but runs fine on numpy 2**, while
  opencv-python 5 requires `numpy>=2`. Install shazamio first, then force
  `pip install "numpy>=2"` and ignore the resolver warning (setup.sh does
  this). Verified working: identified reel 1's music bed (M83) with correct
  per-window track offsets.
- **Always check formats before downloading** (`yt-dlp -F`). A 1080p-capped
  download of a clip that exists in 4K is the single biggest avoidable
  quality loss: 9:16 crops magnify the source ~2.4x from 1080p letterboxed
  film vs ~1.2x from 4K. Grab `bv*[height<=2160]+ba`.
- Grab auto-captions with the source video in one call:
  `--write-auto-subs --sub-langs en --sub-format json3`.

## Analysis

- **Reels are often speed-shifted ~1%** (content-ID dodge). It shows as a
  slowly drifting offset in align.py. Compensate with `setpts/(speed)` on
  video and `atempo` on audio, or lips drift ~0.3s over 30s.
- **Reels layer audio over unrelated visuals** (announcement audio over a
  celebration shot, speech under a cutaway). Never assume audio offset ==
  video offset; verify visually with extracted frames at mapped times.
- **Audio residual analysis needs sample-exact lag search first** — IG's AAC
  re-encode shifts audio by tens of ms; subtracting at nominal offsets reads
  ~100% residual even when the audio is identical. audio_residual.py does the
  lag search; trust its numbers, not naive subtraction.
- **Very high align NCC (>0.9) means no music bed**; NCC 0.2–0.5 with clear
  offset structure means music was layered over the source audio.
- Auto-captions garble names ("Ke Huy Quan" -> "okay") and bleep profanity
  (`[ __ ]`) — use their timing, never their spelling.

## Framing / rendering

- **Detect letterboxing with `cropdetect`** before computing crops (2.39:1
  film in a 16:9 upload = active 1920x800 at y140; 4K = 3840x1600 at y280).
- **Watch for burned-in junk near crop edges**: source uploads carry their own
  captions (Vogue's yellow subs), promo banners ("Subscribe…"), lower-third
  name straps, and corner watermarks. Choose crop height/position to exclude
  them — the reel creators do the same, which is often WHY their zoom is tight.
- **Official award-show uploads may use split-screen/nominee-grid graphics**
  where the broadcast had a clean feed; the clean shot may simply not exist in
  any public source. That is a stop-and-ask situation.
- crop-filter `x` accepts runtime commands: `sendcmd=f=cmds.txt,crop=w:h:x0:y`
  with lines `1.2345 crop x 640;` per frame — timestamps are in the post-`-ss`
  input timeline (starts ~0), at SOURCE fps (before any fps= conversion).
- Big crop-x jumps are CORRECT at shot cuts (the spec's `cuts` reset the
  smoother); a big jump mid-shot means the detector flipped between two
  faces — tighten `cuts` or the fallback for that shot.
- Frame-exact assembly: compute every segment's `-frames:v` count on the
  30fps grid and make counts sum to `round(total*30)`; give `-t` some slack
  and let `-frames:v` do the cutting.

## Delivery

- SendUserFile hard limit: 30 MB. Uploads of 15–20 MB videos time out
  sometimes (30s limit) — retry once; the Desktop master is the deliverable.
- The final container should carry no source metadata: `-map_metadata -1`
  leaves only generic encoder tags. (Platform detection is content
  fingerprinting anyway — metadata is irrelevant to it; strip it for
  cleanliness, not as evasion, and be straight with the user about that.)
