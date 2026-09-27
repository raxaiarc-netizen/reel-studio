#!/usr/bin/env python3
"""Reel Studio — local panel server for the recreate-reel skill.

Each job runs a REAL interactive Claude session inside a detached tmux
terminal (silent in the background, attachable in Terminal on demand), with
--dangerously-skip-permissions, Remote Control enabled (named reel-<id>, so
it's controllable from claude.ai / phone), a pinned --session-id, and an
optional per-reel model + extra instructions.

Because every job owns its session id, a job is a resumable thing: Pause kills
the session, Resume relaunches `claude --resume <sid>` in the same workdir and
the reel carries on from the step it reached. A dead tmux server, a panel
restart or a Mac reboot therefore costs nothing but a click.

Jobs run in parallel up to settings.max_concurrent. Progress comes from each
job's status.txt (the prompt protocol) plus the live tmux pane.

Stdlib only. Run via start.sh; state lives in <STORAGE>/Jobs/<id>/.
"""
import json, os, re, shutil, subprocess, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import research

BASE = os.path.dirname(os.path.abspath(__file__))
PANEL_HTML = os.path.join(BASE, 'panel.html')
SETTINGS_PATH = os.path.join(BASE, 'settings.json')
PROJECTS = os.path.expanduser('~/.claude/projects')
PORT = 7799
MAX_AUTO_RESUME = 2          # unattended retries before a job waits for you

# Storage: ~/ReelStudio (configurable via REELSTUDIO_DIR environment variable)
DEFAULT_STORAGE = os.path.expanduser('~/ReelStudio')

DEFAULTS = {'queue_paused': False, 'max_concurrent': 3, 'auto_resume': True}
settings = dict(DEFAULTS)


def base():
    return os.environ.get('REELSTUDIO_DIR', DEFAULT_STORAGE)


def jobs_dir():
    return os.path.join(base(), 'Jobs')


def masters():
    return os.path.join(base(), 'Masters')


def masters_posts():
    return os.path.join(base(), 'Masters', 'Posts')


def disk_free_gb():
    try:
        s = os.statvfs(base() if os.path.isdir(base()) else os.path.expanduser('~'))
        return round(s.f_bavail * s.f_frsize / 1e9, 1)
    except OSError:
        return None


os.makedirs(os.path.join(base(), 'Jobs'), exist_ok=True)
os.makedirs(os.path.join(base(), 'Masters'), exist_ok=True)
os.makedirs(os.path.join(base(), 'Masters', 'Posts'), exist_ok=True)

# Code version = newest mtime of the python modules. start.sh compares this
# against the files on disk and kills/replaces any running server that doesn't
# match, so a stale server can never silently swallow requests again.
VERSION = str(int(max(
    os.path.getmtime(os.path.abspath(__file__)),
    os.path.getmtime(os.path.join(BASE, 'research.py')))))


def find(cmd, *fallbacks):
    p = shutil.which(cmd)
    if p:
        return p
    for f in fallbacks:
        if os.path.exists(f):
            return f
    return cmd


CLAUDE = find('claude', os.path.expanduser('~/.local/bin/claude'))
TMUX = find('tmux', '/opt/homebrew/bin/tmux', '/usr/local/bin/tmux')

RULES_T = """Panel rules:
1. Progress: at EVERY pipeline step, overwrite the file ./status.txt (in your cwd) with one line: "<step>/{n}|<short label>" — e.g. "{example}". Write "{n}/{n}|delivered" when finished.
2. Source Clip Origin Box: The moment you identify/find each source clip origin (Step 3 / gate #1), IMMEDIATELY write or append it to ./source_origin.txt in your cwd with Title, URL, and Channel/Origin. Example:
Title: <Video Title>
URL: https://www.youtube.com/watch?v=...
Origin: <Channel or Creator Name>
The UI panel displays this in real-time in the Source Clip Origin box on your job card so the user sees exactly where the clip was sourced!
3. When finished, also copy the final {final_desc} (in addition to the Masters copy the skill makes).
4. The skill's stop-and-ask gates: write "BLOCKED|<your question in one line>" to ./status.txt, then ask the question and end your turn. The user's answer arrives as the next message — continue from exactly where you stopped.
5. For anything that is NOT one of the skill's hard gates, never wait for confirmation: make the reasonable default choice and note it in your final summary.
6. Chat file delivery (SendUserFile) may be unavailable here — if it fails, skip it; the panel previews {preview} itself.
7. Storage: do ALL work in your cwd (downloads, sources, renders), never in /tmp or a scratchpad. Deliver to '{masters}/', plus the {finloc} copy.
8. This session can be paused and resumed by the panel at any time, so keep ./status.txt honest — it is the only thing that tells a resumed session where you left off.
9. Do the whole {thing} in THIS session — never spawn subagents (Agent tool) or workflows. The panel already runs jobs in parallel lanes; fanning out inside a job only makes it slower. Background long jobs (downloads, renders) instead.{extra}"""

