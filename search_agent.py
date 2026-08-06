"""
Agent 2 (Searcher) - Groq groq/compound (Llama/GPT-OSS + web search bawaan).
Tugas: cari spec lengkap + SEMUA varian model number (beda suffix/prefix)
di internet, bukan dari website resmi maker / katalog resmi.
"""

import json
import re
from groq import Groq

MODEL = "groq/compound"  # system Groq dgn web search bawaan. Cek console.groq.com/docs/compound
                          # kalau ini error/deprecated di kemudian hari.

SYSTEM_PROMPT = """Kamu adalah asisten riset spare part industri dengan akses web search.
Tugasmu: diberikan kode internal, nama produk, spec awal (sering tidak lengkap),
dan nama maker/brand, kamu HARUS cari via web search:

1. Spec teknis LENGKAP dari part ini (dimensi, rating, material, dll - apapun yang relevan).
2. SEMUA varian model number yang mirip dengan prefix/base code yang sama tapi
   punya suffix berbeda (contoh: DVM4-40-02 dan DVM4-40-02-D adalah 2 varian berbeda,
   keduanya harus dilaporkan terpisah).
3. Link sumber untuk tiap varian. ATURAN PENTING: sumber TIDAK BOLEH dari:
   - Website resmi milik maker/brand itu sendiri (domain yang mengandung nama maker)
   - Halaman katalog resmi manufaktur
   Sumber yang boleh: distributor pihak ketiga, marketplace industri, database
   datasheet independen, forum teknik, dokumentasi engineering pihak ketiga.

Kalau setelah pencarian kamu TIDAK menemukan varian yang cocok sama sekali,
kembalikan array kosong - JANGAN mengarang data.

WAJIB balas HANYA dalam format JSON array, tanpa teks lain, tanpa markdown fence,
tanpa penjelasan proses pencarian:
[
  {
    "variant_model": "kode model spesifik varian ini",
    "full_spec": "spec teknis lengkap dalam satu kalimat/paragraf pendek",
    "source_url": "URL sumber (bukan website resmi maker)",
    "source_type": "distributor / marketplace / datasheet_db / forum / lainnya"
  }
]
"""


def _extract_json(text: str):
    """Model kadang bungkus JSON dengan ```json ... ``` atau nambah teks lain walau sudah
    diminta polos, atau JSON-nya kepotong di tengah teks penjelasan. Bersihkan & ambil array-nya."""
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # fallback: cari blok [...] pertama di dalam teks, siapa tahu ada teks lain nyempil
    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    return []


def search_part(client: Groq, code: str, product: str, spec: str, maker: str,
                 retry_feedback: str = "") -> list:
    """
    Cari spec + varian untuk 1 item PO.
    retry_feedback: dipakai kalau ini pencarian ulang setelah Agent 1 menolak hasil sebelumnya -
    isi feedback kenapa ditolak, supaya Agent 2 cari dengan strategi berbeda.
    """
    user_prompt = f"""Kode internal: {code}
Nama produk: {product}
Spec awal (sering tidak lengkap): {spec}
Maker/Brand: {maker}
"""
    if retry_feedback:
        user_prompt += f"\nCATATAN: pencarian sebelumnya ditolak verifier karena: {retry_feedback}\nCoba strategi pencarian lain / sumber lain."

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=4096,  # batasi output Agent 2 - tanpa ini kadang balasan bisa sangat panjang
                          # (ikut nyeret konten hasil web search), yang lalu diteruskan mentah-mentah
                          # ke Agent 1 (verify_agent) dan bikin request ke Groq kena 413
        compound_custom={"tools": {"enabled_tools": ["web_search"]}},
    )

    text = completion.choices[0].message.content or ""
    candidates = _extract_json(text)
    if not isinstance(candidates, list):
        return []
    return candidates
