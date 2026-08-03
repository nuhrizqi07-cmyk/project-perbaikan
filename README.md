# Project Perbaikan — Isi Otomatis dari PDF

Upload PDF **Surat Persetujuan Kepala Kantor** → kolom terisi otomatis, simpan ke Google Sheet.

## Cara Jalan (Lokal)

```bash
cd "/run/media/noah/Data/My SaaS/project-perbaikan"
source venv/bin/activate
streamlit run project-perbaikan-app.py
```

Buka `http://localhost:8501` di browser.

## Flow

1. Upload PDF surat persetujuan
2. Field otomatis terisi (cek & perbaiki kalau perlu)
3. Pilih **B. Pegawai PDAD** (dropdown)
4. Klik **Simpan** → tersimpan lokal (XLSX + CSV) **dan** dikirim ke Google Sheet via Apps Script
5. Muncul link 🔗 Buka Google Sheet

## Kolom

| Kolom | Status |
|---|---|
| D. Surat Persetujuan | Otomatis — nomor setelah `S-` (contoh: `1850`) |
| E, F, I, J, L, M, O, P, Q, R | Otomatis dari PDF |
| G. Tanggal diterima PDAD | Otomatis — hari ini |
| B. Pegawai PDAD | Manual — dropdown (3 nama) |
| H. Jenis, K. Kode Dokumen, N. Aplikasi | Tidak diisi (disabled) |

## Deploy ke Streamlit Community Cloud

### 1. Buat repo GitHub

```bash
cd "/run/media/noah/Data/My SaaS/project-perbaikan"
git init
git add -A
git commit -m "Project Perbaikan app"
# buat repo di GitHub, lalu:
git remote add origin https://github.com/USERNAME/project-perbaikan.git
git push -u origin main
```

> `.gitignore` sudah disiapkan — `venv/`, `data_perbaikan.*`, `service_account.json`, dan `apps_script_config.json` **tidak ikut ter-commit**.

### 2. Connect ke Streamlit Cloud

1. Buka https://share.streamlit.io → **Sign in with GitHub**
2. **Create app** → pilih repo `project-perbaikan` → branch `main` → file `project-perbaikan-app.py`
3. **Deploy** — tunggu build selesai

### 3. Set Secrets (penting!)

Di dashboard app → **Settings → Secrets**, tambahkan:

```toml
apps_script_url = "https://script.google.com/macros/s/AKfycbyMq2vZmQpJDIzYZtm9th83JuhsCWAuixt3qnvX31yIUqK71eNEXFJHj08SHDdONyCp/exec"
apps_script_token = "pp-3051b019bc54b9c0"
```

App otomatis baca dari Secrets. Kalau tidak di-set, fallback ke `apps_script_config.json` (hanya untuk lokal).

### 4. Catatan Cloud

- Folder app **read-only** di cloud → data sementara disimpan ke `~/project_perbaikan_data/` (ephemeral, hilang saat restart)
- **Sumber data permanen = Google Sheet** — semua baris tetap aman di sana
- Download XLSX tetap jalan (dibuat on-the-fly dari data session)
- Riwayat antar-session di sidebar akan kosong di cloud (karena file lokal ephemeral) — data asli ada di Google Sheet

## File

| File | Fungsi |
|---|---|
| `project-perbaikan-app.py` | App Streamlit (UI) |
| `surat_parser.py` | Parser regex PDF → field |
| `apps_script_config.json` | Config Apps Script (lokal, jangan di-commit) |
| `apps_script_code.gs` | Kode Apps Script untuk Google Sheet |
| `requirements.txt` | Dependency untuk deploy |
| `.gitignore` | File yang tidak ikut git |