KINDS = {
    'reel': {
        'n': 11, 'skill': 'recreate-reel', 'thing': 'reel',
        'example': '3/11|hunting sources (checking 4K)',
        'final_desc': 'master to ./final.mp4 in your cwd',
        'preview': './final.mp4', 'finloc': './final.mp4',
        'masters': masters, 'extra': '',
        'task': 'Recreate this reel end-to-end using the recreate-reel skill',
    },
    'post': {
        'n': 6, 'skill': 'recreate-post', 'thing': 'post',
        'example': '3/6|generating imagery (4 of 8 tabs done)',
        'final_desc': 'slides to ./final/slide_NN.jpg in your cwd',
        'preview': './final/', 'finloc': './final/',
        'masters': masters_posts,
        'extra': '\n9. The browser (Brave + chatgpt.com tabs) is shared with the rest '
                 'of the Mac — the panel runs only one post job at a time; close your '
                 'ChatGPT tabs once the post is delivered.'
                 '\n10. Recreate EVERY slide of a carousel — all of them, in order. '
                 'Never sample, cap, or skip slides: a 19-slide source means 19 '
                 'delivered slides.',
        'task': 'Recreate this Instagram post/carousel end-to-end using the '
                'recreate-post skill',
    },
}


def rules_for(kind):
    k = KINDS.get(kind) or KINDS['reel']
    return RULES_T.format(n=k['n'], example=k['example'], final_desc=k['final_desc'],
                          preview=k['preview'], finloc=k['finloc'],
                          masters=k['masters'](), thing=k['thing'], extra=k['extra'])


def prompt_for(j):
    k = KINDS.get(j.get('kind')) or KINDS['reel']
    return (f"{k['task']}: {j['url']}\n\nYou are running from the Reel Studio panel "
            "(the user watches a progress panel, your terminal, or Remote Control — "
            "not this chat). " + rules_for(j.get('kind')))


def resume_prompt_for(j):
    k = KINDS.get(j.get('kind')) or KINDS['reel']
    return (f"Your previous session on this {k['thing']} was interrupted before it "
            "finished. RESUME it — do not start over.\n\nFirst, work out exactly "
            "where you stopped: read ./status.txt and inspect what is already in "
            "your cwd (downloads, sources, generated images, renders). Trust the "
            "files on disk, not your memory — re-verify anything ambiguous, and "
            "never redo a step whose output already exists and is good. Then "
            f"continue the {k['skill']} pipeline from that point straight through "
            "to delivery.\n\n" + rules_for(j.get('kind')))


def total_of(j):
    return (KINDS.get(j.get('kind')) or KINDS['reel'])['n']

jobs = {}
lock = threading.Lock()
_res_cache = {}


