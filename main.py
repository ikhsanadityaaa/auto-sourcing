"""
Orchestrator utama.

Alur per item:
  1. Agent 2 (Groq groq/compound + web search) cari kandidat spec & varian model.
  2. Agent 1 (Groq llama-3.3-70b) verifikasi kandidat vs data asli.
  3. Kalau verified kosong & belum mentok MAX_RETRY -> search lagi pakai feedback dari Agent 1.
  4. Kalau ada verified (atau sudah mentok retry) -> tulis ke sheet, 1 varian = 1 baris.

Jalankan: python main.py
Env vars yang dibutuhkan (lihat README.md):
  GOOGLE_SERVICE_ACCOUNT_JSON, SPREADSHEET_ID, GROQ_API_KEY
"""

import os
import sys
import time
from datetime import datetime, timezone

from groq import Groq

from sheets_client import SheetsClient
from search_agent import search_part
from verify_agent import verify_candidates

MAX_RETRY = 3           # batas maksimal Agent1<->Agent2 loop per item, biar tidak muter tanpa henti
SLEEP_BETWEEN_ITEMS = 2  # jeda antar item (detik) - jaga-jaga rate limit free tier
SLEEP_AFTER_SEARCH_CALL = 3  # detik - Groq free tier: 30 request/menit per model,
                              # jeda min. 2s antar call; 3s buat margin aman


def process_one_item(groq_client, item: dict) -> list:
    """Return list of output rows (list of list) untuk 1 item PO, siap di-append ke sheet."""
    code = item["code"]
    product = item["product"]
    spec = item["spec"]
    maker = item["maker"]

    feedback = ""
    verified = []
    attempt = 0

    while attempt < MAX_RETRY:
        attempt += 1
        print(f"  [{code}] percobaan {attempt}/{MAX_RETRY} ...")

        candidates = search_part(groq_client, code, product, spec, maker, retry_feedback=feedback)
        time.sleep(SLEEP_AFTER_SEARCH_CALL)  # jaga rate limit Groq free tier
        result = verify_candidates(groq_client, code, product, spec, maker, candidates)
        verified = result.get("verified", [])
        feedback = result.get("rejected_feedback", "")

        if verified:
            break
        print(f"    -> belum ketemu yang cocok. feedback: {feedback}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []

    if verified:
        for v in verified:
            rows.append([
                code,
                product,
                spec,
                maker,
                v.get("variant_model", ""),
                v.get("full_spec", ""),
                v.get("source_url", ""),
                v.get("confidence", ""),
                "Need Confirmation",
                "",  # Human Confirm - dikosongkan, diisi manual oleh user
                now,
            ])
    else:
        # Sudah mentok retry, tetap dicatat sebagai baris "not found" biar kelihatan di sheet
        # dan tidak diproses ulang terus tiap kali script jalan.
        rows.append([
            code, product, spec, maker,
            "", "", "", "",
            "Not Found - Manual Search Needed",
            "",
            now,
        ])

    return rows


def main():
    service_account_path = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    groq_api_key = os.environ["GROQ_API_KEY"]

    sheets = SheetsClient(service_account_path, spreadsheet_id)
    groq_client = Groq(api_key=groq_api_key)

    source_rows = sheets.get_source_rows()
    already_done = sheets.get_already_processed_codes()

    todo = [r for r in source_rows if r["code"] not in already_done]
    print(f"Total item di sheet sumber: {len(source_rows)}")
    print(f"Sudah pernah diproses (skip): {len(already_done)}")
    print(f"Akan diproses sekarang: {len(todo)}")

    if not todo:
        print("Tidak ada item baru. Selesai.")
        return

    processed_count = 0
    not_found_count = 0

    for i, item in enumerate(todo, start=1):
        print(f"\n[{i}/{len(todo)}] Proses: {item['code']} - {item['product']}")
        try:
            rows = process_one_item(groq_client, item)
        except Exception as e:
            print(f"  !! ERROR saat proses {item['code']}: {e}")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            rows = [[
                item["code"], item["product"], item["spec"], item["maker"],
                "", "", "", "", f"Error: {e}", "", now,
            ]]

        sheets.append_result_rows(rows)  # tulis langsung, jangan tunggu semua selesai

        for r in rows:
            if r[8] == "Not Found - Manual Search Needed" or str(r[8]).startswith("Error"):
                not_found_count += 1
            else:
                processed_count += 1

        time.sleep(SLEEP_BETWEEN_ITEMS)

    print("\n=== SELESAI ===")
    print(f"Baris hasil ditulis (varian ditemukan): {processed_count}")
    print(f"Item gagal/tidak ketemu: {not_found_count}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as e:
        print(f"Environment variable belum di-set: {e}")
        sys.exit(1)
