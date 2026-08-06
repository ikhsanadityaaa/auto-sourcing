"""
Agent 1 (Verifier) - Groq (Llama 3.3 70B).
Tugas: cek apakah kandidat dari Agent 2 benar-benar cocok dengan kode/spec asli.
Tidak butuh internet, murni reasoning matching -> makanya pakai model murah/cepat.
"""

import json
import re
from groq import Groq

from groq_retry import call_with_retry

MODEL = "llama-3.3-70b-versatile"  # cek console.groq.com/docs/models kalau model ini deprecated

SYSTEM_PROMPT = """Kamu adalah quality-checker untuk data spare part industri.
Kamu akan menerima data kode/spec ASLI dari client, dan beberapa KANDIDAT hasil
pencarian internet yang mengklaim sebagai varian dari part itu.

Untuk tiap kandidat, evaluasi:
- Apakah variant_model konsisten dengan pola kode asli (base code sama, cuma suffix beda)?
- Apakah full_spec masuk akal untuk jenis produk & maker yang disebutkan?
- Apakah source_url terlihat kredibel (bukan link kosong/placeholder)?

Beri confidence: "high", "medium", atau "low" untuk tiap kandidat yang kamu terima.
Kandidat dengan confidence "low" TETAP dimasukkan ke verified (biar user yang putuskan),
tapi kandidat yang JELAS tidak nyambung sama sekali (misal beda kategori produk total)
harus di-reject.

WAJIB balas HANYA JSON, tanpa teks lain, tanpa markdown fence:
{
  "verified": [
    {"variant_model": "...", "full_spec": "...", "source_url": "...", "confidence": "high|medium|low"}
  ],
  "rejected_feedback": "penjelasan singkat kalau ada yang direject atau kalau verified kosong, untuk dipakai search ulang. Kosongkan string ini kalau semua diterima."
}
"""


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"verified": [], "rejected_feedback": "gagal parse response verifier"}


MAX_CANDIDATES = 15        # batas jumlah kandidat yang dikirim ke verifier per panggilan
MAX_FIELD_CHARS = 400      # batas panjang tiap field teks kandidat (full_spec kadang kebawa
                            # konten scraping web yang panjang dari Agent 2 -> bisa bikin request
                            # ke Groq kena 413 Request Entity Too Large)


def _sanitize_candidates(candidates: list) -> list:
    """Potong field yang kepanjangan & batasi jumlah kandidat, biar payload ke Groq
    tidak membengkak (root cause error 413 request_too_large)."""
    trimmed = []
    for c in candidates[:MAX_CANDIDATES]:
        if not isinstance(c, dict):
            continue
        clean = {}
        for key, val in c.items():
            if isinstance(val, str) and len(val) > MAX_FIELD_CHARS:
                clean[key] = val[:MAX_FIELD_CHARS] + " ...[dipotong]"
            else:
                clean[key] = val
        trimmed.append(clean)
    return trimmed


def verify_candidates(client: Groq, code: str, product: str, spec: str, maker: str,
                       candidates: list) -> dict:
    if not candidates:
        return {"verified": [], "rejected_feedback": "tidak ada kandidat ditemukan, coba kata kunci lain"}

    candidates = _sanitize_candidates(candidates)

    user_prompt = f"""DATA ASLI:
Kode internal: {code}
Nama produk: {product}
Spec awal: {spec}
Maker: {maker}

KANDIDAT DARI PENCARIAN INTERNET:
{json.dumps(candidates, ensure_ascii=False, indent=2)}
"""

    completion = call_with_retry(
        client.chat.completions.create,
        label=f"verify_candidates[{code}]",
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )

    text = completion.choices[0].message.content or ""
    result = _extract_json(text)
    if "verified" not in result:
        result["verified"] = []
    if "rejected_feedback" not in result:
        result["rejected_feedback"] = ""
    return result
