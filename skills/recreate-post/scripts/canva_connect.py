#!/usr/bin/env python
"""Canva Connect API client — the Canva step without the browser or per-page MCP calls.

One-time setup (~5 min at https://www.canva.com/developers/integrations):
  1. Create an integration ("LM recreate-post"), add scopes
       design:content:write  design:content:read  design:meta:read  asset:write  asset:read
  2. Add redirect URL  http://127.0.0.1:3001/oauth/redirect
  3. Put the client id + secret in ~/.claude/skills/recreate-post/canva_app.json:
       {"client_id": "...", "client_secret": "..."}
  4. Run:  canva_connect.py auth        (opens Brave once; token is cached + auto-refreshed)

Then per post (from the job/work dir):
  canva_connect.py build "LM Post - HEADLINE" gen/*.png
      → builds a 1080x1350 multi-page PDF, imports it as a new Canva design
        (one page per render), exports every page as JPG (quality 100, pro),
        downloads them untouched to post/slide_NN.jpg, prints the design URL.
  canva_connect.py export DESIGN_ID            (re-export an existing design)

Everything is sequential HTTP; a 20-slide post takes ~30-60 s total.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "canva_app.json")
TOKEN = os.path.join(HERE, "..", "canva_token.json")
API = "https://api.canva.com/rest/v1"
REDIRECT = "http://127.0.0.1:3001/oauth/redirect"
SCOPES = "design:content:write design:content:read design:meta:read asset:write asset:read"


# ---------------------------------------------------------------- http helpers
def _req(method, url, headers=None, data=None, timeout=120):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"{method} {url} → HTTP {e.code}: {body[:500]}")


def app():
    if not os.path.exists(APP):
        raise SystemExit(f"missing {os.path.normpath(APP)} — see the setup notes at the top of this file")
    return json.load(open(APP))


def _basic():
    a = app()
    return "Basic " + base64.b64encode(f"{a['client_id']}:{a['client_secret']}".encode()).decode()


def _token_request(form):
    st, tok = _req("POST", f"{API}/oauth/token",
                   {"Authorization": _basic(), "Content-Type": "application/x-www-form-urlencoded"},
                   urllib.parse.urlencode(form).encode())
    tok["obtained_at"] = int(time.time())
    json.dump(tok, open(TOKEN, "w"), indent=1)
    os.chmod(TOKEN, 0o600)
    return tok


def bearer():
    """Cached access token, refreshed when within 2 minutes of expiry."""
    if not os.path.exists(TOKEN):
        raise SystemExit("not authorised yet — run: canva_connect.py auth")
    tok = json.load(open(TOKEN))
    if time.time() > tok["obtained_at"] + tok.get("expires_in", 14400) - 120:
        tok = _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    return {"Authorization": f"Bearer {tok['access_token']}"}


# ---------------------------------------------------------------------- auth
def cmd_auth():
    a = app()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = "https://www.canva.com/api/oauth/authorize?" + urllib.parse.urlencode({
        "code_challenge": challenge, "code_challenge_method": "s256", "scope": SCOPES,
        "response_type": "code", "client_id": a["client_id"], "state": state, "redirect_uri": REDIRECT})
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Canva authorised - you can close this tab.")

        def log_message(self, *x):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 3001), H)
    if os.environ.get("CANVA_NO_BROWSER"):
        print("CONSENT_URL", url, flush=True)
    else:
        print("opening Canva consent page…", flush=True)
        webbrowser.open(url)
    while "code" not in got:
        srv.handle_request()
    if got.get("state") != state:
        raise SystemExit("state mismatch — retry auth")
    _token_request({"grant_type": "authorization_code", "code_verifier": verifier,
                    "code": got["code"], "redirect_uri": REDIRECT})
    st, d = _req("GET", f"{API}/designs?limit=1", bearer())
    print("authorised — API reachable, designs visible:", len(d.get("items", [])), "→", os.path.normpath(TOKEN))


# --------------------------------------------------------------------- build
def _write_pdf_lossless(ims, out):
    """Dependency-free PDF: one FlateDecode RGB image per 1080x1350 page (no re-encoding)."""
    import zlib
    objs = []

    def add(b):
        objs.append(b)
        return len(objs)

    add(b"")                                            # obj 1: /Pages, filled below
    pages = []
    for im in ims:
        raw = zlib.compress(im.tobytes(), 6)
        img = add(b"<< /Type /XObject /Subtype /Image /Width 1080 /Height 1350 /ColorSpace /DeviceRGB "
                  b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % len(raw) + raw + b"\nendstream")
        content = b"q 1080 0 0 1350 0 0 cm /Im Do Q"
        cs = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        pages.append(add(b"<< /Type /Page /Parent 1 0 R /MediaBox [0 0 1080 1350] /Resources << /XObject << /Im %d 0 R >> >> "
                         b"/Contents %d 0 R >>" % (img, cs)))
    objs[0] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % p for p in pages), len(pages))
    cat = add(b"<< /Type /Catalog /Pages 1 0 R >>")
    with open(out, "wb") as f:
        f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offs = []
        for i, o in enumerate(objs, 1):
            offs.append(f.tell())
            f.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
        x = f.tell()
        f.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
        for o in offs:
            f.write(b"%010d 00000 n \n" % o)
        f.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, x))


def build_pdf(pngs, out="gen/post.pdf", max_bytes=60_000_000):
    ims = []
    for p in pngs:
        im = Image.open(p).convert("RGB")
        if im.size != (1080, 1350):
            im = im.resize((1080, 1350), Image.LANCZOS)
        ims.append(im)
    _write_pdf_lossless(ims, out)
    if os.path.getsize(out) > max_bytes:                # very long carousel: fall back to JPEG q95 pages
        ims[0].save(out, "PDF", save_all=True, append_images=ims[1:], resolution=72.0, quality=95)
    return out


def poll(url, key, tries=90):
    for _ in range(tries):
        st, j = _req("GET", url, bearer())
        job = j.get("job", {})
        if job.get("status") == "success":
            return job
        if job.get("status") == "failed":
            raise SystemExit(f"{key} failed: {json.dumps(job.get('error'))}")
        time.sleep(2)
    raise SystemExit(f"{key} timed out")


def import_pdf(pdf, title):
    meta = json.dumps({"title_base64": base64.b64encode(title.encode()).decode(), "mime_type": "application/pdf"})
    h = {**bearer(), "Content-Type": "application/octet-stream", "Import-Metadata": meta}
    st, j = _req("POST", f"{API}/imports", h, open(pdf, "rb").read(), timeout=300)
    job = poll(f"{API}/imports/{j['job']['id']}", "import")
    d = job["result"]["designs"][0]
    return d["id"], d.get("urls", {}).get("edit_url", "")


def export_jpg(design_id):
    body = json.dumps({"design_id": design_id,
                       "format": {"type": "jpg", "quality": 100, "export_quality": "pro",
                                  "width": 1080, "height": 1350}}).encode()   # PDF pts import at 4/3 scale otherwise
    st, j = _req("POST", f"{API}/exports", {**bearer(), "Content-Type": "application/json"}, body)
    job = poll(f"{API}/exports/{j['job']['id']}", "export")
    return job["urls"]


def download(urls):
    os.makedirs("post", exist_ok=True)
    out = []
    for i, u in enumerate(urls, 1):
        p = f"post/slide_{i:02d}.jpg"
        with urllib.request.urlopen(u, timeout=120) as r, open(p, "wb") as f:
            f.write(r.read())
        im = Image.open(p)
        print(f"{p}: {os.path.getsize(p)} bytes {im.size[0]}x{im.size[1]}")
        out.append(p)
    return out


def cmd_build(title, pngs):
    pngs = sorted(pngs)
    pdf = build_pdf(pngs)
    print(f"pdf: {pdf} ({len(pngs)} pages)")
    design_id, edit_url = import_pdf(pdf, title)
    print(f"design: {design_id} {edit_url}")
    urls = export_jpg(design_id)
    files = download(urls)
    if os.path.exists("status.txt"):
        open("status.txt", "w").write(f"5/6|exported {len(files)} slides from Canva")
    print(f"CANVA-OK {design_id} {len(files)} slides")


def cmd_export(design_id):
    download(export_jpg(design_id))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "auth":
        cmd_auth()
    elif args[0] == "build" and len(args) >= 3:
        cmd_build(args[1], args[2:])
    elif args[0] == "export" and len(args) == 2:
        cmd_export(args[1])
    else:
        sys.exit(__doc__)
