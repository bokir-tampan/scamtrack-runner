#!/usr/bin/env python3
"""scamtrack GH-Action lookup runner.

Input: /tmp/inp.json  {provider, action, arg1, arg2, arg3, use_proxy}
Output: result.json  — selalu JSON.

Provider:
  rfpdev      — rekening/ewallet/nik (gratis, tanpa key)  [tanpa captcha]
  kpu         — DPT KPU (butuh token reCAPTCHA arg2)
  cekrekening — blacklist resmi Komdigi (Cloudflare Turnstile)
  generic     — ambil URL (arg1) via browser, dump HTML/text

Captcha:
  * Turnstile/reCAPTCHA: kalau ada CAPTCHA_KEY + CAPTCHA_PROVIDER -> solve via API.
    Ada NOPECHA_KEY -> pakai nopecha (browser extension / API).
  * Kalau tidak ada key: fallback ke interaksi manual tak mungkin di CI -> tulis
    needs_solver:true + screenshot + halaman, biar operator selesaikan.
"""
import json, os, sys, time
import urllib.parse as up

INP = json.load(open("/tmp/inp.json")) if os.path.exists("/tmp/inp.json") else {}
PROV = (INP.get("provider") or "rfpdev").lower()
ACT = (INP.get("action") or "").lower()
A1, A2, A3 = INP.get("arg1", ""), INP.get("arg2", ""), INP.get("arg3", "")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def out(d):
    json.dump(d, open("result.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(d, ensure_ascii=False)[:4000])


def requests_():
    import requests
    return requests


def proxies():
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    return {"http": p, "https": p} if p else None


# ---------- rfpdev (no captcha) ----------
def rfpdev():
    r = requests_()
    base = "https://rfpdev.me"
    if ACT in ("rekening", "bank"):
        body = {"account_number": A2 or A1, "bank_code": A1 if A2 else A1}
        body = {"account_number": A2, "bank_code": A1}
        u, b = base + "/api/check-rekening", body
    elif ACT in ("ewallet", "wallet"):
        u, b = base + "/api/check-ewallet", {"phone_number": A2, "ewallet_code": A1}
    elif ACT == "nik":
        u, b = base + "/api/check-nik", {"nik": A1}
    else:
        u, b = base + "/api/check-leaks", {"search": A1}
    rr = r.post(u, json=b, headers={"Accept": "application/json"}, timeout=30, proxies=proxies())
    return {"provider": "rfpdev", "url": u, "sent": b, "code": rr.status_code, "json": _j(rr)}


# ---------- generic browser ----------
def generic():
    from playwright.sync_api import sync_playwright
    url = A1
    wait = int(A3 or 8)
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True, proxy=_pw_proxy())
        pg = br.new_page(user_agent=UA)
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(wait * 1000)
        html = pg.content()
        shot = "page.png"
        pg.screenshot(path=shot, full_page=True)
        turnstile = "challenges.cloudflare.com" in html or "turnstile" in html.lower()
        recaptcha = "recaptcha" in html.lower()
        body = pg.inner_text("body")[:5000]
        br.close()
    return {"provider": "generic", "url": url, "turnstile": turnstile,
            "recaptcha": recaptcha, "text": body, "screenshot": shot}


def _pw_proxy():
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not p:
        return None
    u = up.urlparse(p)
    return {"server": f"{u.scheme}://{u.hostname}:{u.port}",
            "username": u.username, "password": u.password}


# ---------- captcha solving ----------
def solve_turnstile(sitekey, pageurl):
    key = os.environ.get("CAPTCHA_KEY")
    prov = (os.environ.get("CAPTCHA_PROVIDER") or "").lower()
    if key and prov in ("2captcha", "anticaptcha", "capsolver"):
        return _api_captcha(prov, key, sitekey, pageurl)
    nope = os.environ.get("NOPECHA_KEY")
    if nope:
        return _nopecha(nope, sitekey, pageurl)
    return {"error": "no solver key (set CAPTCHA_KEY/NOPECHA_KEY)"}


def _api_captcha(prov, key, sitekey, pageurl):
    r = requests_()
    if prov == "2captcha":
        rr = r.post("https://2captcha.com/in.php", data={
            "key": key, "method": "turnstile", "sitekey": sitekey,
            "pageurl": pageurl, "json": 1}).json()
        if rr.get("status") != 1:
            return {"error": rr}
        cid = rr["request"]
        for _ in range(40):
            time.sleep(5)
            g = r.get("https://2captcha.com/res.php", params={
                "key": key, "action": "get", "id": cid, "json": 1}).json()
            if g.get("status") == 1:
                return {"token": g["request"]}
            if g.get("request") not in ("CAPCHA_NOT_READY",):
                return {"error": g}
        return {"error": "timeout"}
    if prov == "capsolver":
        rr = r.post("https://api.capsolver.com/createTask", json={
            "clientKey": key, "task": {"type": "AntiTurnstileTaskProxyLess",
            "websiteURL": pageurl, "websiteKey": sitekey}}).json()
        tid = rr.get("taskId")
        for _ in range(40):
            time.sleep(5)
            g = r.post("https://api.capsolver.com/getTaskResult",
                       json={"clientKey": key, "taskId": tid}).json()
            if g.get("status") == "ready":
                return {"token": g["solution"].get("token")}
            if g.get("status") == "failed":
                return {"error": g}
        return {"error": "timeout"}
    return {"error": f"provider {prov} not implemented"}


def _nopecha(key, sitekey, pageurl):
    r = requests_()
    rr = r.post("https://api.nopecha.com/token", json={
        "key": key, "type": "turnstile", "sitekey": sitekey, "url": pageurl}).json()
    for _ in range(40):
        data = rr.get("data")
        if isinstance(data, list) and data:
            return {"token": data[0]}
        if rr.get("error"):
            return {"error": rr}
        time.sleep(5)
        rr = r.get("https://api.nopecha.com/token",
                   params={"key": key, "id": rr.get("id")}).json()
    return {"error": "timeout"}


# ---------- cekrekening.id ----------
def cekrekening():
    """Cari endpoint. Umumnya SPA + Turnstile; hasil = status blacklist."""
    g = generic()
    res = {"provider": "cekrekening", **g}
    if g.get("turnstile"):
        res["captcha"] = "cloudflare_turnstile"
        res["needs_solver"] = not (os.environ.get("CAPTCHA_KEY") or os.environ.get("NOPECHA_KEY"))
    return res


# ---------- KPU DPT ----------
def kpu():
    """KPU butuh reCAPTCHA v2 token (arg2). Kalau tak ada token -> error jelas."""
    if not A2:
        return {"provider": "kpu", "error": "butuh token reCAPTCHA di arg2 (atau solver)"}
    r = requests_()
    q = {"query": "query findNikSidalih($wilayah_id:Int!,$nik:String!,$token:String!){"
                  "findNikSidalih(wilayah_id:$wilayah_id,nik:$nik,token:$token)"
                  "{nama nkk provinsi kabupaten kecamatan kelurahan jenis_kelamin}}",
         "variables": {"nik": A1, "wilayah_id": int(A1[:2]) if A1[:2].isdigit() else 0, "token": A2}}
    rr = r.post("https://cekdptonline.kpu.go.id/v2", json=q,
                headers={"User-Agent": UA, "Content-Type": "application/json"},
                timeout=30, proxies=proxies())
    return {"provider": "kpu", "code": rr.status_code, "json": _j(rr)}


def _j(rr):
    try:
        return rr.json()
    except Exception:
        return rr.text[:2000]


def main():
    try:
        if PROV == "rfpdev":
            res = rfpdev()
        elif PROV == "cekrekening":
            res = cekrekening()
        elif PROV == "kpu":
            res = kpu()
        else:
            res = generic()
    except Exception as e:
        res = {"provider": PROV, "error": str(e)[:500]}
    out({"ok": "error" not in res, **res})


if __name__ == "__main__":
    main()
