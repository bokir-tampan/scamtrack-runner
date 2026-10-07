#!/usr/bin/env python3
"""scamtrack GH-Action lookup runner.

Input: /tmp/inp.json  {provider, action, arg1, arg2, arg3, use_proxy}
Output: result.json  — selalu JSON.

Provider:
  rfpdev      — rekening/ewallet/nik (gratis, tanpa key)  [tanpa captcha]
  kpu         — DPT KPU (token reCAPTCHA; auto-bypass kalau arg2 kosong)
  cekrekening — blacklist resmi Komdigi (Cloudflare Turnstile)
  solvecaptcha— uji solver gratis: action=recaptcha|turnstile
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
# ---------- generic browser (camoufox) ----------
def generic():
    url = A1
    wait = int(A3 or 8)
    b = _bypass()
    if not b:
        return {"error": "camoufox tidak tersedia"}
    from camoufox.sync_api import Camoufox
    with Camoufox(headless=True, os="windows", humanize=True,
                  locale="id-ID", timezone="Asia/Jakarta", geoip=True,
                  i_know_what_im_doing=True, proxy=_cf_proxy()) as br:
        pg = br.new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(wait * 1000)
        html = pg.content()
        pg.screenshot(path="page.png", full_page=True)
        turnstile = "challenges.cloudflare.com" in html or "turnstile" in html.lower()
        recaptcha = "recaptcha" in html.lower()
        body = pg.inner_text("body")[:5000]
    return {"provider": "generic", "url": url, "turnstile": turnstile,
            "recaptcha": recaptcha, "text": body, "screenshot": "page.png"}


def solvecaptcha():
    """Uji solver gratis: provider=solvecaptcha, action=recaptcha|turnstile, arg1=sitekey|url."""
    b = _bypass()
    if not b:
        return {"error": "captcha_bypass tidak tersedia"}
    if ACT == "turnstile":
        return {"kind": "turnstile", **b.solve_turnstile(A1)}
    return {"kind": "recaptcha", **b.solve_recaptcha_v2_html(A1 or KPU_SITEKEY, A2 or None)}


def _cf_proxy():
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not p:
        return None
    u = up.urlparse(p)
    return ("http", f"{u.hostname}:{u.port}", u.username, u.password)


def _pw_proxy():
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not p:
        return None
    u = up.urlparse(p)
    return {"server": f"{u.scheme}://{u.hostname}:{u.port}",
            "username": u.username, "password": u.password}


# ---------- captcha solving ----------
def _bypass():
    try:
        import captcha_bypass
        return captcha_bypass
    except Exception as e:
        print("[bypass import err]", e)
        return None


def solve_turnstile(sitekey, pageurl):
    key = os.environ.get("CAPTCHA_KEY")
    prov = (os.environ.get("CAPTCHA_PROVIDER") or "").lower()
    if key and prov in ("2captcha", "anticaptcha", "capsolver"):
        return _api_captcha(prov, key, sitekey, pageurl)
    nope = os.environ.get("NOPECHA_KEY")
    if nope:
        return _nopecha(nope, sitekey, pageurl)
    # gratis: browser stealth
    b = _bypass()
    if b:
        if "recaptcha" in pageurl:
            return b.solve_recaptcha_v2_html(sitekey, pageurl)
        return b.solve_turnstile(pageurl)
    return {"error": "no solver key & bypass module tak ada"}


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
KPU_SITEKEY = "6Lcs6gYaAAAAAFgluYoQBea_lCpiT9MkKH-jzhDH"


def kpu():
    """KPU butuh token reCAPTCHA v2. arg2 = token; kalau kosong → bypass gratis."""
    token = A2
    solved = None
    if not token:
        b = _bypass()
        if b:
            solved = b.solve_recaptcha_v2_html(KPU_SITEKEY, "https://cekdptonline.kpu.go.id/")
            token = solved.get("token")
    if not token:
        return {"provider": "kpu", "error": "token reCAPTCHA gagal didapat",
                "solver": solved}
    r = requests_()
    q = {"query": "query findNikSidalih($wilayah_id:Int!,$nik:String!,$token:String!){"
                  "findNikSidalih(wilayah_id:$wilayah_id,nik:$nik,token:$token)"
                  "{nama nkk provinsi kabupaten kecamatan kelurahan jenis_kelamin}}",
         "variables": {"nik": A1, "wilayah_id": int(A1[:2]) if A1[:2].isdigit() else 0, "token": token}}
    rr = r.post("https://cekdptonline.kpu.go.id/v2", json=q,
                headers={"User-Agent": UA, "Content-Type": "application/json"},
                timeout=30, proxies=proxies())
    return {"provider": "kpu", "solver": ("bypass" if solved else "operator_token"),
            "code": rr.status_code, "json": _j(rr)}


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
        elif PROV == "solvecaptcha":
            res = solvecaptcha()
        else:
            res = generic()
    except Exception as e:
        res = {"provider": PROV, "error": str(e)[:500]}
    out({"ok": "error" not in res, **res})


if __name__ == "__main__":
    main()
