# PO Spec Agent

Otomatis lengkapi spec + cari semua varian model number untuk item PO di Google Sheet,
pakai 2-agent (Gemini untuk search, Groq untuk verifikasi) — 100% free tier, tanpa kartu kredit.

## Cara kerja singkat

1. Baca baris dari tab `Sheet1` (kolom: EMS Code, EMS product, EMS Spec, Model #, Maker).
2. Agent 2 (Gemini + Google Search grounding) cari spec lengkap & semua varian model.
3. Agent 1 (Groq) cek apakah hasil itu benar-benar cocok. Kalau tidak, Agent 2 disuruh cari ulang (maks 3x).
4. Hasil ditulis ke tab baru `AI_Result`, **1 varian = 1 baris**, dengan kolom `Status = Need Confirmation`.
5. Anda review manual di sheet, isi kolom `Human Confirm`.
6. Item yang sudah pernah ditulis ke `AI_Result` otomatis di-skip kalau script dijalankan lagi — jadi aman dijalankan berulang / terjadwal.

## Setup dari nol (sekali saja)

### 1. Google Service Account (buat Sheets API akses)

1. Buka https://console.cloud.google.com/ → buat project baru (gratis).
2. Aktifkan **Google Sheets API** untuk project itu (menu "APIs & Services" → "Enable APIs").
3. Buat **Service Account** (menu "IAM & Admin" → "Service Accounts" → "Create").
4. Di service account itu, buat **key baru** format JSON → akan ke-download otomatis, simpan file ini.
5. Buka Google Sheet Anda (yang sheet CSR itu) → klik **Share** → paste email service account
   (formatnya `xxxx@xxxx.iam.gserviceaccount.com`, ada di file JSON tadi) → kasih akses **Editor**.

### 2. Gemini API key (gratis, tanpa kartu kredit)

1. Buka https://aistudio.google.com/apikey
2. Sign in pakai akun Google → generate API key. Simpan.

### 3. Groq API key (gratis, tanpa kartu kredit)

1. Buka https://console.groq.com/keys
2. Sign up (email/Google) → generate API key. Simpan.

### 4. Ambil Spreadsheet ID

Dari URL sheet Anda:
```
https://docs.google.com/spreadsheets/d/INI_SPREADSHEET_ID_NYA/edit
```

### 5. Setup repo GitHub + secrets

1. Push folder ini ke repo GitHub baru (boleh private).
2. Buka repo → Settings → Secrets and variables → Actions → New repository secret. Tambahkan 4 secret ini:
   - `SPREADSHEET_ID` → spreadsheet ID dari langkah 4
   - `GEMINI_API_KEY` → dari langkah 2
   - `GROQ_API_KEY` → dari langkah 3
   - `GOOGLE_SERVICE_ACCOUNT_JSON_B64` → isi file JSON dari langkah 1, tapi di-**encode base64 dulu**:
     ```bash
     base64 -i service-account-file.json | tr -d '\n'
     ```
     Copy hasilnya (satu baris panjang) sebagai value secret.

### 6. Jalankan

- Manual: buka tab **Actions** di repo → pilih workflow "Process PO Spec Sheet" → **Run workflow**.
- Otomatis terjadwal: workflow sudah di-set jalan tiap hari jam 09:00 WIB (bisa diubah di `.github/workflows/process_sheet.yml`, baris `cron`).

## Menjalankan lokal (opsional, untuk testing sebelum push ke GitHub)

```bash
pip install -r requirements.txt

export GOOGLE_SERVICE_ACCOUNT_JSON="path/ke/service-account.json"
export SPREADSHEET_ID="spreadsheet_id_anda"
export GEMINI_API_KEY="..."
export GROQ_API_KEY="..."

python main.py
```

## Catatan penting

- **Free tier limits**: Gemini grounding 5.000 query gratis/bulan, Groq 14.400 request/hari.
  Untuk volume ~100 item/run, ini jauh cukup. Kalau suatu saat sheet Anda ribuan baris sekaligus,
  mungkin perlu beberapa hari untuk selesai semua (karena limit harian), tapi script aman
  dijalankan berkali-kali karena skip item yang sudah selesai.
- **Model names** (`gemini-2.5-flash` di `search_agent.py`, `llama-3.3-70b-versatile` di
  `verify_agent.py`) bisa berubah/deprecated seiring waktu — kalau script error soal model
  not found, cek nama model terbaru di:
  - https://ai.google.dev/gemini-api/docs/models
  - https://console.groq.com/docs/models
- **Ini bukan pengganti review manusia.** Kolom `Human Confirm` di `AI_Result` wajib dicek
  sebelum data dipakai untuk PO final — AI bisa salah cocokkan spec, terutama untuk part
  dengan kode yang mirip tapi beda produk.
