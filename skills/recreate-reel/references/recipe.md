# The finishing recipe (exact values)

These values are the standing default for every recreation.
Apply all of them unless a change is requested in the run.

## Subtitle / title styling (ASS)

White Montserrat Italic only — this stands in for Gotham Italic (commercial,
not installed; Montserrat is the standard free lookalike). Fonts are bundled in
`assets/fonts/`; pass `fontsdir=<skill>/assets/fonts` to the ass filter.

```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Montserrat SemiBold,52,&H00FFFFFF,&H00FFFFFF,&H96000000,&H78000000,0,-1,0,0,100,100,0,0,1,1.6,2.4,5,60,60,0,1
Style: Sub,Montserrat Medium,44,&H00FFFFFF,&H00FFFFFF,&H96000000,&H78000000,0,-1,0,0,100,100,0,0,1,1.5,2.2,2,70,70,360,1
```

- Every dialogue line gets `{\blur1}`; Title lines get `{\pos(540,Y)\blur1}`.
- Title default Y = 955 (mid-frame). **The title must never sit on a face** —
  check frames per section; when it would cover a mouth/face, move that
  section's Y (e.g. 1195 put it at chest level under an interview closeup).
  Split the title into multiple timed Dialogue events, switching position at
  hard cuts so the move reads as intentional.
- Dialogue subs sit at MarginV 360 (bottom-anchored, ~y1560). One sub visible
  at a time; a sub may hold until the next line starts. Mirror the source
  reel's censoring style (`f*ck`, `sh*t`).

## Grade + scrim + layer order

Layer order is fixed: clips -> grade -> black scrim -> subtitles (text always
on the very front). The current dialed-in look ("50% grade, 13% scrim"):

```
curves=master='0/0.006 0.25/0.2275 0.5/0.5 0.75/0.7725 1/0.994',
colorbalance=rs=-0.03:gs=-0.008:bs=0.038:rm=0.012:bm=-0.01:rh=0.025:bh=-0.028,
eq=saturation=1.1:contrast=1.02:gamma=1.025,
drawbox=x=0:y=0:w=iw:h=ih:color=black@0.13:t=fill,
ass=subs.ass:fontsdir=<skill>/assets/fonts
```

(A filmic S-curve, teal-leaning shadows / warm highlights, mild saturation.
The "100%" version doubled every deviation and used black@0.28 — Chirag found
that too heavy.)

## Encode settings

- Segment intermediates: `-c:v libx264 -preset medium -crf 12 -pix_fmt yuv420p -an`
  (near-lossless so the final encode is the only lossy generation).
- Final: `-c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -movflags +faststart`
  plus `-map_metadata -1` (strip container tags).
- Output: 1080x1920 @ 30fps, `scale=WxH:flags=lanczos`, frame-exact `-frames:v`
  per segment so segment frame counts sum to round(duration*30).
- Sharpening: only on segments upscaled >2x from a 1080p-capped source —
  `cas=0.30` (0.26–0.34) after the scale. 4K-sourced segments need none.

## Audio rebuild

- Speech comes from the source clips, cut at the segments' exact video
  in/out points (lip-sync by construction). Apply the reel's measured speed
  factor with `atempo` when a chunk is speed-shifted.
- Per-segment `volume=` gains from audio_residual.py's rms_gain (mirror the
  reel's levels), 8ms `afade` in/out at every join, then
  `concat` -> `aresample=48000` -> `alimiter=limit=0.97:level=false`.
- Verify: final integrated loudness (`ebur128`) should land within ~0.5 LU of
  the reel's. Encode `-c:a aac -b:a 256k`.
- Music bed (only when residual analysis shows one): identify via shazamio,
  fetch the track with yt-dlp, locate its offset by cross-correlation against
  the reel, gain-match to the reel's music level in low-speech windows, mix
  under the speech. Cannot identify it -> STOP AND ASK.

## Delivery

- Master: `<BASE>/Masters/<Subject>_reel.mp4` (defaults to `~/ReelStudio/Masters/<Subject>_reel.mp4`).
- Chat preview: re-encode `-crf 24`, must be under 30 MB (SendUserFile limit);
  network timeouts on upload happen — retry once, then rely on the local master copy.
