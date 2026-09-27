---
name: recreate-post
description: Recreate an Instagram post or carousel as a faithful remake — ChatGPT (driven through the browser, source slide + LM logo overlay attached) renders each slide in full with the same text word-for-word, then the renders are metadata-stripped and exported through Canva via the Canva MCP, no source watermarks. Use whenever someone pastes an IG post/carousel link (instagram.com/p/...) and wants it recreated, remade, rebuilt, or "same but better" — including post approvals from the Reel Studio panel.
---

# Recreate Post

Rebuild an IG post or carousel slide-by-slide: ChatGPT renders each slide
in full — imagery, the source's exact words, and (cover only) the LM logo +
side lines from the attached overlay — then the render is metadata-stripped,
renamed, dropped into Canva as a full-bleed page and exported. Never a
filtered repost, never the source's branding.

**Recreate EVERY slide.** A carousel is recreated in full — all slides, in
order. Never sample, cap, or skip slides: a 19-slide source means 19 delivered
slides. If generation is slow, batch it (Step 3) — never trim the count.

**Two hard gates — STOP and ask the user, never silently improvise:**
1. ChatGPT refuses or swaps the likeness of a real person on a slide (it
   normally keeps likeness when the source slide is attached — one re-roll,
   then stop and ask).
2. ChatGPT in the browser is broken after 2 honest retries (logged out, no
   credits, layout changed) — or the Canva MCP / Canva login is down.

Everything else runs full-auto to finished slides; iterate afterward.

**One session, no subagents** — same rule as reels: run the whole post here.
Parallelism comes from batching (all ChatGPT tabs generate simultaneously,
one strip_meta.py loop, one edit-design call per page), not from agents.

**Shared ChatGPT account** — before Step 3, check whether a panel post job
is already generating (`cat ~/ReelStudio/Jobs/*/status.txt | grep "3/6"`).
Two jobs together exceed ChatGPT's 5-concurrent ceiling, so renders queue
for 10+ min. If one is running, wait for it to pass step 3 before opening
tabs.

**Storage** — work in `<BASE>/Work/<post-name>/` (or the panel job's cwd),
where `<BASE>` is `~/ReelStudio` (or `$REELSTUDIO_DIR`).

```bash
K=~/.claude/skills/recreate-post          # this skill
R=~/.claude/skills/recreate-reel          # shared venv + bin (ffmpeg, yt-dlp)
PY="$R/venv/bin/python"
```

## Step 1 — Fetch the source post (Apify only)

```bash
"$PY" "$K/scripts/fetch_post.py" "<post-url>" source
```

Runs Apify's `apify~instagram-scraper` (token configured in Reel Studio UI or `$K/apify_token`) and saves
every slide full-res to `source/slide_NN.jpg` + `source/meta.json` (account,
caption, likes, dims, video flags). **Never open the post on instagram.com in
the browser** — not to fetch, not to "check", not as a fallback (it risks logged-in accounts). On `FETCH-FAILED` stop and tell the user what Apify said.

Video slides (`is_video: true` in meta.json) are saved as `slide_NN.mp4`;
recreate their cover frame as a still unless the user's note says otherwise, and
say so in the final report.

## Step 2 — Study every slide

Never Read slides one by one — every full-res image Read costs 10-50 s of
model time and bloats the context for the rest of the run. Build contact
sheets and Read those (4 slides per Read, text stays legible):

```bash
"$PY" "$K/scripts/sheet.py" qa/src source/slide_*.jpg   # → qa/src_1.jpg, qa/src_2.jpg, ...
```

From the sheets build the slide map before generating anything:

- **Text, exactly**: every word, line break, casing, punctuation, and
  censoring as printed. Proof-read your transcription against the sheet
  twice — it goes into the prompt verbatim and the render must match
  word-for-word. Zoom with a single-slide Read only if a line is genuinely
  unreadable on the sheet.
- **Composition**: who/what is where, the palette, the style (photo collage,
  tweet card, quote card…) — the prompt describes it so the render keeps the
  same layout feel.
- **Source branding to remove**: watermarks (SWIPE tags, page logos, photo
  marks like "AN") and their positions — name each one in the prompt.
- **Cover vs body**: slide 1 gets the LM logo + side lines; slides 2+ get no
  logo at all.

## Step 3 — Render every slide in ChatGPT (Brave)

Drive chatgpt.com through claude-in-chrome in **waves of 5 slides, one tab
per slide — 5 is a measured ceiling, not a preference** (Sep 14, 2026: 10
simultaneous prompts → 4 rendered, 6 refused, and ChatGPT locked the whole
account with "Too many requests… wait a few minutes" for well over 3 min;
5 concurrent has worked in every real job). Submits must be **≥4 s apart**
— a burst of sends within a few seconds is what trips the lock, regardless
of tab count. If a tab ever shows "Too many requests": stop submitting,
close nothing, wait 10 min, then continue the wave; never retry in a loop.
Time is spent per tool call (~20 s each), so a wave is a fixed budget of
**7 calls** — never one call per slide for anything:

1. **Tabs** — ONE `browser_batch`: `tabs_create_mcp` ×5 (first wave: the
   `tabs_context_mcp createIfEmpty` tab counts as one), `navigate` each to
   https://chatgpt.com/, `wait 5`, `find` "file input in the chat message
   composer form (input type=file)" ×5.
2. **Attach** — ONE `browser_batch`: `file_upload` ×5 (each tab gets its
   slide's `source/slide_NN.jpg`; the cover also gets
   `$K/assets/lm-logo-reference.jpg` — the transparent overlay is invisible
   to ChatGPT), then `wait 4`.
3. **Submit** — ONE `browser_batch` with 5 `javascript_tool` actions
   **separated by `wait 4`**, each: `#prompt-textarea` focus →
   `execCommand('insertText', false, PROMPT)` → `await` 800 ms →
   `#composer-submit-button` click.
   **Prompt shape** (exact text spelled out):
   - "Recreate the first attached image as a finished, sharp, high-resolution
     4:5 design with the same composition: <who/what where, palette>."
   - "Keep the text EXACTLY, word for word: <verbatim text>" — cover: bold
     white condensed uppercase (Anton-style) over the dark gradient, all
     white (no coloured words).
   - "REMOVE the '<watermark>' at <position> and the '<page logo>' at
     <position>."
   - Cover only: "Instead, place the white 'LM' monogram with its thin fading
     horizontal side lines exactly as shown in the second attached image,
     centred directly above the headline." Body: "do NOT add any logo,
     watermark or extra text."
   - "Portrait output; keep every element inside the central 4:5 area and
     extend the background above and below." (a 4:5 source comes back
     1122x1402 — no crop needed.)