# ── settings ────────────────────────────────────────────────────────────────
def load_settings():
    try:
        settings.update({k: v for k, v in json.load(open(SETTINGS_PATH)).items()
                         if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    settings['max_concurrent'] = max(1, min(6, int(settings['max_concurrent'])))


def save_settings():
    try:
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(settings, f, indent=1)
    except OSError:
        pass


def get_apify_token():
    tok = settings.get('apify_token') or os.environ.get('APIFY_TOKEN')
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


def save_apify_token(tok):
    settings['apify_token'] = tok
    save_settings()
    os.environ['APIFY_TOKEN'] = tok
    for p in [os.path.join(BASE, 'apify_token'),
              os.path.join(os.path.dirname(BASE), 'skills', 'recreate-post', 'apify_token'),
              os.path.expanduser('~/.claude/skills/recreate-post/apify_token')]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w') as f:
                f.write(tok.strip() + '\n')
        except OSError:
            pass


def get_source_origin(j):
    """Read source clip provenance from job directory or dl logs."""
    # 1. Direct file written by Claude session
    for fname in ('source_origin.txt', 'sources.txt', 'source.txt'):
        p = os.path.join(j['dir'], fname)
        if os.path.exists(p):
            try:
                txt = open(p, errors='ignore').read().strip()
                if txt:
                    return txt
            except OSError:
                pass
    # 2. Extract from download logs in src/
    src_dir = os.path.join(j['dir'], 'src')
    if os.path.isdir(src_dir):
        for lf in sorted(os.listdir(src_dir)):
            if lf.endswith('.log'):
                lp = os.path.join(src_dir, lf)
                try:
                    with open(lp, errors='ignore') as f:
                        for line in f:
                            if 'Extracting URL:' in line:
                                url = line.split('Extracting URL:', 1)[1].strip()
                                stem = lf.replace('_dl.log', '').replace('.log', '')
                                return f"URL: {url}\nClip: {stem}"
                except OSError:
                    pass
    return None


# ── tmux + session plumbing ─────────────────────────────────────────────────
_sess = {'at': 0.0, 'names': set()}


def tmux(*args, capture=False):
    try:
        r = subprocess.run([TMUX, *args], capture_output=True, text=True, timeout=10)
        if args and args[0] in ('new-session', 'kill-session'):
            _sess['at'] = 0.0          # liveness cache is stale the moment we change it
        return r.stdout if capture else (r.returncode == 0)
    except Exception:
        return '' if capture else False


def tname(jid):
    return f"rs_{jid}"


def alive(jid):
    """One `list-sessions` a second serves every job, instead of a `has-session`
    per job per poll (that was ~6 tmux spawns a second with a full panel)."""
    if time.time() - _sess['at'] > 1.0:
        _sess['names'] = set(tmux('list-sessions', '-F', '#{session_name}',
                                  capture=True).split())
        _sess['at'] = time.time()
    return tname(jid) in _sess['names']


def proj_dir(j):
    """Where Claude keeps this workdir's transcripts (~/.claude/projects/<slug>)."""
    return os.path.join(PROJECTS, re.sub(r'[^A-Za-z0-9]', '-', j['dir']))


def transcript_sid(j):
    """Newest non-empty transcript for this job's workdir, or None."""
    sid = j.get('session_id')
    if sid and os.path.exists(os.path.join(proj_dir(j), sid + '.jsonl')):
        return sid
    d = proj_dir(j)
    try:
        fs = [f for f in os.listdir(d)
              if f.endswith('.jsonl') and os.path.getsize(os.path.join(d, f)) > 200]
    except OSError:
        return None
    if not fs:
        return None
    fs.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)))
    return fs[-1][:-6]


def resumable(j):
    """Is there saved work a Resume would pick up? Cached — polled every 2s."""
    if j['state'] in ('running', 'blocked'):
        return False
    hit = _res_cache.get(j['id'])
    if hit and time.time() - hit[0] < 15:
        return hit[1]
    val = bool(transcript_sid(j))
    _res_cache[j['id']] = (time.time(), val)
    return val


META_KEYS = ('id', 'url', 'note', 'model', 'kind', 'state', 'created', 'started',
             'ended', 'activity', 'session_id', 'step', 'label', 'runs',
             'auto_resumes', 'removed')


def save_meta(j):
    try:
        with open(os.path.join(j['dir'], 'meta.json'), 'w') as f:
            json.dump({k: j.get(k) for k in META_KEYS}, f)
    except OSError:
        pass


def detect_kind(url):
    return 'post' if ('instagram.com' in url and '/p/' in url) else 'reel'


