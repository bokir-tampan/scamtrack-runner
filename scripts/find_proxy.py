#!/usr/bin/env python3
"""find_proxy.py — ambil free proxy, tes tembus Cloudflare sampai dashboard.api.co.id/register."""
import sys, concurrent.futures as cf
from curl_cffi import requests
import concurrent.futures

SRC = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=id",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
]

def load():
    seen, out = set(), []
    for u in SRC:
        try:
            r = requests.get(u, timeout=20, impersonate="chrome")
            for line in r.text.splitlines():
                p = line.strip()
                if p and ":" in p and p not in seen:
                    seen.add(p); out.append(p)
        except Exception as e:
            print("src fail", u[:50], e, file=sys.stderr)
    return out

def test(p):
    url = "http://" + p
    try:
        r = requests.get("https://dashboard.api.co.id/register", proxies={"http": url, "https": url},
                         impersonate="chrome", timeout=18)
        cf = "Just a moment" in r.text
        return (p, r.status_code, cf, len(r.text))
    except Exception as e:
        return (p, "err", str(e)[:40], 0)

def main():
    prox = load()
    print("proxies loaded:", len(prox))
    good = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as ex:
        for i, res in enumerate(ex.map(test, prox[:300])):
            p, code, cf, ln = res
            if code == 200 and cf is False and ln > 3000:
                print("HIT", p, code, "cf=", cf, "len=", ln)
                good.append(p)
            if i % 50 == 0:
                print("...tested", i, flush=True)
    open("/tmp/good_proxy.txt", "w").write("\n".join(good))
    print("GOOD:", good)

if __name__ == "__main__":
    main()