4. **Poll + download** — `browser_batch` has its own ~2 min ceiling, so
   never stack the 50 s wait AND five 35 s polls in one call: one batch of
   `wait 10` ×5, then a batch with the per-tab JS below **followed by
   `wait 3`** (a `pending` tab just gets another short batch later) (Brave drops blob downloads fired
   within ~2 s of each other as 0-byte `FILE_FAILED`; spaced ones always
   land — either under their name or as a full-size
   `~/Downloads/.com.brave.Browser.XXXXXX` temp file, which is why the
   collect step matches by byte size). The JS never throws, so the batch
   never stops early, and the in-page poll stays under the 45 s CDP limit:
   ```js
   const t0=Date.now(); let img=null;
   while(Date.now()-t0<35000){ const g=[...document.querySelectorAll('img[src*="estuary"]')]
     .filter(i=>!i.closest('[data-message-author-role="user"]')&&i.naturalWidth>500);
     if(g.length){img=g[g.length-1];break;} await new Promise(r=>setTimeout(r,2000)); }
   if(!img){'pending'} else { const b=await (await fetch(img.src)).blob();
     const a=document.createElement('a'); a.href=URL.createObjectURL(b); a.download='${SLUG}_NN.png';
     document.body.appendChild(a); a.click(); a.remove(); JSON.stringify({size:b.size,w:img.naturalWidth,h:img.naturalHeight}) }
   ```
   Any `pending` → one more batch of `wait 10` ×3 + the same JS (+ `wait 3`)
   for those tabs only.
5. **Collect** — ONE Bash, the script does the matching, moving, stripping
   and status update:
   ```bash
   "$PY" "$K/scripts/collect.py" $SLUG 06:1491134 07:877152 08:931335 09:1399613 10:881108
   ```
   (`NN:SIZE` pairs **from step 4's JSON only — never from `ls ~/Downloads`**:
   a panel job may be downloading its own slides into the same folder at the
   same time, which is also why the download name is `${SLUG}_NN.png`, not a
   generic name). It takes `~/Downloads/${SLUG}_NN.png` or the exact-size
   `.com.brave.Browser.*` temp file, writes
   `raw/slide_NN.png` + `gen/${SLUG}_NN.png`, deletes 0-byte `Unconfirmed`
   stubs, and exits 1 listing `MISSING` slides. **A missing slide** → open
   that conversation's URL in a NEW tab, run the download JS once, `wait 3`,
   run collect again for that slide. One download per tab, ever. Do not
   inspect Brave prefs, history or dialogs — the pipeline is understood:
   chatgpt.com's CSP blocks any fetch to localhost, so a download is the
   only way out of the page, and spaced single downloads are the reliable
   form.
