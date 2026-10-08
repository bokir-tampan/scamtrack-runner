#!/usr/bin/env python3
"""scrapling_cf.py — register api.co.id PROD via scrapling StealthySession.
CF solve OK; submit pakai fetch DI DALAM browser (cf_clearance + csrf). OTP dari NayTra.
"""
import json, os, re, time, random, string

BASE = "https://dashboard.api.co.id"
USE  = "https://use.api.co.id"
PW   = "Rahasia#2026"
NAYTRA_BASE = "https://mail.naytra.net"
NAYTRA_USER = os.environ.get("NAYTRA_USER", "asu22")
NAYTRA_PW   = os.environ.get("NAYTRA_PW", "Germand26")

INPAGE_POST = """async ({o, body}) => {
  const r = await fetch(o, {method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest'},
    body: new URLSearchParams(body), redirect:'follow'});
  return {status: r.status, url: r.url, text: (await r.text()).slice(0,300)};
}"""


def naytra():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"})
    s.get(f"{NAYTRA_BASE}/login", timeout=30)
    s.post(f"{NAYTRA_BASE}/login", data={"username": NAYTRA_USER, "password": NAYTRA_PW}, timeout=30)
    d = s.get(f"{NAYTRA_BASE}/api/generate", timeout=40).json()
    addr = d.get("address") or d.get("email")
    s.post(f"{NAYTRA_BASE}/api/saved", json={"address": addr}, timeout=25)
    return s, addr


def _extract_code(blob):
    t = re.sub(r'<[^>]+>', ' ', blob or '')
    t = re.sub(r'\s+', ' ', t)
    for pat in [r'(?i)registration[^0-9]{0,30}(\d{4,8})',
                r'(?i)verification[^0-9]{0,30}(\d{4,8})',
                r'(?i)\botp\b[^0-9]{0,15}[:：]?\s*(\d{4,8})',
                r'(?i)\bcode\b[^0-9]{0,15}[:：]?\s*(\d{4,8})']:
        m = re.search(pat, t)
        if m:
            return m.group(1)
    m = re.search(r'(?<!\d)(\d{6})(?!\d)', t)
    return m.group(1) if m else None


def wait_otp(s, addr, timeout=150):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = s.get(f"{NAYTRA_BASE}/api/inbox/{addr}", timeout=40).json()
        for e in d.get("emails") or []:
            blob = e.get("subject", "") or ""
            if e.get("id") is not None:
                ed = s.get(f"{NAYTRA_BASE}/api/email/{e['id']}", timeout=40).json()
                blob += " " + (ed.get("body_text") or "") + " " + (ed.get("body_html") or "") + " " + (ed.get("body") or "")
            code = _extract_code(blob)
            if code:
                return code
        time.sleep(5)
    return None