def new_job(url, note='', model='', kind=''):
    jid = f"j{int(time.time()) % 1000000}{len(jobs) % 100:02d}"
    d = os.path.join(jobs_dir(), jid)
    os.makedirs(d, exist_ok=True)
    j = {'id': jid, 'url': url, 'note': note, 'model': model,
         'kind': kind or detect_kind(url), 'state': 'queued',
         'dir': d, 'created': time.time(), 'started': None, 'ended': None,
         'session_id': str(uuid.uuid4()), 'step': 0, 'label': '', 'runs': 0,
         'auto_resumes': 0, 'removed': False, 'activity': 'waiting in queue'}
    with lock:
        jobs[jid] = j
    save_meta(j)
    return j


def start_job(j, resume=False):
    sid = transcript_sid(j) if resume else None
    if sid:
        j['session_id'] = sid
        prompt, args = resume_prompt_for(j), ['--resume', sid]
    else:
        resume = False
        j['session_id'] = j.get('session_id') or str(uuid.uuid4())
        prompt = prompt_for(j)
        args = ['--session-id', j['session_id']]
    if j.get('note'):
        prompt += (f"\n\nExtra instructions for this reel "
                   f"(they override defaults): {j['note']}")
    cmd = [CLAUDE, prompt, '--dangerously-skip-permissions',
           '--remote-control', f"reel-{j['id']}", *args]
    if j.get('model'):
        cmd += ['--model', j['model']]
    tmux('kill-session', '-t', tname(j['id']))
    env = os.environ.copy()
    tok = get_apify_token()
    if tok:
        env['APIFY_TOKEN'] = tok
    r = subprocess.run([TMUX, 'new-session', '-d', '-s', tname(j['id']),
                        '-x', '220', '-y', '50', '-c', j['dir'], *cmd],
                       capture_output=True, text=True, env=env)
    if tok:
        tmux('set-environment', '-t', tname(j['id']), 'APIFY_TOKEN', tok)
    if r.returncode != 0:
        j['state'] = 'failed'
        j['activity'] = f"tmux failed: {r.stderr.strip()[:120]}"
        j['ended'] = time.time()
    else:
        j['state'] = 'running'
        j['started'] = j['started'] or time.time()
        j['ended'] = None
        j['runs'] = (j.get('runs') or 0) + 1
        j['activity'] = (f"resuming from step {j.get('step') or '?'} of {total_of(j)}"
                         if resume else 'claude session starting')
    _res_cache.pop(j['id'], None)
    save_meta(j)


# ── status.txt protocol ─────────────────────────────────────────────────────
def status_path(j):
    return os.path.join(j['dir'], 'status.txt')


def read_status(j):
    try:
        return open(status_path(j)).read().strip()
    except OSError:
        return ''


def sync_step(j):
    """Recover the filmstrip position from the job's own status.txt."""
    m = re.match(r'(\d+)\s*/\s*\d+\s*\|\s*(.*)', read_status(j))
    if m:
        j['step'], j['label'] = int(m.group(1)), m.group(2)
    return m is not None


def write_status(j, label):
    """Keep the filmstrip where it was while clearing a BLOCKED gate."""
    try:
        with open(status_path(j), 'w') as f:
            f.write(f"{j.get('step') or 0}/{total_of(j)}|{label}")
    except OSError:
        pass


def final_slides(j):
    """Delivered slides for a post job, sorted (empty for reels)."""
    try:
        return sorted(f for f in os.listdir(os.path.join(j['dir'], 'final'))
                      if re.match(r'slide_\d+\.(jpe?g|png)$', f))
    except OSError:
        return []


def pane_tail(jid, lines=14):
    out = tmux('capture-pane', '-p', '-t', tname(jid), capture=True)
    rows = [r.rstrip() for r in out.split('\n') if r.strip()]
    return rows[-lines:]


BOX = re.compile(r'^[\s\u2500-\u257F]*$')       # box-drawing rules / dividers
TIP = re.compile(r'^\s*\u23bf\s*Tip:')          # the hint just above the input box