6. **QA** — `sheet.py qa/raw_wN raw/slide_*.png` for the wave, ONE Read.
   Wrong words, wrong layout, missing/misdrawn logo, leftover watermark,
   changed face → one re-roll with the correction spelled out, in that
   slide's tab (its conversation keeps the context), then a fresh tab for
   the download.
7. **Close** — ONE `browser_batch`: `tabs_close_mcp` ×5. The next wave
   starts at 1 with new tabs.

While a wave generates (~60-90 s after submit) there is nothing to wait on
by hand — the `wait 10` ×5 in step 4 is the whole pause. A 3-slide post is
one wave ≈ 4 min; an 18-slide carousel is 4 waves ≈ 16 min.

`raw/` files still carry ChatGPT's C2PA manifest — never upload or deliver
one.

## Step 4 — Strip metadata + rename

Done by `collect.py` in Step 3 (it calls `strip_meta.py`, which re-encodes
pixels only — dropping C2PA/JUMBF, XMP, EXIF, tEXt, ICC — then runs
`exiftool -all=` and exits non-zero if any provenance tag survives; treat
that as a bug in the strip, never something to skip). Only
`gen/${SLUG}_NN.png` files go to Canva; `raw/` never leaves the machine.
Manual form if ever needed: `"$PY" "$K/scripts/strip_meta.py" raw/slide_NN.png gen/${SLUG}_NN.png`.

## Step 5 — Canva

Canva is the page container and exporter only — every slide is already a
finished render. Two ways in; use A whenever it is authorised.

### A. Connect API script (one call, ~30-60 s for any slide count)

```bash
"$PY" "$K/scripts/canva_connect.py" build "LM Post - <HEADLINE>" gen/*.png
```

Builds a lossless 1080x1350 multi-page PDF from the clean renders, imports it
as a new Canva design (one page per render), exports every page as JPG
(quality 100, pro, 1080x1350) and downloads them untouched to
`post/slide_NN.jpg`. Prints `CANVA-OK <design_id> <N> slides` and the design
URL for the report. Verified Sep 14, 2026: 18 slides in 2 min 49 s,
pixel-identical to the renders, Canva EXIF present. The integration
("LM recreate-post", authorised for rax.ai.arc@gmail.com) is set up and the
token auto-refreshes; if the script ever exits "not authorised", run
`canva_connect.py auth` from a normal session (it needs one Allow click in
Brave) — never inside a panel job; use B for that post instead.

### B. MCP fallback (one `edit-design` call per page)

Start from a **fresh copy** of the LM template `DAHPi6lG9Js`
(https://canva.link/29vmafe3rbqrfe4, 1080x1350, **3 pages**: 1 = cover,
2 = white page holding only the LM logo group, 3 = body) — the template
itself is never edited or committed.

1. **Copy + size.** `copy-design` (design_id `DAHPi6lG9Js`) → working design
   `W` (3 pages). For N slides > 3: ONE `merge-designs` call,
   `type: modify_existing_design`, `design_id: W`, single op
   `insert_pages` from `DAHPi6lG9Js` with `page_numbers: [3, 3, ...]`
   (N-3 threes — one op per call; repeated page numbers duplicate). Title
   via `update_title` in the first edit call. Fewer slides than pages: leave
   the spare pages alone and export only pages 1..N — never `delete_pages`.
2. **Upload the clean renders** — the MCP's `upload-asset-from-url` only takes
   public URLs, so upload through Chirag's own Canva session instead
   (private, nothing published): open `W`'s edit URL in a claude-in-chrome
   tab, wait ~8 s for the editor, click **Uploads** in the left rail and
   confirm the panel opened (screenshot — an early click is swallowed), then
   `find` "file input (type=file) in the Uploads panel" and `file_upload`
   the `gen/${SLUG}_NN.png` files (≤10 MB per call — batch by size). Wait
   ~20 s, then `list-folder-items` with `folder_id: "uploads"`,
   `item_types: ["image"]`, `sort_by: created_descending` — the newest items
   are the renders, mapped to asset IDs by `name`. Close the tab.
