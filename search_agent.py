"""
Agent 2 (Searcher) - Gemini Flash + Google Search grounding.
Tugas: cari spec lengkap + SEMUA varian model number (beda suffix/prefix)
di internet, bukan dari website resmi maker / katalog resmi.
"""

import json
import re
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"  # model tetap, hindari alias "latest" biar nggak boros 2x call/item
                                  # kalau ini pun error 404 di kemudian hari, cek model terbaru di:
                                  # https://ai.google.dev/gemini-api/docs/models

SYSTEM_PROMPT = """Kamu adalah asisten riset spare part industri.
Tugasmu: diberikan kode internal, nama produk, spec awal (sering tidak lengkap),
dan nama maker/brand, kamu HARUS mencari via internet:

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

WAJIB balas HANYA dalam format JSON array, tanpa teks lain, tanpa markdown fence:
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
    """Gemini kadang bungkus JSON dengan ```json ... ``` walau sudah diminta polos. Bersihkan dulu."""
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


def search_part(client: genai.Client, code: str, product: str, spec: str, maker: str,
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

    response = client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
        ),
    )

    text = response.text or ""
    candidates = _extract_json(text)
    if not isinstance(candidates, list):
        return []
    return candidates
