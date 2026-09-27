#!/usr/bin/env python3
"""Identify background music in a reel via Shazam (shazamio).

Usage: identify_music.py audio_or_video_file [start_s] [dur_s]

Probes up to three windows (start, start+dur, start+2*dur) and prints every
match with its confidence context, because speech over the music defeats
recognition in some windows but not others. Each probe is transcoded to a
temp 44.1k mono wav with the bundled ffmpeg first (shazamio's decoder does
not handle every container).

Needs network. If NO window matches, that is the stop-and-ask gate: report
what the music sounds like and ask the user to name the track or provide a file.
"""
import asyncio, os, subprocess, sys, tempfile
from shazamio import Shazam

K = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(K, 'bin', 'ffmpeg')

src = sys.argv[1]
start = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
dur = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0

async def main():
    shazam = Shazam()
    found = False
    for i in range(3):
        t0 = start + i * dur
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            path = tmp.name
        try:
            r = subprocess.run(
                [FF, '-loglevel', 'error', '-y', '-ss', f'{t0}', '-t', f'{dur}',
                 '-i', src, '-vn', '-ac', '1', '-ar', '44100', path],
                capture_output=True)
            if r.returncode != 0 or os.path.getsize(path) < 1000:
                print(f"window {t0:.1f}s: extraction failed/empty (past end?)")
                continue
            out = await shazam.recognize(path)
            track = out.get('track')
            if track:
                found = True
                offset = None
                m = out.get('matches') or []
                if m:
                    offset = m[0].get('offset')
                print(f"window {t0:.1f}s: MATCH  {track.get('title')} — {track.get('subtitle')}"
                      + (f"  (track offset ~{offset:.1f}s)" if offset is not None else ""))
            else:
                print(f"window {t0:.1f}s: no match")
        finally:
            os.unlink(path)
    print("RESULT:", "IDENTIFIED" if found else "UNIDENTIFIED -> stop and ask the user")

asyncio.run(main())
