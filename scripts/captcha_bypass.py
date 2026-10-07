#!/usr/bin/env python3
"""captcha_bypass.py — selesaikan captcha TANPA solver berbayar.

Strategi (gratis):
  reCAPTCHA v2  : camoufox stealth → klik checkbox. Kalau lolos otomatis, token
                  langsung ada. Kalau tantangan gambar muncul → tombol AUDIO →
                  unduh mp3 → transkripsi faster-whisper → isi → token.
  Cloudflare T/S: camoufox stealth + tunggu. Turnstile "managed" sering lolos
                  non-interaktif dengan browser+BIP bagus.

Token diambil dari: textarea[name=g-recaptcha-response] / input[name=cf-turnstile-response].
"""
import os, sys, time, io, json, re

UA_HINT = {"locale": "id-ID", "timezone": "Asia/Jakarta"}


def _camoufox():
    from camoufox.sync_api import Camoufox
    return Camoufox


def _transcribe(mp3_bytes):
    """faster-whisper (PyAV bundled, tak butuh ffmpeg sistem)."""
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(io.BytesIO(mp3_bytes), language="en")
    txt = " ".join(s.text for s in segs).strip()
    return re.sub(r"[^a-z0-9 ]", "", txt.lower())


def solve_recaptcha_v2_html(sitekey, pageurl=None, timeout=90):
    """Buka halaman kosong + inject reCAPTCHA v2 sitekey, lalu selesaikan."""
    Camoufox = _camoufox()
    pageurl = pageurl or "https://www.google.com/"
    html = f"""<!doctype html><html><head>
    <script src="https://www.google.com/recaptcha/api.js" async defer></script>
    </head><body>
    <div class="g-recaptcha" data-sitekey="{sitekey}"></div>
    </body></html>"""
    token = None
    with Camoufox(headless=True, os="windows", humanize=True,
                  locale=UA_HINT["locale"], timezone=UA_HINT["timezone"],
                  geoip=True, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.set_content(html)
        page.wait_for_timeout(3000)
        # klik checkbox di iframe anchor
        try:
            fr = page.frame_locator("iframe[src*='api2/anchor']")
            fr.locator("#recaptcha-anchor").click(timeout=15000)
        except Exception:
            pass
        # tunggu: (a) token di textarea (lolos), atau (b) frame bframe (tantangan)
        deadline = time.time() + timeout
        while time.time() < deadline:
            tok = page.evaluate("() => (document.querySelector('#g-recaptcha-response')||{}).value || ''")
            if tok:
                token = tok
                break
            # tantangan gambar → coba audio
            try:
                bf = page.frame_locator("iframe[src*='api2/bframe']")
                aud_btn = bf.locator("#recaptcha-audio-button")
                if aud_btn.count() and aud_btn.is_visible():
                    aud_btn.click(timeout=5000)
                    page.wait_for_timeout(2500)
                    # ambil url audio (src atau dari download link)
                    src = bf.locator("#audio-source").get_attribute("src")
                    if not src:
                        src = bf.locator("audio#audio-source, audio source").first.get_attribute("src")
                    if src:
                        import requests
                        au = requests.get(src, timeout=30).content
                        ans = _transcribe(au)
                        bf.locator("#audio-response").fill(ans, timeout=8000)
                        bf.locator("#recaptcha-verify-button").click(timeout=8000)
                        page.wait_for_timeout(3000)
                    else:
                        page.wait_for_timeout(2000)
            except Exception:
                page.wait_for_timeout(1500)
            page.wait_for_timeout(1500)
    return {"token": token, "ok": bool(token)}


def solve_turnstile(url, timeout=60):
    """Buka URL, tunggu Cloudflare Turnstile menyelesaikan token."""
    Camoufox = _camoufox()
    token = None
    with Camoufox(headless=True, os="windows", humanize=True,
                  locale=UA_HINT["locale"], timezone=UA_HINT["timezone"],
                  geoip=True, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + timeout
        while time.time() < deadline:
            tok = page.evaluate(
                "() => {const e=document.querySelector('[name=cf-turnstile-response]');"
                "return e? e.value : '';}")
            if tok:
                token = tok
                break
            # klik widget kalau perlu
            try:
                page.frame_locator("iframe[src*='challenges.cloudflare.com']") \
                    .locator("input[type=checkbox], body").first.click(timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
    return {"token": token, "ok": bool(token)}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "recaptcha"
    if mode == "recaptcha":
        print(json.dumps(solve_recaptcha_v2_html(sys.argv[2]), ensure_ascii=False))
    else:
        print(json.dumps(solve_turnstile(sys.argv[2]), ensure_ascii=False))