def main():
    from scrapling.fetchers import StealthySession
    import requests
    out = {"status": "failed"}
    ns, email = naytra()
    out["email"] = email
    print("mail:", email, flush=True)

    with StealthySession(headless=True, solve_cloudflare=True) as sess:
        # 1) register
        def do_register(page):
            page.fill('input[name="email"]', email)
            page.fill('input[name="password"]', PW)
            page.fill('input[name="password_confirmation"]', PW)
            page.click('button[type="submit"], input[type="submit"], form button')
            try:
                page.wait_for_load_state("networkidle", timeout=45000)
            except Exception:
                pass
            return page
        p1 = sess.fetch(f"{BASE}/register", page_action=do_register, network_idle=True)
        print("after register:", getattr(p1, "url", "?"), flush=True)

        otp = wait_otp(ns, email, timeout=150)
        print("otp:", otp, flush=True)
        out["otp"] = otp

        # 2) submit OTP via in-page fetch
        def do_otp(page):
            if "/register/otp" not in page.url:
                page.goto(f"{BASE}/register/otp")
            page.wait_for_selector('input[name="otp"]', timeout=60000)
            tok = page.eval_on_selector('input[name="_token"]', "e=>e.value")
            res = page.evaluate(INPAGE_POST, {"o": f"{BASE}/register/otp",
                                              "body": {"_token": tok, "otp": otp}})
            print("otp post:", res, flush=True)
            page.goto(f"{BASE}/login")
            return page
        p2 = sess.fetch(f"{BASE}/register/otp", page_action=do_otp, network_idle=True)
        print("after otp url:", getattr(p2, "url", "?"), flush=True)
        out["after_otp_url"] = getattr(p2, "url", "")

        # 2b) LOGIN (email + password) sampai masuk dashboard
        def do_login(page):
            if "/login" not in page.url:
                page.goto(f"{BASE}/login")
            page.wait_for_selector('input[name="email"]', timeout=60000)
            try:
                tok = page.eval_on_selector('input[name="_token"]', "e=>e.value")
            except Exception:
                tok = ""
            res = page.evaluate(INPAGE_POST, {"o": f"{BASE}/login",
                                              "body": {"_token": tok, "email": email, "password": PW}})
            print("login post:", res, flush=True)
            page.goto(f"{BASE}/profile/credentials")
            return page
        p2b = sess.fetch(f"{BASE}/login", page_action=do_login, network_idle=True)
        print("after login url:", getattr(p2b, "url", "?"), flush=True)
        out["after_login_url"] = getattr(p2b, "url", "")

        # 3) credentials + rotate via in-page fetch
        def do_creds(page):
            if "/profile/credentials" not in page.url:
                page.goto(f"{BASE}/profile/credentials")
            try:
                page.wait_for_selector('form[action*="credentials/rotate"]', timeout=60000)
            except Exception:
                pass
            try:
                tok = page.eval_on_selector('meta[name="csrf-token"]', "e=>e.content")
            except Exception:
                try:
                    tok = page.eval_on_selector('input[name="_token"]', "e=>e.value")
                except Exception:
                    tok = ""
            print("creds url:", page.url, "token?", bool(tok), flush=True)
            res = page.evaluate(INPAGE_POST, {"o": f"{BASE}/profile/credentials/rotate",
                                              "body": {"_token": tok}})
            print("rotate post:", res, flush=True)
            page.goto(f"{BASE}/profile/credentials")
            return page
        p3 = sess.fetch(f"{BASE}/profile/credentials", page_action=do_creds, network_idle=True)
        html = getattr(p3, "html_content", "") or str(p3)
        cands = sorted(set(re.findall(r'\b([A-Za-z0-9]{40,64})\b', html)))
        out["candidates"] = cands
        print("candidates:", cands[:8], flush=True)

        # 3b) dump info produk + saldo untuk tahu jalur gratis
        def dump_info(page):
            return page
        for _p, _name in [(f"{BASE}/products", "products"), (f"{BASE}/profile/balance", "balance"),
                          (f"{BASE}/dashboard/subscriptions", "subs")]:
            try:
                _pg = sess.fetch(_p, page_action=dump_info, network_idle=True)
                _h = getattr(_pg, "html_content", "") or ""
                import re as _re
                _t = _re.sub(r'\s+', ' ', _re.sub(r'<[^>]+>', ' ', _h))
                out[_name] = _t[:1500]
                print(f"[{_name}]", _t[:400], flush=True)
            except Exception as _e:
                print(f"[{_name}] err", _e, flush=True)

        # 4) verify
        for k in cands:
            try:
                r = requests.get(f"{USE}/api/bank-validation",
                                 params={"bank_code": "bca", "account_number": "3010175428"},
                                 headers={"x-api-co-id": k}, timeout=25)
                print(f"[verify {k[:8]}] {r.status_code} {r.text[:120]}", flush=True)
                if "Invalid API key" not in r.text and r.status_code != 401:
                    out.update({"status": "success", "key": k, "verify": r.text[:300]}); break
            except Exception as e:
                print("verify err", e, flush=True)

    json.dump(out, open("result.json", "w"), indent=1)
    print("RESULT:", json.dumps(out)[:600], flush=True)


if __name__ == "__main__":
    main()
