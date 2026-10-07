#!/usr/bin/env python3
"""captcha_bypass.py — selesaikan captcha TANPA solver berbayar.

PENTING: reCAPTCHA sitekey hanya terbit token di DOMAIN ASLINYA. Jadi solve
harus di halaman target yang sebenarnya (bukan inject di halaman kosong).

Alur (reCAPTCHA v2):
  camoufox stealth → buka pageurl asli → klik checkbox anchor
  → kalau muncul tantangan gambar: tombol AUDIO → ambil mp3 (via context request
    supaya cookie/UA benar) → faster-whisper transkripsi → isi → verify
  → poll token dari textarea#g-recaptcha-response.

Turnstile: buka pageurl asli → poll [name=cf-turnstile-response].
"""
import io, re, json, sys, time


def _camoufox():
    from camoufox.sync_api import Camoufox
    return Camoufox


def _transcribe(mp3_bytes):
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(io.BytesIO(mp3_bytes), language="en")
    txt = " ".join(s.text for s in segs).strip()
    return re.sub(r"[^a-z0-9 ]", "", txt.lower())


def _token(page):
    return page.evaluate(
        "() => {const t=document.querySelector('#g-recaptcha-response');"
        "return t ? t.value : '';}")


def solve_recaptcha_on_page(pageurl, timeout=150):
    Camoufox = _camoufox()
    token, notes = None, []
    with Camoufox(headless=True, os="windows", humanize=True,
                  locale="id-ID", geoip=True, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.goto(pageurl, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        anchor = page.frame_locator("iframe[src*='api2/anchor']")
        try:
            anchor.locator("#recaptcha-anchor").click(timeout=15000)
            notes.append("clicked_anchor")
        except Exception as e:
            notes.append("anchor_click_fail:" + str(e)[:60])
        deadline = time.time() + timeout
        while time.time() < deadline:
            tok = _token(page)
            if tok:
                token = tok
                break
            try:
                bf = page.frame_locator("iframe[src*='api2/bframe']")
                btn = bf.locator("#recaptcha-audio-button")
                if btn.count() and btn.is_visible():
                    btn.click(timeout=6000)
                    notes.append("audio_clicked")
                    page.wait_for_timeout(2500)
                    src = bf.locator("#audio-source").get_attribute("src")
                    if src:
                        try:
                            resp = page.context.request.get(src, timeout=30000)
                            ans = _transcribe(resp.body())
                            notes.append("stt:" + ans[:40])
                            bf.locator("#audio-response").fill(ans, timeout=8000)
                            bf.locator("#recaptcha-verify-button").click(timeout=8000)
                            page.wait_for_timeout(3000)
                        except Exception as e:
                            notes.append("stt_fail:" + str(e)[:60])
            except Exception:
                pass
            page.wait_for_timeout(1500)
    return {"token": token, "ok": bool(token), "notes": notes}


def solve_turnstile_on_page(pageurl, timeout=90):
    Camoufox = _camoufox()
    token, notes = None, []
    with Camoufox(headless=True, os="windows", humanize=True,
                  locale="id-ID", geoip=True, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        page.goto(pageurl, wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + timeout
        while time.time() < deadline:
            tok = page.evaluate(
                "() => {const e=document.querySelector('[name=cf-turnstile-response]');"
                "return e? e.value:'';}")
            if tok:
                token = tok
                break
            try:
                page.frame_locator("iframe[src*='challenges.cloudflare.com']") \
                    .locator("body").first.click(timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
    return {"token": token, "ok": bool(token), "notes": notes}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "recaptcha"
    url = sys.argv[2] if len(sys.argv) > 2 else ""
    fn = solve_turnstile_on_page if mode == "turnstile" else solve_recaptcha_on_page
    print(json.dumps(fn(url), ensure_ascii=False))
