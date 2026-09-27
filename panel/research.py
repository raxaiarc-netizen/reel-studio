#!/usr/bin/env python3
"""Reel Studio research engine.

Scans the last 10 posts of every curated account, ranks reels by views and
posts by likes, downloads thumbnails for the winners, and persists candidates
+ approval state to research.json. Fetch order per account: anonymous
web_profile_info (UA-rotated) first; Brave session cookies only as a last
resort (exported on demand).
"""
import json, os, subprocess, threading, time, urllib.request, urllib.parse, http.cookiejar

BASE = os.path.dirname(os.path.abspath(__file__))
RESEARCH_JSON = os.path.join(BASE, 'research.json')
DEFAULT_STORAGE = os.path.expanduser('~/ReelStudio')
COOKIES = os.path.join(BASE, 'ig_cookies.txt')
K = os.path.dirname(BASE)


def storage():
    """Active storage base: ~/ReelStudio (or REELSTUDIO_DIR env var)."""
    return os.environ.get('REELSTUDIO_DIR', DEFAULT_STORAGE)


def thumbs_dir():
    return os.path.join(storage(), 'Thumbs')


def post_ideas_dir():
    return os.path.join(storage(), 'PostIdeas')


def thumb_path(name):
    """Find a thumbnail in thumbs_dir."""
    p = os.path.join(thumbs_dir(), name)
    return p if os.path.exists(p) else None


def get_apify_token():
    tok = os.environ.get('APIFY_TOKEN')
    if not tok:
        for p in [os.path.join(BASE, 'apify_token'),
                  os.path.join(os.path.dirname(BASE), 'skills', 'recreate-post', 'apify_token'),
                  os.path.expanduser('~/.claude/skills/recreate-post/apify_token')]:
            if os.path.exists(p):
                try:
                    tok = open(p).read().strip()
                    if tok:
                        break
                except OSError:
                    pass
    return tok or ''

REEL_ACCOUNTS = ['lolita', 'steven', 'the_goodfilms', 'evolving.ai', 'joerogan',
                 'jayshetty', 'melrobbins', 'theovon', 'hubermanlab',
                 'patrickbetdavid', 'chriswillx', 'shawnryanshow', 'lexfridman']
POST_ACCOUNTS = ['wealth', 'mindset.therapy']

UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0",
]
os.makedirs(thumbs_dir(), exist_ok=True)

state = {'running': False, 'progress': '', 'lock': threading.Lock()}


def _load():
    try:
        return json.load(open(RESEARCH_JSON))
    except (OSError, ValueError):
        return {'ran_at': None, 'reels': [], 'posts': [], 'errors': []}


def _save(d):
    with open(RESEARCH_JSON, 'w') as f:
        json.dump(d, f, indent=1)


def _anon_fetch(username, ua):
    req = urllib.request.Request(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        headers={"User-Agent": ua, "x-ig-app-id": "936619743392459"})
    return json.load(urllib.request.urlopen(req, timeout=25))['data']['user']


def _brave_opener():
    if not os.path.exists(COOKIES) or time.time() - os.path.getmtime(COOKIES) > 86400:
        subprocess.run([os.path.join(K, 'bin', 'yt-dlp'), '--cookies-from-browser', 'brave',
                        '--cookies', COOKIES, '--skip-download', '--simulate',
                        'https://www.youtube.com/watch?v=vPncWhSR_dI'],
                       capture_output=True, timeout=120)
    cj = http.cookiejar.MozillaCookieJar(COOKIES)
    cj.load(ignore_discard=True, ignore_expires=True)
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [('User-Agent', UAS[0]), ('x-ig-app-id', '936619743392459'),
                     ('Referer', 'https://www.instagram.com/')]
    return op


def fetch_account(username, idx, brave):
    """Last-12 timeline posts, newest first. Raises on total failure."""
    for attempt in range(2):
        try:
            return _anon_fetch(username, UAS[(idx + attempt) % len(UAS)]), brave
        except Exception:
            time.sleep(3)
    if brave is None:
        brave = _brave_opener()
    d = json.load(brave.open(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        timeout=25))['data']['user']
    return d, brave


def _grab_thumb(code, url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UAS[0]})
        data = urllib.request.urlopen(req, timeout=25).read()
        with open(os.path.join(thumbs_dir(), f'{code}.jpg'), 'wb') as f:
            f.write(data)
        return True
    except Exception:
        return False


