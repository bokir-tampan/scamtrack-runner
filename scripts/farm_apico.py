#!/usr/bin/env python3
"""farm_apico.py — api.co.id: register (NayTra tempmail) → OTP → generate API key → verify key live."""
import sys, re, time, json
sys.path.insert(0, "/root/.hermes/tools/grok-farm")
import naytra_client as nc
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
BASE = "https://stg-dashboard.api.co.id"
USE  = "https://use.api.co.id"

def meta_token(html):
    m = (re.search(r'name="_token" value="([^"]+)"', html)
         or re.search(r'csrf-token"\s+content="([^"]+)"', html))
    return m.group(1) if m else ""

def all_keys(html):
    return sorted(set(re.findall(r'\b([A-Za-z0-9]{40,64})\b', html)))

def main():
    n = nc.Naytra()
    email = n.create_inbox()
    print("mail:", email, flush=True)
    s = requests.Session(); s.headers.update({"User-Agent": UA})
    t = meta_token(s.get(f"{BASE}/register", timeout=30).text)
    r = s.post(f"{BASE}/register", data={"_token": t, "email": email,
               "password": "Rahasia#2026", "password_confirmation": "Rahasia#2026"},
               allow_redirects=False, timeout=30)
    print("register:", r.status_code, r.headers.get("Location"), flush=True)
    otp = n.wait_otp(email, timeout=90)
    print("otp:", otp, flush=True)
    if otp:
        t = meta_token(s.get(f"{BASE}/register/otp", timeout=30).text)
        r = s.post(f"{BASE}/register/otp", data={"_token": t, "otp": otp},
                   allow_redirects=False, timeout=30)
        print("otp submit:", r.status_code, r.headers.get("Location"), flush=True)
    creds = s.get(f"{BASE}/profile/credentials", timeout=30).text
    before = all_keys(creds)
    t = meta_token(creds)
    r = s.post(f"{BASE}/profile/credentials/rotate", data={"_token": t},
               headers={"Referer": f"{BASE}/profile/credentials"},
               allow_redirects=False, timeout=30)
    print("rotate:", r.status_code, r.headers.get("Location"), flush=True)
    creds2 = s.get(f"{BASE}/profile/credentials", timeout=30).text
    keys = [k for k in all_keys(creds2) if k not in before] or all_keys(creds2)
    m = re.search(r'(?:api[_-]?key|key)["\'>:=\s]{1,12}([A-Za-z0-9]{40,64})', creds2, re.I)
    if m and m.group(1) not in keys:
        keys.insert(0, m.group(1))
    print("keys:", keys, flush=True)
    if keys:
        key = keys[0]
        open("/tmp/apico_key.txt", "w").write(key)
        for probe in [f"{USE}/validation/bank/available",
                      f"{USE}/validation/bank?bank_code=bca&account_number=3010175428"]:
            try:
                pr = requests.get(probe, headers={"x-api-co-id": key}, timeout=25)
                print(f"[probe] {pr.status_code} {pr.text[:200]}", flush=True)
            except Exception as e:
                print("probe err", e, flush=True)
    open("/tmp/apico_acct.json", "w").write(json.dumps(
        {"email": email, "pw": "Rahasia#2026", "key": keys[0] if keys else "", "otp": otp}))

if __name__ == "__main__":
    main()