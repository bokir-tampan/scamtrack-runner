#!/usr/bin/env python3
"""apico_register.py — register api.co.id PROD (dashboard.api.co.id, Cloudflare) via camoufox,
OTP email dari NayTra tempmail, generate API key, VERIFIKASI ke https://use.api.co.id/api/bank-validation.

Output -> result.json
"""
import json, os, re, sys, time, random, string

BASE = "https://dashboard.api.co.id"
USE  = "https://use.api.co.id"
PW   = "Rahasia#2026"

# ── NayTra tempmail (HTTP, dari client grok-farm) ───────────────────────────
NAYTRA_BASE = "https://mail.naytra.net"
NAYTRA_USER = os.environ.get("NAYTRA_USER", "asu22")
NAYTRA_PW   = os.environ.get("NAYTRA_PW", "Germand26")

def _naytra_session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"})
    s.get(f"{NAYTRA_BASE}/login", timeout=30)
    s.post(f"{NAYTRA_BASE}/login", data={"username": NAYTRA_USER, "password": NAYTRA_PW}, timeout=30)
    return s

def naytra_new_inbox():
    s = _naytra_session()
    d = s.get(f"{NAYTRA_BASE}/api/generate", timeout=40).json()
    addr = d.get("address") or d.get("email")
    s.post(f"{NAYTRA_BASE}/api/saved", json={"address": addr}, timeout=25)
    return s, addr

def naytra_wait_otp(s, addr, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = s.get(f"{NAYTRA_BASE}/api/inbox/{addr}", timeout=40).json()
        for e in d.get("emails") or []:
            subj = e.get("subject", "") or ""
            blob = subj
            if e.get("id") is not None:
                ed = s.get(f"{NAYTRA_BASE}/api/email/{e['id']}", timeout=40).json()
                blob += " " + (ed.get("body") or "") + " " + (ed.get("body_html") or "")
            m = re.search(r'(?<!\d)(\d{6})(?!\d)', blob)
            if m:
                return m.group(1)
        time.sleep(5)
    return None

# ── camoufox flow ───────────────────────────────────────────────────────────
def meta_token(html):
    m = re.search(r'name="_token" value="([^"]+)"', html) or re.search(r'csrf-token"\s+content="([^"]+)"', html)
    return m.group(1) if m else ""

def main():
    out = {"status": "failed"}
    import requests
    ns, email = naytra_new_inbox()
    out["email"] = email
    print("mail:", email, flush=True)

    from camoufox.sync_api import Camoufox
    opts = dict(headless="virtual", humanize=True, geoip=True,
                os=["windows"], locale="en-US")
    with Camoufox(**opts) as browser:
        page = browser.new_page()
        page.goto(f"{BASE}/register", wait_until="domcontentloaded", timeout=90000)
        # tunggu CF clear + form muncul
        try:
            page.wait_for_selector('input[name="email"]', timeout=90000)
            print("register form appeared", flush=True)
        except Exception as e:
            print("form wait:", e, "url:", page.url, "title:", page.title(), flush=True)
            try:
                page.screenshot(path="cf_debug.png")
                open("cf_debug.html", "w").write(page.content())
            except Exception:
                pass
        html = page.content()
        tok = meta_token(html)
        page.fill('input[name="email"]', email)
        page.fill('input[name="password"]', PW)
        page.fill('input[name="password_confirmation"]', PW)
        page.eval_on_selector('form', "f=>f.submit()")
        page.wait_for_load_state("networkidle", timeout=60000)
        print("after register url:", page.url, flush=True)

        otp = naytra_wait_otp(ns, email, timeout=120)
        print("otp:", otp, flush=True)
        out["otp"] = otp
        if otp:
            # halaman OTP
            if "/register/otp" not in page.url:
                page.goto(f"{BASE}/register/otp", wait_until="networkidle", timeout=60000)
            page.fill('input[name="otp"]', otp)
            page.eval_on_selector('form', "f=>f.submit()")
            page.wait_for_load_state("networkidle", timeout=60000)
            print("after otp url:", page.url, flush=True)

        # generate key
        page.goto(f"{BASE}/profile/credentials", wait_until="networkidle", timeout=60000)
        body = page.content()
        before = set(re.findall(r'\b([A-Za-z0-9]{40,64})\b', body))
        # submit rotate form
        try:
            page.eval_on_selector('form[action*="credentials/rotate"]', "f=>f.submit()")
            page.wait_for_load_state("networkidle", timeout=60000)
        except Exception as e:
            print("rotate submit err:", e, flush=True)
        page.goto(f"{BASE}/profile/credentials", wait_until="networkidle", timeout=60000)
        after = set(re.findall(r'\b([A-Za-z0-9]{40,64})\b', page.content()))
        cands = [c for c in after if c not in before] + list(after)
        out["candidates"] = cands
        print("candidates:", cands[:8], flush=True)

        # verify each candidate against prod API
        for k in cands:
            try:
                r = requests.get(f"{USE}/api/bank-validation",
                                 params={"bank_code": "bca", "account_number": "3010175428"},
                                 headers={"x-api-co-id": k}, timeout=25)
                print(f"[verify {k[:8]}..] {r.status_code} {r.text[:140]}", flush=True)
                if r.status_code == 200 and ("is_success" not in r.text or "true" in r.text.lower()):
                    out.update({"status": "success", "key": k, "verify": r.text[:400]})
                    break
                if "Invalid API key" not in r.text:
                    out.update({"status": "success", "key": k, "verify": r.text[:400]})
                    break
            except Exception as e:
                print("verify err", e, flush=True)

    json.dump(out, open("result.json", "w"), indent=1)
    print("RESULT:", json.dumps(out)[:500], flush=True)

if __name__ == "__main__":
    main()