def run(new_job):
    """Full research pass. new_job(url, note, model) is the panel's job creator
    (unused here, kept for signature parity with approve)."""
    with state['lock']:
        if state['running']:
            return
        state['running'] = True
    try:
        os.makedirs(thumbs_dir(), exist_ok=True)
        old = _load()
        old_status = {c['code']: c for c in old.get('reels', []) + old.get('posts', [])}
        reels, posts, errors = [], [], []
        brave = None
        for i, acct in enumerate(REEL_ACCOUNTS + POST_ACCOUNTS):
            state['progress'] = f"scanning @{acct} ({i + 1}/{len(REEL_ACCOUNTS) + len(POST_ACCOUNTS)})"
            try:
                user, brave = fetch_account(acct, i, brave)
            except Exception as e:
                errors.append(f"@{acct}: {type(e).__name__}")
                continue
            edges = user['edge_owner_to_timeline_media']['edges']
            items = sorted((e['node'] for e in edges),
                           key=lambda n: n['taken_at_timestamp'], reverse=True)[:10]
            for n in items:
                cap = ''.join(x['node']['text'] for x in
                              n.get('edge_media_to_caption', {}).get('edges', [])[:1])[:120]
                base = {'account': acct, 'code': n['shortcode'],
                        'taken_at': n['taken_at_timestamp'],
                        'likes': n['edge_liked_by']['count'],
                        'caption': cap, 'thumb_url': n.get('display_url', '')}
                if acct in REEL_ACCOUNTS and n.get('is_video'):
                    base['views'] = n.get('video_view_count') or 0
                    base['url'] = f"https://www.instagram.com/reel/{n['shortcode']}/"
                    reels.append(base)
                elif acct in POST_ACCOUNTS and not n.get('is_video'):
                    base['url'] = f"https://www.instagram.com/p/{n['shortcode']}/"
                    posts.append(base)
            time.sleep(4)

        # Keep a deep ranked pool so rejecting a candidate reveals the next one.
        reels = sorted(reels, key=lambda c: -c.get('views', 0))[:30]
        posts = sorted(posts, key=lambda c: -c['likes'])[:12]
        for rank, c in enumerate(reels, 1):
            c['rank'] = rank
            c['kind'] = 'reel'
        for rank, c in enumerate(posts, 1):
            c['rank'] = rank
            c['kind'] = 'post'
        state['progress'] = 'downloading thumbnails'
        for i, c in enumerate(reels + posts):
            prev = old_status.get(c['code'], {})
            c['status'] = prev.get('status', 'pending')
            c['job_id'] = prev.get('job_id')
            have = bool(thumb_path(f"{c['code']}.jpg"))
            want = (c['kind'] == 'reel' and c['rank'] <= 20) or \
                   (c['kind'] == 'post' and c['rank'] <= 8)
            c['has_thumb'] = have or (want and _grab_thumb(c['code'], c['thumb_url']))
            c.pop('thumb_url', None)
        _save({'ran_at': time.time(), 'reels': reels, 'posts': posts, 'errors': errors})
        state['progress'] = 'done'
    finally:
        state['running'] = False


def get():
    d = _load()
    d['running'] = state['running']
    d['progress'] = state['progress']
    return d


def act(code, action, new_job, note='', model=''):
    """approve/dismiss a candidate. Approving a reel queues recreation NOW,
    with the model + extra instructions chosen in the Research toolbar."""
    d = _load()
    for c in d['reels'] + d['posts']:
        if c['code'] != code:
            continue
        if action == 'dismiss':
            c['status'] = 'dismissed'
        elif action == 'reset':
            c['status'] = 'pending'
            c['job_id'] = None
        elif action == 'approve':
            # Reels AND posts both queue a real recreation job now; posts also
            # keep their thumbnail in PostIdeas as a browsable archive.
            j = new_job(c['url'], note, model, c['kind'])
            c['status'] = 'approved'
            c['job_id'] = j['id']
            c['note'], c['model'] = note, model
            if c['kind'] == 'post':
                os.makedirs(post_ideas_dir(), exist_ok=True)
                src = thumb_path(f"{code}.jpg")
                if src:
                    import shutil
                    shutil.copy(src, os.path.join(post_ideas_dir(),
                                                  f"{c['account']}_{code}.jpg"))
        _save(d)
        return c
    return None