3. **Read the copy.** `read-design` `W` with `open_transaction: true` and
   `filter.fields: ["page_metadata"]` only — no `design_content` dump. Page 1
   keeps the template's IDs (photo rect `LB752dsg3K3R8XTd`, scrim
   `LBLh255VbQKhbYq8`, logo group `LByyFZfQd8bmX9CD`, headline
   `LBrkKQBwtPfmQtyL`, all prefixed `PBTtkcLzhzTz5pL4-`); page 2 keeps its
   logo group `PB0sG2cjrNTrnwKt-LB2YxhYK0Sz8CNS1`. Inserted pages get new IDs:
   read `design_content` for those pages only, in chunks of 6.
4. **One `edit-design` call per page** (`finalize: keep_open`). Pages with a
   photo frame: `update_fill` → `resize_element` 1080x1350
   (`preserve_aspect_ratio: false`) → `position_element` 0,0 → `crop_media`
   0/0/1080/1350 → `delete_element` for the scrim, logo group and every
   text element. Page 2 (no frame): `delete_element` the logo group, then
   `insert_fill` with `page_id`, the asset, `top: 0, left: 0, width: 1080,
   height: 1350`. The resize/position/crop trio is required on existing
   frames — `update_fill` alone keeps the template's hand-crop and shows a
   zoomed band. Look at the returned thumbnail: the page must be exactly the
   render, nothing else on it. No status-update Bash calls between pages —
   update status every 5 pages inside the next needed Bash.
5. **Commit once** after every page checks out: `edit-design` with
   `finalize: "commit"` and no operations. Cancel and redo if anything is off
   — never commit a half-done design.
6. **Export** — `get-export-formats` once, then `export-design`
   `{type:"jpg", quality:100, export_quality:"pro", pages:[1..N]}` and hand
   the URLs to Step 6.

## Step 6 — QA + deliver

ONE Bash — the script downloads (MCP path) or reuses `post/` (script path),
verifies 1080x1350, builds the QA pairs + sheet, and copies to Masters and
`final/`:

```bash
"$PY" "$K/scripts/export_dl.py" "<Subject>" --from-dir post        # after canva_connect.py build
"$PY" "$K/scripts/export_dl.py" "<Subject>" "<url1>" "<url2>" ...   # after MCP export-design
```

**Never touch the exported files' metadata** — Canva's EXIF stays exactly as
exported (Chirag's rule — only ChatGPT's files get stripped, in Step 4).

Then Read `qa/pairs_*.jpg` (source | recreation, 4 pairs per sheet) and
actually look: text matches the source word-for-word, layout feel matches,
no source watermark or page logo, faces not mangled, LM logo + side lines on
slide 1 only. Anything off → fix that slide (Iterating) before reporting.

- Report: slide count, Canva design URL, any re-rolls or substitutions, and
  that the renders are ChatGPT-generated (C2PA stripped; an invisible pixel
  watermark may remain — nothing strips that).

## Step 7 — Caption → humanizer → Telegram

1. Take the original caption from `source/meta.json` (`caption`) and write a
   **variation**: same facts and same beats in the same order, different
   wording, no line copied verbatim, the source page's "follow us" line and
   handle dropped, emojis kept sparingly where the source used them, ending
   on the source's question or hook if it had one. Never add a fact the
   source doesn't state.
2. **REQUIRED SUB-SKILL:** run it through `humanizer` (embedded mode: final
   text only). Straight quotes, no dashes, no one-line closers, no
   "let's dive in" openers.
3. Send it with the telegram-mcp to **Mummy ❤️** (chat_id `8131470331`,
   @moniterr — search_contacts "mummy" if the id ever changes), one
   `send_message` per post, plain text, **the caption and nothing else** —
   no "Caption:" label, no post name, no preamble; the message must be
   copy-paste ready for Instagram. Sending the slides themselves is not part
   of this step unless Chirag asks.
4. Put the same caption in the report.

## Iterating

Any change = re-render that slide's ChatGPT tab with the correction spelled
out, `collect.py` for that slide, then Step 5 again (path A rebuilds the
whole design in one call; path B: browser-upload the one file, `update_fill`
+ the resize/position/crop trio on that page, commit, re-export that page)
and `export_dl.py`. Keep the
workdir and `W` until the post is signed off. `compose.py` (Pillow text over
a generated background) stays in `scripts/` only for an explicit request for
a non-ChatGPT render.
