#!/usr/bin/env python3
"""scrapling_cf.py — StealthyFetcher solve Cloudflare pada dashboard.api.co.id/register,
lalu (kalau tembus) jalankan flow register+OTP+generate key. Output result.json.
"""
import json, os, re, sys, time, random, string

BASE = "https://dashboard.api.co.id"
USE  = "https://use.api.co.id"
PW   = "Rahasia#2026"
NAYTRA_BASE = "https://mail.naytra.net"
NAYTRA_USER = os.environ.get("NAYTRA_USER", "asu22")
NAYTRA_PW   = os.environ.get("NAYTRA_PW", "Germand26")


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


def wait_otp(s, addr, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = s.get(f"{NAYTRA_BASE}/api/inbox/{addr}", timeout=40).json()
        for e in d.get("emails") or []:
            blob = e.get("subject", "") or ""
            if e.get("id") is not None:
                ed = s.get(f"{NAYTRA_BASE}/api/email/{e['id']}", timeout=40).json()
                blob += " " + (ed.get("body") or "") + " " + (ed.get("body_html") or "")
            m = re.search(r'(?<!\d)(\d{6})(?!\d)', blob)
            if m:
                return m.group(1)
        time.sleep(5)
    return None


def main():
    out = {"status": "failed"}
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception as e:
        print("scrapling import fail:", e); json.dump(out, open("result.json", "w")); return

    ns, email = naytra()
    out["email"] = email
    print("mail:", email, flush=True)

    p = StealthyFetcher.fetch(f"{BASE}/register", headless=True,
                              solve_cloudflare=True, network_idle=True, timeout=120000)
    html = getattr(p, "html_content", "") or str(p)
    out["register_cf"] = "Just a moment" in html
    out["register_has_form"] = 'name="email"' in html
    print("register status:", getattr(p, "status", "?"), "CF:", out["register_cf"],
          "form:", out["register_has_form"], "len:", len(html), flush=True)
    if out["register_cf"]:
        json.dump(out, open("result.json", "w"), indent=1)
        print("RESULT:", json.dumps(out)[:400]); return

    # submit register via plain HTTP using cookies from stealth session
    import requests
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"})
    try:
        for c in p.cookies:
            sess.cookies.set(c["name"], c["value"], domain=c.get("domain"))
    except Exception:
        pass
    tok = re.search(r'name="_token" value="([^"]+)"', html)
    tok = tok.group(1) if tok else ""
    r = sess.post(f"{BASE}/register", data={"_token": tok, "email": email,
                  "password": PW, "password_confirmation": PW}, allow_redirects=False, timeout=30)
    print("submit:", r.status_code, r.headers.get("Location"), flush=True)
    otp = wait_otp(ns, email, timeout=120)
    print("otp:", otp, flush=True)
    out["otp"] = otp
    if otp:
        # OTP page may also be CF; use stealth again carrying sess cookies
        p2 = StealthyFetcher.fetch(f"{BASE}/register/otp", headless=True, solve_cloudflare=True, network_idle=True, timeout=120000)
        h2 = getattr(p2, "html_content", "")
        t2 = re.search(r'name="_token" value="([^"]+)"', h2)
        r2 = sess.post(f"{BASE}/register/otp", data={"_token": (t2.group(1) if t2 else ""), "otp": otp},
                       allow_redirects=False, timeout=30)
        print("otp submit:", r2.status_code, r2.headers.get("Location"), flush=True)
        # generate key
        p3 = StealthyFetcher.fetch(f"{BASE}/profile/credentials", headless=True, solve_cloudflare=True, network_idle=True, timeout=120000)
        h3 = getattr(p3, "html_content", "")
        before = set(re.findall(r'\b([A-Za-z0-9]{40,64})\b', h3))
        t3 = re.search(r'csrf-token"\s+content="([^"]+)"', h3)
        r3 = sess.post(f"{BASE}/profile/credentials/rotate", data={"_token": (t3.group(1) if t3 else "")},
                       headers={"Referer": f"{BASE}/profile/credentials"}, allow_redirects=False, timeout=30)
        p4 = StealthyFetcher.fetch(f"{BASE}/profile/credentials", headless=True, solve_cloudflare=True, network_idle=True, timeout=120000)
        h4 = getattr(p4, "html_content", "")
        cands = [k for k in set(re.findall(r'\b([A-Za-z0-9]{40,64})\b', h4)) if k not in before]
        out["candidates"] = cands
        for k in cands:
            try:
                pr = requests.get(f"{USE}/api/bank-validation",
                                  params={"bank_code": "bca", "account_number": "3010175428"},
                                  headers={"x-api-co-id": k}, timeout=25)
                print(f"[verify {k[:8]}] {pr.status_code} {pr.text[:120]}", flush=True)
                if "Invalid API key" not in pr.text:
                    out.update({"status": "success", "key": k, "verify": pr.text[:300]}); break
            except Exception as e:
                print("verify err", e)
    json.dump(out, open("result.json", "w"), indent=1)
    print("RESULT:", json.dumps(out)[:500], flush=True)


if __name__ == "__main__":
    main()