def pane_activity(rows):
    """The last line that says something — Claude Code's input box, footer and
    tip block are chrome, and on a narrow attached terminal the footer wraps to
    a lone '/rc', which is what used to leave the activity line blank."""
    for i in range(len(rows) - 1, max(-1, len(rows) - 9), -1):
        if TIP.match(rows[i]):
            rows = rows[:i]
            break
    for r in reversed(rows):
        t = r.strip()
        if not t or BOX.match(r) or t.startswith('\u23f5') or t.startswith('\u276f') or t == '/rc':
            continue
        return re.sub(r'\s{2,}', ' ', t)[:160]
    return ''


# ── background loops ────────────────────────────────────────────────────────
def reap_orphans():
    names = tmux('list-sessions', '-F', '#{session_name}', capture=True).split()
    with lock:
        known = {tname(jid) for jid in jobs}
    for n in names:
        if n.startswith('rs_') and n not in known:
            tmux('kill-session', '-t', n)


def monitor():
    """Advance job states from status.txt + tmux liveness; refresh activity."""
    reaped = 0.0
    while True:
        if time.time() - reaped > 60:
            reaped = time.time()
            reap_orphans()
        with lock:
            # 'done' stays watched so idle sessions get auto-closed after 2h
            active = [j for j in jobs.values()
                      if j['state'] in ('running', 'blocked', 'done')]
        for j in active:
            was = j['state']
            live = alive(j['id'])
            status = read_status(j)
            n = total_of(j)
            delivered = os.path.exists(os.path.join(j['dir'], 'final.mp4')) or \
                final_slides(j)
            done = status.startswith(f'{n}/{n}') or bool(delivered)
            state, act = was, j['activity']
            if done:
                state = 'done'
                j['ended'] = j['ended'] or time.time()
                j['step'] = n
                # Idle Claude sessions hold 0.5-1.5GB each; keep one open for
                # follow-ups for 2h after delivery, then reclaim the memory.
                if live and time.time() - j['ended'] > 2 * 3600:
                    tmux('kill-session', '-t', tname(j['id']))
                    act = 'finished — session auto-closed after 2h idle'
                elif live:
                    act = 'finished — session open for follow-ups (auto-closes in 2h)'
                else:
                    act = 'finished'
            elif status.startswith('BLOCKED|'):
                state, act = 'blocked', 'waiting for your answer'
            elif not live:
                j['ended'] = time.time()
                if settings['auto_resume'] and \
                        (j.get('auto_resumes') or 0) < MAX_AUTO_RESUME and \
                        transcript_sid(j):
                    j['auto_resumes'] = (j.get('auto_resumes') or 0) + 1
                    j['_resume'] = j['_force'] = True
                    state = 'queued'
                    act = (f"session dropped — auto-resuming "
                           f"(attempt {j['auto_resumes']} of {MAX_AUTO_RESUME})")
                elif transcript_sid(j):
                    state = 'paused'
                    act = 'session ended early — Resume picks up where it stopped'
                else:
                    state = 'failed'
                    act = 'session ended before it saved any work'
            else:
                rows = pane_tail(j['id'], 14)
                # Fresh job dirs trigger Claude's folder-trust prompt; the panel
                # created these dirs itself, so auto-accept (option 1 is default).
                if any('trust this folder' in r for r in rows):
                    tmux('send-keys', '-t', tname(j['id']), 'Enter')
                    act = 'accepted folder trust prompt'
                else:
                    act = pane_activity(rows) or act
                sync_step(j)
            # Don't clobber a state a request changed while we were working.
            if j['state'] != was:
                continue
            j['state'], j['activity'] = state, act
            snap = (state, act, j['ended'], j['step'])
            if j.get('_snap') != snap:
                j['_snap'] = snap
                save_meta(j)
        time.sleep(2)


