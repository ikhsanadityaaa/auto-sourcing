"""
Wrapper tipis di atas gspread untuk baca sheet sumber (PO items)
dan tulis hasil ke sheet output (AI_Result), termasuk expand 1 varian = 1 baris.
"""

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SOURCE_SHEET_NAME = "Sheet1"     # tab sumber, sesuai sheet CSR Anda
OUTPUT_SHEET_NAME = "AI_Result"  # tab hasil, dibuat otomatis kalau belum ada

OUTPUT_HEADERS = [
    "EMS Code",
    "EMS Product",
    "Original Spec",
    "Maker",
    "Variant Model #",
    "Full Spec (AI)",
    "Source URL",
    "Confidence",
    "Status",
    "Human Confirm",
    "Processed At",
]


class SheetsClient:
    def __init__(self, service_account_json_path: str, spreadsheet_id: str):
        creds = Credentials.from_service_account_file(service_account_json_path, scopes=SCOPES)
        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_key(spreadsheet_id)

    def get_source_rows(self):
        """Baca semua baris dari sheet sumber. Return list of dict."""
        ws = self.sh.worksheet(SOURCE_SHEET_NAME)
        records = ws.get_all_records()  # pakai header row 1 otomatis
        rows = []
        for r in records:
            code = str(r.get("EMS Code", "")).strip()
            if not code:
                continue
            rows.append({
                "code": code,
                "product": str(r.get("EMS product", "")).strip(),
                "spec": str(r.get("EMS Spec", "")).strip(),
                "model": str(r.get("Model #", "")).strip(),
                "maker": str(r.get("Maker", "")).strip(),
            })
        return rows

    def get_output_ws(self):
        """Ambil/bikin worksheet output, pastikan header ada."""
        try:
            ws = self.sh.worksheet(OUTPUT_SHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=OUTPUT_SHEET_NAME, rows=2000, cols=len(OUTPUT_HEADERS))
            ws.append_row(OUTPUT_HEADERS)
            return ws

        # Pastikan header row sudah benar (kalau sheet baru dibuat manual kosong)
        first_row = ws.row_values(1)
        if first_row != OUTPUT_HEADERS:
            ws.update("A1", [OUTPUT_HEADERS])
        return ws

    def get_already_processed_codes(self):
        """Set EMS Code yang sudah pernah ditulis ke AI_Result, biar tidak diproses ulang."""
        ws = self.get_output_ws()
        col_a = ws.col_values(1)[1:]  # skip header
        return set(c.strip() for c in col_a if c.strip())

    def append_result_rows(self, rows: list):
        """
        rows: list of list, tiap item sesuai urutan OUTPUT_HEADERS.
        Ditulis langsung (incremental) supaya kalau proses berhenti di tengah,
        hasil yang sudah selesai tidak hilang.
        """
        if not rows:
            return
        ws = self.get_output_ws()
        ws.append_rows(rows, value_input_option="USER_ENTERED")
