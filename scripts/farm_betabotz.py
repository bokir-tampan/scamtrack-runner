#!/usr/bin/env python3
"""farm_betabotz.py — daftar betabotz pakai tempmail NayTra (mail.naytra.net), auto-verifikasi, ambil apikey."""
import json, random, string, time, re, sys, ssl, urllib.request, urllib.parse, http.cookiejar

sys.path.insert(0, "/root/.hermes/tools/grok-farm")
import naytra_client as nc

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE

def req(url, data=None, headers=None, opener=None):
    h = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
    h.update(headers or {})
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode()
            h.setdefault("Content-Type","application/x-www-form-urlencoded")
        else:
            body = data
    r = urllib.request.Request(url, data=body, headers=h)
    op = opener or urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    resp = op.open(r, timeout=30)
    return resp.read().decode("utf-8","replace"), resp

def bb_register(email, username, nomor, pw):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=ctx))
    out, _ = req("https://api.betabotz.eu.org/users/register",
                 {"email":email,"username":username,"nomor":nomor,"password":pw,"confirmPassword":pw},
                 {"X-Requested-With":"XMLHttpRequest","Origin":"https://api.betabotz.eu.org",
                  "Referer":"https://api.betabotz.eu.org/users/register"}, opener=op)
    return out, op

def find_verify(blob):
    for u in re.findall(r'https?://[^\s"\'<>()]+', blob or ""):
        if re.search(r'verif|activ|confirm|token|/users/', u, re.I):
            return u.rstrip('\\')
    return None

def main():
    n = nc.Naytra()
    email = n.create_inbox()
    print("mail:", email)
    u = "osint"+''.join(random.choices(string.ascii_lowercase,k=6))
    nomor = "+62812%07d" % random.randint(0,9999999)
    out, op = bb_register(email, u, nomor, "Rahasia#2026")
    print("register:", out[:140].replace("\n"," "))
    link = None
    for i in range(24):
        d = n._get(f"/api/inbox/{email}")
        for e in d.get("emails") or []:
            eid = e.get("id")
            ed = n._get(f"/api/email/{eid}") if eid is not None else {}
            link = find_verify(json.dumps({**e, **ed}))
            if link:
                print("email subj:", e.get("subject"))
                break
        if link:
            break
        time.sleep(5)
    print("verify:", link)
    if link:
        try:
            v, _ = req(link, {"Accept":"text/html"}, opener=op)
            print("verify resp:", len(v), "byte")
        except Exception as e:
            print("verify err:", e)
    for path in ["/users/profile","/users/dashboard","/users/apikey","/profile"]:
        try:
            p, _ = req("https://api.betabotz.eu.org"+path, opener=op)
            m = re.findall(r'(?:apikey|api key|key)["\'>:=\s]{1,6}([A-Za-z0-9\-_]{10,40})', p, re.I)
            print(f"[{path}] len {len(p)} keys={m[:3]}")
        except Exception as e:
            print(f"[{path}] err {e}")
    open("/tmp/betabotz_acct.json","w").write(json.dumps(
        {"addr":email,"user":u,"nomor":nomor,"pw":"Rahasia#2026","verify":link}))

if __name__ == "__main__":
    main()