def worker():
    while True:
        with lock:
            busy = sum(1 for j in jobs.values() if j['state'] in ('running', 'blocked'))
            # The browser (Brave + ChatGPT tabs) is a single shared resource, so
            # post jobs run one at a time regardless of how many lanes are free.
            post_busy = any(j['state'] in ('running', 'blocked') and
                            j.get('kind') == 'post' for j in jobs.values())
            nxt = None
            if busy < settings['max_concurrent']:
                ready = sorted((j for j in jobs.values() if j['state'] == 'queued'),
                               key=lambda x: (0 if x.get('_force') else 1, x['created']))
                for j in ready:
                    if not (j.get('_force') or not settings['queue_paused']):
                        continue
                    if post_busy and j.get('kind') == 'post':
                        if 'one post at a time' not in j['activity']:
                            j['activity'] = ('queued — one post at a time '
                                             '(the browser is shared)')
                        continue
                    nxt = j
                    break
        if nxt and not os.path.isdir(nxt['dir']):
            nxt['activity'] = 'held — work directory not found'
            nxt = None
        if nxt:
            nxt.pop('_force', None)
            start_job(nxt, resume=bool(nxt.pop('_resume', False)))
        time.sleep(1.5)


# ── job actions ─────────────────────────────────────────────────────────────
def answer_job(j, text):
    write_status(j, 'continuing with your answer')
    tmux('send-keys', '-t', tname(j['id']), '-l', text)
    time.sleep(0.3)
    tmux('send-keys', '-t', tname(j['id']), 'Enter')
    j['state'] = 'running'
    j['activity'] = 'resuming with your answer'
    save_meta(j)


def pause_job(j, why='paused by you'):
    step = j.get('step') or 0
    j['state'] = 'paused'
    j['activity'] = (f"{why} — Resume picks up from step {step} of {total_of(j)}"
                     if step else f"{why} — Resume to continue")
    j['ended'] = j['ended'] or time.time()
    save_meta(j)
    tmux('kill-session', '-t', tname(j['id']))
    _res_cache.pop(j['id'], None)


def resume_job(j):
    if read_status(j).startswith('BLOCKED|'):
        write_status(j, 'resuming')
    j['state'] = 'queued'
    j['_resume'] = j['_force'] = True
    j['auto_resumes'] = 0
    j['ended'] = None
    j['activity'] = ('resuming from where it stopped…' if resumable(j)
                     else 'no saved session — starting this reel fresh')
    save_meta(j)


def restart_job(j):
    tmux('kill-session', '-t', tname(j['id']))
    stamp = int(time.time())
    for name in ('status.txt', 'final.mp4', 'final'):
        p = os.path.join(j['dir'], name)
        if os.path.exists(p):
            try:
                os.rename(p, f"{p}.run{j.get('runs') or 1}.{stamp}")
            except OSError:
                pass
    j.update({'session_id': str(uuid.uuid4()), 'state': 'queued', 'step': 0,
              'label': '', 'started': None, 'ended': None, 'auto_resumes': 0,
              '_resume': False, '_force': True,
              'activity': 'restarting this reel from step 1'})
    _res_cache.pop(j['id'], None)
    save_meta(j)


def stop_job(j, why='stopped by you'):
    tmux('kill-session', '-t', tname(j['id']))
    if j['state'] != 'done':
        j['state'] = 'failed'
        j['activity'] = why
    j['ended'] = j['ended'] or time.time()
    save_meta(j)
    _res_cache.pop(j['id'], None)


def remove_job(j):
    tmux('kill-session', '-t', tname(j['id']))
    j['removed'] = True
    save_meta(j)
    with lock:
        jobs.pop(j['id'], None)
    _res_cache.pop(j['id'], None)


ACTIONS = {'pause': pause_job, 'resume': resume_job, 'restart': restart_job,
           'stop': stop_job, 'cancel': stop_job, 'kill': stop_job,
           'remove': remove_job}


def job_view(j):
    status = read_status(j)
    question = status.split('|', 1)[1] if status.startswith('BLOCKED|') else None
    return {'id': j['id'], 'url': j['url'], 'note': j.get('note', ''),
            'model': j.get('model', ''), 'state': j['state'],
            'kind': j.get('kind') or 'reel', 'total': total_of(j),
            'step': j.get('step') or 0, 'label': j.get('label') or '',
            'question': question if j['state'] == 'blocked' else None,
            'activity': j['activity'], 'created': j['created'],
            'started': j['started'], 'ended': j['ended'],
            'runs': j.get('runs') or 0, 'resumable': resumable(j),
            'session_alive': bool(j['state'] in ('running', 'blocked', 'done')
                                  and alive(j['id'])),
            'has_video': os.path.exists(os.path.join(j['dir'], 'final.mp4')),
            'slides': len(final_slides(j)) if j.get('kind') == 'post' else 0,
            'source_origin': get_source_origin(j)}


