#!/usr/bin/env python3
"""Fetch an Instagram post/carousel: every slide at full resolution + metadata.

Usage: fetch_post.py <post-url-or-shortcode> [outdir]

Writes <outdir>/slide_NN.jpg (and slide_NN.mp4 for video slides) plus
<outdir>/meta.json (account, caption, taken_at, per-slide dims/type).

Single path, by Chirag's rule: the Apify `apify~instagram-scraper` actor, run
synchronously. Instagram is NEVER opened in the browser for fetching. The token
lives next to this script in ../apify_token (one line); APIFY_TOKEN in the
environment overrides it. On failure it exits 2 with FETCH-FAILED and the
Apify error — stop and tell Chirag, don't improvise another fetch path.
"""
import json, os, re, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, '..', 'apify_token')
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
ACTOR = 'apify~instagram-scraper'


def shortcode_of(arg):
    m = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', arg)
    return m.group(1) if m else arg.strip('/')


def token():
    t = os.environ.get('APIFY_TOKEN', '').strip()
    if not t:
        for sp in [os.path.join(HERE, '..', '..', '..', 'panel', 'settings.json'),
                   os.path.join(HERE, '..', '..', 'panel', 'settings.json'),
                   os.path.expanduser('~/.claude/skills/recreate-reel/panel/settings.json')]:
            if os.path.exists(sp):
                try:
                    t = json.load(open(sp)).get('apify_token', '').strip()
                    if t:
                        break
                except Exception:
                    pass
    if not t and os.path.exists(TOKEN_FILE):
        try:
            t = open(TOKEN_FILE).read().strip()
        except OSError:
            pass
    if not t:
        raise RuntimeError('No Apify API key found. Set it in the Reel Studio UI (Apify Key button) or export APIFY_TOKEN.')
    return t


def apify_post(code):
    """Run the scraper synchronously for one post; return the dataset item."""
    url = (f'https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items'
           f'?token={urllib.parse.quote(token())}')
    body = json.dumps({'directUrls': [f'https://www.instagram.com/p/{code}/'],
                       'resultsType': 'posts', 'resultsLimit': 1,
                       'addParentData': False}).encode()
    req = urllib.request.Request(url, data=body, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        items = json.load(r)
    if not items:
        raise RuntimeError('Apify returned no items (private/removed post?)')
    item = items[0]
    if item.get('error') or item.get('errorDescription'):
        raise RuntimeError(f"Apify: {item.get('error')} {item.get('errorDescription', '')}")
    return item


def slides_from_apify(item):
    """Normalize an Apify post item → (account, caption, taken_at, [slide])."""
    def one(it):
        return {'image': it.get('displayUrl'),
                'w': it.get('dimensionsWidth'), 'h': it.get('dimensionsHeight'),
                'video': it.get('videoUrl') if it.get('type') == 'Video' else None}
    kids = item.get('childPosts') or []
    slides = [one(k) for k in kids] if kids else [one(item)]
    return (item.get('ownerUsername', ''), item.get('caption', ''),
            item.get('timestamp'), slides)


def grab(url, path):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, 'wb') as f:
        f.write(r.read())


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    code = shortcode_of(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else 'source'
    os.makedirs(out, exist_ok=True)

    try:
        item = apify_post(code)
        account, caption, taken_at, slides = slides_from_apify(item)
    except Exception as e:
        print(f'FETCH-FAILED: {type(e).__name__}: {e}\n'
              'Apify is the required fetch path for posts and carousels. '
              'Please check your Apify API key in the Reel Studio UI or environment.')
        sys.exit(2)

    meta = {'shortcode': code, 'account': account, 'caption': caption,
            'taken_at': taken_at, 'via': 'apify', 'likes': item.get('likesCount'),
            'comments': item.get('commentsCount'), 'slides': []}
    for i, s in enumerate(slides, 1):
        rec = {'n': i, 'w': s['w'], 'h': s['h'], 'is_video': bool(s['video'])}
        if s['image']:
            rec['file'] = f'slide_{i:02d}.jpg'
            grab(s['image'], os.path.join(out, rec['file']))
        if s['video']:
            rec['video_file'] = f'slide_{i:02d}.mp4'
            grab(s['video'], os.path.join(out, rec['video_file']))
        meta['slides'].append(rec)
        print(f"slide {i}/{len(slides)}: {s['w']}x{s['h']}"
              f"{' VIDEO' if s['video'] else ''}")
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print(f"FETCH-OK: @{account} · {len(slides)} slide(s) via apify → {out}/")


if __name__ == '__main__':
    main()
