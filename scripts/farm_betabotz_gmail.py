#!/usr/bin/env python3
"""farm_betabotz_gmail.py — daftar betabotz pakai Gmail dot-alias (betabotz whitelist GMAIL only),
auto-verifikasi lewat IMAP, ambil apikey.

Butuh App Password Gmail (bukan password login):
  env BETABOTZ_GMAIL=emailmu@gmail.com  BETABOTZ_GMAIL_PW="xxxx xxxx xxxx xxxx"
Satu Gmail -> tak terbatas alias (titik diabaikan Gmail, betabotz lihat unik).
"""
import os, re, sys, ssl, time, random, string, imaplib, email as emailmod, urllib.parse, urllib.request, http.cookiejar

GMAIL = os.environ.get("BETABOTZ_GMAIL", "").strip()
GMAIL_PW = os.environ.get("BETABOTZ_GMAIL_PW", "").strip()
BASE = "https://api.betabotz.eu.org"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def dotted_alias(base_local):
    """sisip titik acak -> alias unik yang tetap nyampe ke inbox."""
    n = len(base_local)
    if n < 5:
        return f"{base_local}{random.randint(100,999)}"
    for _ in range(200):
        positions = sorted(random.sample(range(1, n), k=random.randint(1, min(3, n-1))))
        local = "".join(c + ("." if (i+1) in positions else "") for i, c in enumerate(base_local))
        if not re.search(r'\.\.|^\.|\.$', local):
            return local
    return base_local + str(random.randint(100,999))

def _req(opener, url, data=None, headers=None, method=None):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    resp = opener.open(r, timeout=30)
    return resp.read().decode("utf-8", "replace")

def imap_wait_link(user_alias, addr, timeout=150):
    """baca inbox Gmail (INBOX+Spam), cari email ke addr persis, ambil link verifikasi."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            M.login(GMAIL, GMAIL_PW)
            for box in ('INBOX', '"[Gmail]/Spam"'):
                try:
                    M.select(box)
                except Exception:
                    continue
                typ, data = M.search(None, f'(TO "{addr}")')
                for num in (data[0].split() if data and data[0] else []):
                    typ, msg = M.fetch(num, "(RFC822)")
                    raw = msg[0][1]
                    m = emailmod.message_from_bytes(raw)
                    body = ""
                    if m.is_multipart():
                        for p in m.walk():
                            body += (p.get_payload(decode=True) or b"").decode("utf-8", "replace")
                    else:
                        body = (m.get_payload(decode=True) or b"").decode("utf-8", "replace")
                    blob = f"{m.get('Subject','')}\n{body}"
                    for u in re.findall(r'https?://[^\s"\'<>()]+', blob):
                        if re.search(r'verif|activ|confirm|token|/users/', u, re.I):
                            M.logout()
                            return u.rstrip('\\')
            M.logout()
        except Exception as e:
            print("imap:", e, flush=True)
        time.sleep(6)
    return None

def main():
    if not GMAIL or not GMAIL_PW:
        print("SET BETABOTZ_GMAIL + BETABOTZ_GMAIL_PW (Gmail App Password)"); return
    local, dom = GMAIL.split("@")
    alias = dotted_alias(local)
    email = f"{alias}@{dom}"
    uname = "osint" + ''.join(random.choices(string.ascii_lowercase, k=6))
    nomor = "+62812%07d" % random.randint(0, 9999999)
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    print("alias:", email, flush=True)
    resp = _req(op, f"{BASE}/users/register", {"email": email, "username": uname, "nomor": nomor,
                 "password": "Rahasia#2026", "confirmPassword": "Rahasia#2026"},
                {"X-Requested-With": "XMLHttpRequest", "Origin": BASE, "Referer": f"{BASE}/users/register"})
    print("register:", resp[:120].replace("\n", " "), flush=True)
    link = imap_wait_link(alias, email)
    print("verify link:", link, flush=True)
    if link:
        try:
            _req(op, link, headers={"Accept": "text/html"})
        except Exception as e:
            print("verify err:", e)
    for path in ["/users/profile", "/users/dashboard", "/"]:
        try:
            p = _req(op, BASE + path)
            k = re.findall(r'(?:apikey|api[_ ]?key)["\'>:=\s]{1,8}([A-Za-z0-9]{8,40})', p, re.I)
            print(f"[{path}] keys={k[:3]}", flush=True)
            if k:
                open("/root/.hermes/tools/scamtrack/.betabotz_key", "w").write(k[0]); break
        except Exception as e:
            print(f"[{path}] err {e}")

if __name__ == "__main__":
    main()