def rehydrate_one(root, jid):
    mp = os.path.join(root, jid, 'meta.json')
    if not os.path.exists(mp):
        return None
    try:
        m = json.load(open(mp))
    except ValueError:
        return None
    if m.get('removed'):
        return None
    m['dir'] = os.path.join(root, jid)
    return m


def rehydrate():
    """Re-adopt jobs after a panel restart. Sessions that survived keep running;
    ones whose tmux died become resumable rather than lost."""
    root = jobs_dir()
    if not os.path.isdir(root):
        return
    found = [(root, jid) for jid in sorted(os.listdir(root))]
    for root, jid in found:
        m = rehydrate_one(root, jid)
        if m is None or m['id'] in jobs:
            continue
        m.setdefault('activity', '')
        m.setdefault('step', 0)
        m.setdefault('runs', 0)
        m.setdefault('label', '')
        # Jobs created before kinds existed were all reels — even /p/ URLs, so
        # never re-detect from the URL here; new jobs persist their kind.
        if not m.get('kind'):
            m['kind'] = 'reel'
        m['auto_resumes'] = 0
        sync_step(m)          # the filmstrip survives in the job's status.txt
        if m.get('state') in ('running', 'blocked'):
            if alive(m['id']):
                m['state'] = 'running'      # session survived the panel restart
            elif transcript_sid(m):
                m['state'] = 'paused'
                m['activity'] = ('interrupted by a panel or Mac restart — '
                                 'Resume picks up where it stopped')
            else:
                m['state'] = 'failed'
                m['activity'] = 'interrupted before it saved any work'
        jobs[m['id']] = m


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, ctype, cache=None):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        if cache:
            self.send_header('Cache-Control', cache)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_bytes(open(PANEL_HTML, 'rb').read(), 'text/html; charset=utf-8')
        elif self.path == '/api/ping':
            self.send_json({'ok': True, 'version': VERSION, 'storage': base()})
        elif self.path in ('/api/state', '/api/jobs'):
            with lock:
                snap = sorted(jobs.values(), key=lambda x: -x['created'])
            view = [job_view(j) for j in snap]
            self.send_json(view if self.path == '/api/jobs' else
                           {'jobs': view, 'settings': settings,
                            'apify_configured': bool(get_apify_token()),
                            'disk_free_gb': disk_free_gb(), 'version': VERSION})
        elif self.path == '/api/apify-token':
            tok = get_apify_token()
            masked = (tok[:10] + '••••' + tok[-4:]) if len(tok) > 14 else ('••••' if tok else '')
            self.send_json({'configured': bool(tok), 'masked': masked})
        elif self.path == '/api/research':
            self.send_json(research.get())
        elif self.path.startswith('/api/research/thumb/'):
            p = research.thumb_path(os.path.basename(self.path) + '.jpg')
            if not p or not os.path.exists(p):
                return self.send_json({'error': 'no thumb'}, 404)
            self.send_bytes(open(p, 'rb').read(), 'image/jpeg', 'max-age=86400')
        elif self.path.startswith('/api/jobs/') and self.path.endswith('/pane'):
            self.send_json({'lines': pane_tail(self.path.split('/')[3], 18)})
        elif self.path.startswith('/api/jobs/') and '/slide/' in self.path:
            parts = self.path.split('/')
            j = jobs.get(parts[3])
            names = final_slides(j) if j else []
            try:
                name = names[int(parts[5]) - 1]
            except (IndexError, ValueError):
                return self.send_json({'error': 'no slide'}, 404)
            self.send_bytes(open(os.path.join(j['dir'], 'final', name), 'rb').read(),
                            'image/png' if name.endswith('.png') else 'image/jpeg',
                            'max-age=30')
        elif self.path.startswith('/api/jobs/') and self.path.endswith('/video'):
            jid = self.path.split('/')[3]
            j = jobs.get(jid)
            path = os.path.join(j['dir'], 'final.mp4') if j else ''
            if not os.path.exists(path):
                return self.send_json({'error': 'no video'}, 404)
            size = os.path.getsize(path)
            rng = self.headers.get('Range')
            start, end = 0, size - 1
            if rng:
                m = re.match(r'bytes=(\d*)-(\d*)', rng)
                if m:
                    if m.group(1):
                        start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
            length = end - start + 1
            self.send_response(206 if rng else 200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Accept-Ranges', 'bytes')
            if rng:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.send_header('Content-Length', str(length))
            self.end_headers()
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    remaining -= len(chunk)
        else:
            self.send_json({'error': 'not found'}, 404)

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        try:
            data = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            data = {}
        p = self.path

        if p == '/api/settings':
            for k in DEFAULTS:
                if k in data:
                    settings[k] = data[k]
            settings['max_concurrent'] = max(1, min(6, int(settings['max_concurrent'])))
            save_settings()
            return self.send_json(settings)

        if p == '/api/apify-token':
            tok = (data.get('token') or '').strip()
            save_apify_token(tok)
            masked = (tok[:10] + '••••' + tok[-4:]) if len(tok) > 14 else ('••••' if tok else '')
            return self.send_json({'ok': True, 'configured': bool(tok), 'masked': masked})

        if p == '/api/research/run':
            threading.Thread(target=research.run, args=(new_job,), daemon=True).start()
            return self.send_json({'ok': True})

        if p == '/api/research/act':
            c = research.act(data.get('code', ''), data.get('action', ''), new_job,
                             (data.get('note') or '').strip(),
                             (data.get('model') or '').strip())
            return self.send_json(c or {'error': 'no such candidate'}, 200 if c else 404)

        if p == '/api/jobs':
            entries = data.get('jobs') or [{'url': u} for u in data.get('urls', [])]
            made = [j['id'] for e in entries
                    if e.get('url', '').strip().startswith('http')
                    and (j := new_job(e['url'].strip(), (e.get('note') or '').strip(),
                                      (e.get('model') or '').strip(),
                                      (e.get('kind') or '').strip()))]
            return self.send_json({'created': made})

        if p == '/api/bulk':
            action = data.get('action', '')
            fn = ACTIONS.get(action)
            if not fn:
                return self.send_json({'error': 'bad action'}, 400)
            with lock:
                targets = [j for j in jobs.values() if j['id'] in set(data.get('ids') or [])]
            for j in targets:
                if action == 'resume' and j['state'] in ('running', 'blocked', 'done'):
                    continue
                fn(j)
            return self.send_json({'ok': True, 'count': len(targets)})

        if p.startswith('/api/jobs/'):
            parts = p.split('/')
            jid, action = parts[3], parts[4] if len(parts) > 4 else ''
            j = jobs.get(jid)
            if not j:
                return self.send_json({'error': 'no such job'}, 404)
            if action == 'answer' and j['state'] == 'blocked':
                answer_job(j, data.get('text', ''))
            elif action == 'terminal':
                subprocess.Popen(['osascript', '-e',
                                  f'tell application "Terminal"\nactivate\n'
                                  f'do script "{TMUX} attach -t {tname(jid)}"\nend tell'])
            elif action == 'next':
                with lock:
                    j['created'] = min(x['created'] for x in jobs.values()) - 1
                j['_force'] = True
                j['activity'] = 'moved to the front of the queue'
                save_meta(j)
            elif action == 'reveal':
                target = os.path.join(j['dir'], 'final' if j.get('kind') == 'post'
                                      else 'final.mp4')
                subprocess.Popen(['open', target] if os.path.isdir(target)
                                 else ['open', '-R', target] if os.path.exists(target)
                                 else ['open', j['dir']])
            elif action in ACTIONS:
                ACTIONS[action](j)
            else:
                return self.send_json({'error': 'bad action'}, 400)
            return self.send_json({'ok': True})

        self.send_json({'error': 'not found'}, 404)


if __name__ == '__main__':
    load_settings()
    rehydrate()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=monitor, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
