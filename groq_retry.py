"""
Helper retry+backoff untuk panggilan ke Groq API.

Dipakai oleh search_agent.py & verify_agent.py supaya tahan terhadap error
transient yang sering muncul waktu pakai groq/compound (web search) dalam volume
banyak berturut-turut:

- 429 rate_limit_exceeded: rate limit `groq/compound` ikut rate limit model-model
  turunannya (mis. meta-llama/llama-4-scout-17b-16e-instruct yang dipakai
  compound buat orkestrasi tool call), BUKAN model yang kita panggil langsung.
  Jadi walau kita sudah kasih jeda antar call, TPM model turunan itu tetap bisa
  kepakai habis kalau volume tinggi. Groq balikin pesan yang isinya berapa detik
  harus nunggu -> kita parse & pakai itu, bukan nebak-nebak.
- 413 request_too_large: kadang muncul dari orkestrasi internal compound waktu
  hasil web search yang di-pull besar. Ukurannya beda-beda tiap kali jalan
  (tergantung apa yang ketemu di web search), jadi retry singkat kadang berhasil;
  kalau tetap gagal setelah beberapa kali, biarkan error naik ke pemanggil
  (main.py) supaya item itu dicatat sebagai error & di-skip, bukan bikin seluruh
  run berhenti.
"""

import re
import time

import groq

RETRY_WAIT_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)


def _parse_wait_seconds(message: str):
    m = RETRY_WAIT_RE.search(message)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def call_with_retry(fn, *, max_retries: int = 5, label: str = "", **kwargs):
    """Jalankan fn(**kwargs) dengan retry otomatis untuk error transient dari Groq.

    fn biasanya client.chat.completions.create - semua kwargs (model, messages, dst)
    diteruskan apa adanya ke fn, kecuali max_retries & label yang dipakai di sini saja.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn(**kwargs)
        except groq.RateLimitError as e:
            if attempt > max_retries:
                raise
            wait = _parse_wait_seconds(str(e)) or min(2 ** attempt, 30)
            print(f"    [retry] {label} kena rate limit (429), tunggu {wait:.1f}s "
                  f"(percobaan {attempt}/{max_retries}) ...")
            time.sleep(wait + 0.5)  # buffer kecil di atas waktu yang diminta Groq
        except groq.APIStatusError as e:
            if e.status_code == 413:
                if attempt > min(max_retries, 3):
                    raise
                wait = 3 * attempt
                print(f"    [retry] {label} kena 413 request_too_large, coba lagi "
                      f"dalam {wait}s (percobaan {attempt}) ...")
                time.sleep(wait)
            else:
                raise
        except (groq.APIConnectionError, groq.APITimeoutError):
            if attempt > max_retries:
                raise
            wait = min(2 ** attempt, 30)
            print(f"    [retry] {label} koneksi bermasalah, tunggu {wait}s ...")
            time.sleep(wait)
