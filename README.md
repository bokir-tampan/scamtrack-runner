# GH-Actions lookup harness

Jalur untuk request yang butuh **captcha / IP asing / browser** — dijalankan di
runner GitHub (IP cloud bersih, rotasi tiap run), hasil balik ke scamtrack.

## Kenapa
- `rfpdev.me` gratis tanpa key tapi **rate-limit per network** → tiap run runner
  baru = IP baru, aman dari "Too many requests".
- KPU (`cekdptonline.kpu.go.id`) butuh token reCAPTCHA — solver di CI.
- `cekrekening.id` di belakang **Cloudflare Turnstile** — solver + browser di CI.
- Box Hermes tak punya Chromium → browser berat dijalankan di runner.

## Struktur
```
gh/
  .github/workflows/osint-lookup.yml   # workflow (workflow_dispatch + repository_dispatch)
  scripts/run_lookup.py                # logika: rfpdev | kpu | cekrekening | generic
```

## Deploy
```bash
# buat repo (private) via gh CLI
gh repo create scamtrack-runner --private --source gh --push
# atau: cd gh && git init && git add . && git commit -m init
#       gh repo create <user>/scamtrack-runner --private --source . --push
```

## Secrets (Settings → Secrets → Actions)
| Secret | Untuk |
|---|---|
| `CAPTCHA_KEY` + `CAPTCHA_PROVIDER` | 2captcha / capsolver (`AntiTurnstileTaskProxyLess`) |
| `NOPECHA_KEY` | alternatif solver Turnstile/reCAPTCHA |
| `HTTP_PROXY` | IP Indonesia (cekbansos 403 dari IP asing; opsional) |
| `TG_BOT_TOKEN` + `TG_CHAT` | kirim hasil balik ke Telegram |

## Trigger
**Manual (Actions → Run workflow):** provider `rfpdev`, action `ewallet`,
arg1 `wallet_dana`, arg2 `081234567890`.

**API (dari scamtrack):**
```bash
curl -X POST https://api.github.com/repos/<user>/scamtrack-runner/dispatches \
  -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  -d '{"event_type":"osint-lookup","client_payload":{
       "provider":"kpu","action":"dpt","arg1":"3273...","arg2":"<recaptcha_token>"}}'
```
Ambil hasil: `actions/upload-artifact` → `osint-result` (`result.json`), atau
polling via API actions/runs.

## Provider & action
| provider | action | arg1 | arg2 |
|---|---|---|---|
| rfpdev | rekening | bank_code (mis. bank_bca) | nomor rekening |
| rfpdev | ewallet | kode (mis. wallet_dana/gopay_user) | nomor HP |
| rfpdev | nik | NIK 16 | — |
| rfpdev | check | (search) | — |
| kpu | dpt | NIK | token reCAPTCHA |
| cekrekening | check | (URL opsional) | — |
| generic | get | URL | wait detik (arg3) |

## Captcha policy — BYPASS GRATIS (terbukti jalan)
Tidak perlu solver berbayar. `scripts/captcha_bypass.py`:
- **reCAPTCHA v2** di halaman asli target (sitekey terikat domain → wajib pageurl asli):
  camoufox stealth → klik anchor → kalau tantangan gambar → tombol **AUDIO** →
  ffmpeg → **STT gratis** (SpeechRecognition/Google Web Speech, fallback faster-whisper)
  → isi jawaban → verify → token.
  ✅ Teruji di GH Actions: `{ok:true, token:"0cAFcWeA43..."}` (demo reCAPTCHA Google).
- **Turnstile**: camoufox buka pageurl asli → poll `cf-turnstile-response`.
- Solver berbayar (2captcha/capsolver/nopecha) cuma *opsional* kalau ada `CAPTCHA_KEY`.

**Catatan KPU:** `cekdptonline.kpu.go.id` menggantung dari IP GH (harus IP Indonesia)
→ set secret `HTTP_PROXY` (VPS ID) supaya goto tidak timeout. Bypass-nya sendiri jalan.

## Lanjutan (opsional)
`scamtrack` bisa memanggil harness ini otomatis: set `GH_TOKEN` + `SCAM_GH_REPO`,
lalu `rek()` fallback ke dispatch saat rate-limit. Belum diaktifkan di v2 ini.
