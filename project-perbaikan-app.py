#!/usr/bin/env python3
"""
project-perbaikan-app.py — Upload PDF Surat Persetujuan → Isi otomatis Google Sheet
Run: streamlit run project-perbaikan-app.py
"""

import io
import json
import os
import re
import importlib
from datetime import date, datetime

import streamlit as st
import fitz  # pymupdf

import surat_parser
importlib.reload(surat_parser)  # selalu pakai versi terbaru parser (tanpa restart app)
from surat_parser import parse_surat

# ── Konfigurasi ──
SHEET_ID = "1Jvi7Ek8LynDr5dHdc0GBahqpwiKKv_v4d1u3l7RPZWw"
SHEET_NAME = "Sheet1"
SERVICE_ACCOUNT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "service_account.json")
APPS_SCRIPT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "apps_script_config.json")

# Output: di cloud folder app read-only → simpan data sementara ke /tmp
# (data permanen tetap di Google Sheet; file lokal hanya cache/tombol download)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if os.access(APP_DIR, os.W_OK):
    DATA_DIR = APP_DIR
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"), "project_perbaikan_data")
    os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(DATA_DIR, "data_perbaikan.csv")
OUTPUT_XLSX = os.path.join(DATA_DIR, "data_perbaikan.xlsx")


def load_apps_script_config():
    """Baca konfigurasi endpoint Apps Script (url + token).

    Prioritas: st.secrets (cloud, aman) → apps_script_config.json (lokal).
    Setup di Streamlit Cloud: Settings → Secrets →
      apps_script_url = "..."
      apps_script_token = "..."
    """
    try:
        url = st.secrets.get("apps_script_url", "").strip()
        token = st.secrets.get("apps_script_token", "").strip()
        if url:
            return url, token
    except Exception:
        pass
    try:
        with open(APPS_SCRIPT_CONFIG) as f:
            cfg = json.load(f)
        return cfg.get("url", "").strip(), cfg.get("token", "").strip()
    except Exception:
        return "", ""

# Kolom yang HARUS teks (biar gak jadi scientific notation di Excel)
TEXT_COLUMNS = {4, 10, 12}  # D(4) Surat, J(10) Nomor Aju, L(12) Nopen


def clean_aju(x):
    """Normalisasi nomor aju: buang SEMUA varian tanda hubung (- − – — ‐)."""
    if x is None:
        return ""
    return re.sub(r"[\-−–—‐]", "", str(x)).strip()


def pad_nopen(x):
    """Normalisasi nopen: angka saja, wajib 6 digit (isi 0 di depan kalau kurang)."""
    if x is None:
        return ""
    if isinstance(x, (int, float)):
        digits = str(int(x))
    else:
        digits = re.sub(r"[^0-9]", "", str(x))
    return digits.zfill(6) if digits else ""

# Mapping kolom: nama field → nomor kolom (1-based)
COLUMNS = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "I": 9, "J": 10, "K": 11, "L": 12, "M": 13, "N": 14, "O": 15,
    "P": 16, "Q": 17, "R": 18,
}

st.set_page_config(page_title="Parser Surat Perbaikan",
                   page_icon="📋", layout="wide")


def extract_pdf(uploaded_file):
    """Extract text from uploaded PDF."""
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    return text


def append_row_gs(values):
    """Append a row to Google Sheet via service account."""
    import gspread
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    ws.append_row(values)
    return True


def send_to_apps_script(values):
    """Kirim 1 baris data ke Google Sheet via Apps Script web app.

    values: list 18 elemen (kolom A–R, A diisi otomatis di sisi sheet).
    Return: (ok: bool, message: str)
    """
    import requests

    url, token = load_apps_script_config()
    if not url:
        return False, "URL Apps Script belum diisi (apps_script_config.json / Secrets)"

    payload = {"token": token, "values": values}

    def _post():
        return requests.post(url, json=payload, timeout=120)

    # Warm-up doGet dulu (Apps Script lambat saat cold start — bisa >30s)
    try:
        requests.get(url, timeout=30)
    except Exception:
        pass  # warm-up gagal bukan masalah fatal

    try:
        resp = _post()
        data = resp.json()
        if data.get("ok"):
            return True, f"Tersimpan ke sheet baris {data.get('row', '?')}"
        return False, data.get("error", f"HTTP {resp.status_code}")
    except Exception as e:
        # Retry sekali — seringnya timeout karena cold start, coba kedua lebih cepat
        try:
            resp = _post()
            data = resp.json()
            if data.get("ok"):
                return True, f"Tersimpan ke sheet baris {data.get('row', '?')}"
            return False, data.get("error", f"HTTP {resp.status_code}")
        except Exception as e2:
            return False, f"Gagal hubungi Apps Script: {e2}"


def main():
    st.title("Parser Surat Perbaikan")
    st.caption("Upload PDF Surat Persetujuan Kepala Kantor Spreadsheet terisi Otomatis")

    # ── Sidebar: Download data tersimpan ──
    with st.sidebar:
        st.header("⬇️ Download Data")
        rows = load_local_rows()
        if rows:
            st.caption(f"{len(rows)} baris tersimpan di CSV lokal")
            st.download_button(
                "📊 Download XLSX",
                data=build_xlsx_bytes(rows),
                file_name="data_perbaikan.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.download_button(
                "📄 Download CSV",
                data=open(OUTPUT_CSV, "rb").read(),
                file_name="data_perbaikan.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("Belum ada data tersimpan.")

    # ── Upload ──
    uploaded = st.file_uploader("📄 Upload PDF Surat Persetujuan",
                                type=["pdf"])

    if uploaded is None:
        st.info("Upload PDF surat persetujuan untuk mulai.")
        return

    # ── Parse ──
    with st.spinner("Membaca PDF..."):
        text = extract_pdf(uploaded)
        parsed_list = parse_surat(text)

    is_multi = len(parsed_list) > 1
    st.success(f"✅ PDF terbaca — {len(parsed_list)} aju ditemukan"
               + (" (multi-aju)" if is_multi else ""))

    # ── Pick which aju to display/edit ──
    if is_multi:
        # Tampilkan tabel ringkasan, user bisa pilih aju untuk edit
        st.subheader(f"📋 Daftar {len(parsed_list)} Aju")
        preview = []
        for i, p in enumerate(parsed_list):
            preview.append({
                "#": i + 1,
                "No Aju": clean_aju(p["nomor_aju"]),
                "Nopen": p["nopen"],
                "Status": p["status"],
                "Item": p["item_perbaikan"][:60] + ("..." if len(p.get("item_perbaikan","")) > 60 else ""),
            })
        st.dataframe(preview, use_container_width=True, hide_index=True)
        st.caption("Semua aju akan disimpan jadi baris terpisah di Google Sheet.")
        selected_idx = 0  # default: edit aju pertama
        st.divider()

    # Pilih data untuk ditampilkan di form
    parsed = parsed_list[0] if is_multi else parsed_list[0]

    # ── Form: kolom yang diisi otomatis (D–M, O–R) ──
    st.subheader("📝 Data Terisi Otomatis")

    # Row 1: Surat + tanggal
    c1, c2, c3 = st.columns(3)
    with c1:
        d_surat = st.text_input("D. Surat Persetujuan Kepala Kantor", parsed["surat"])
    with c2:
        e_tgl_surat = st.text_input("E. Tanggal Surat Persetujuan", parsed["tanggal_surat"])
    with c3:
        g_tgl_diterima = st.date_input("G. Tanggal diterima PDAD", value=date.today())

    # Hal
    f_hal = st.text_input("F. Hal Surat Persetujuan", parsed["hal"])

    # Row 2: Perusahaan (H. Jenis & K. Kode Dokumen dikosongkan sesuai revisi)
    c4, c5, c6 = st.columns(3)
    with c4:
        st.caption("H. Jenis")
        st.text_input("tidak diisi (revisi)", value="", disabled=True, key="jenis_disabled")
    with c5:
        i_perusahaan = st.text_input("I. Perusahaan", parsed["perusahaan"])
    with c6:
        st.caption("K. Kode Dokumen")
        st.text_input("tidak diisi (revisi)", value="", disabled=True, key="kode_disabled")

    # Row 3: Nomor Aju, Nopen, Tanggal Daftar
    c7, c8, c9 = st.columns(3)
    with c7:
        j_nomor_aju = st.text_input("J. Nomor Aju", clean_aju(parsed["nomor_aju"]))
    with c8:
        l_nopen = st.text_input("L. Nopen", pad_nopen(parsed["nopen"]))
    with c9:
        m_tgl_daftar = st.text_input("M. Tanggal Daftar", parsed["tanggal_daftar"])

    st.divider()

    # Row 4: Surat Permohonan, Tanggal, Status
    c10, c11, c12 = st.columns(3)
    with c10:
        o_surat_perm = st.text_input("O. Surat Permohonan", parsed["surat_permohonan"])
    with c11:
        p_tgl_perm = st.text_input("P. Tanggal Surat Permohonan", parsed["tanggal_permohonan"])
    with c12:
        q_status = st.text_input("Q. Status Dokumen", parsed["status"])

    # Item Perbaikan
    r_item = st.text_area("R. Item Perbaikan", parsed["item_perbaikan"],
                          height=90)

    # ── Kolom manual (tidak diisi otomatis) ──
    st.subheader("✍️ Kolom Manual")
    PEGAWAI_LIST = [
        "Albertus Yudha Sanjaya",
        "Dian Meilinda",
        "Nuh Bachrudin Rizqi",
    ]
    c13, c14 = st.columns(2)
    with c13:
        b_pegawai = st.selectbox("B. Pegawai PDAD", PEGAWAI_LIST,
                                 index=None, placeholder="Pilih pegawai...",
                                 key="pegawai_select")
    with c14:
        st.caption("N. Aplikasi")
        st.text_input("tidak diisi (revisi)", value="", disabled=True,
                      key="aplikasi_disabled")

    # ── Save ──
    st.divider()
    save_col, msg_col = st.columns([1, 3])
    with save_col:
        save_btn = st.button("💾 Simpan ke File Lokal", type="primary",
                             use_container_width=True)

    if save_btn:
        if not b_pegawai:
            st.error("Isi dulu kolom B (Pegawai PDAD).")
            return

        # Build common values (cuma sekali)
        common_base = [
            b_pegawai,
            "",  # C File
            d_surat,
            e_tgl_surat,
            f_hal,
            g_tgl_diterima.strftime("%d-%m-%Y"),
            "",  # H Jenis
            i_perusahaan,
            "",  # K Kode Dokumen
            "",  # N Aplikasi
            o_surat_perm,
            p_tgl_perm,
        ]

        # Loop semua aju yg mau disimpan
        aju_list = parsed_list if is_multi else [{"nomor_aju": j_nomor_aju,
            "nopen": l_nopen, "tanggal_daftar": m_tgl_daftar,
            "status": q_status, "item_perbaikan": r_item,
            "surat_permohonan": o_surat_perm, "tanggal_permohonan": p_tgl_perm}]

        saved = 0
        for i, aju in enumerate(aju_list):
            values = [
                "",  # A No (dihitung otomatis)
                b_pegawai if i == 0 else b_pegawai,  # B
                "",  # C File
                d_surat,
                e_tgl_surat,
                f_hal,
                g_tgl_diterima.strftime("%d-%m-%Y"),
                "",  # H Jenis
                i_perusahaan,
                clean_aju(aju.get("nomor_aju", "")),
                "",  # K Kode Dokumen
                pad_nopen(aju.get("nopen", "")),
                aju.get("tanggal_daftar", ""),
                "",  # N Aplikasi
                aju.get("surat_permohonan", o_surat_perm),
                aju.get("tanggal_permohonan", p_tgl_perm),
                aju.get("status", q_status),
                aju.get("item_perbaikan", r_item),
            ]
            save_local(values)
            saved += 1

        # Simpan lokal — XLSX + CSV
        xlsx_bytes = build_xlsx_bytes(load_local_rows())
        st.success(f"✅ {saved} baris tersimpan ke file lokal!")

        # Tombol download langsung
        st.download_button(
            "⬇️ Download XLSX terbaru",
            data=xlsx_bytes,
            file_name="data_perbaikan.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        # Kirim ke Google Sheet via Apps Script (kalau URL sudah diisi)
        url_gs, _ = load_apps_script_config()
        SPREADSHEET_URL = ("https://docs.google.com/spreadsheets/d/"
                           "1Jvi7Ek8LynDr5dHdc0GBahqpwiKKv_v4d1u3l7RPZWw/edit")
        gs_saved = 0
        if url_gs:
            for aju in aju_list:
                vals = [
                    "", b_pegawai, "", d_surat, e_tgl_surat, f_hal,
                    g_tgl_diterima.strftime("%d-%m-%Y"), "", i_perusahaan,
                    clean_aju(aju.get("nomor_aju", "")), "", aju.get("nopen", ""),
                    aju.get("tanggal_daftar", ""), "",
                    aju.get("surat_permohonan", o_surat_perm),
                    aju.get("tanggal_permohonan", p_tgl_perm),
                    aju.get("status", q_status),
                    aju.get("item_perbaikan", r_item),
                ]
                ok, _ = send_to_apps_script(vals)
                if ok: gs_saved += 1
            if gs_saved:
                st.success(f"📤 {gs_saved}/{len(aju_list)} baris terkirim ke Google Sheet")
                st.markdown(f"🔗 [Buka Google Sheet]({SPREADSHEET_URL})")
            if gs_saved < len(aju_list):
                st.warning(f"⚠️ {len(aju_list) - gs_saved} gagal kirim ke Google Sheet")
        elif os.path.exists(SERVICE_ACCOUNT):
            try:
                append_row_gs(values)
                st.info("➕ Juga tersimpan ke Google Sheet.")
                st.markdown(f"🔗 [Buka Google Sheet]({SPREADSHEET_URL})")
            except Exception as e:
                st.warning(f"⚠️ Gagal simpan ke Google Sheet: {e}")
        else:
            st.info("ℹ️ URL Apps Script belum diisi — data hanya tersimpan lokal. "
                    "Isi `apps_script_config.json` untuk sinkron ke Google Sheet.")

        # Preview JSON
        with msg_col:
            st.json({k: v for k, v in zip(
                ["B Pegawai", "C File", "D Surat", "E Tgl Surat", "F Hal",
                 "G Tgl Diterima", "H Jenis", "I Perusahaan", "J Nomor Aju",
                 "K Kode", "L Nopen", "M Tgl Daftar", "N Aplikasi",
                 "O Surat Permohonan", "P Tgl Permohonan", "Q Status",
                 "R Item"],
                values[1:])})


def build_xlsx_bytes(rows):
    """Buat workbook XLSX dari rows → return bytes (untuk tombol download)."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill

    headers = ["No", "Pegawai PDAD", "File Surat Persetujuan",
               "Surat Persetujuan Kepala Kantor", "Tanggal Surat Persetujuan",
               "Hal Surat Persetujuan", "Tanggal diterima PDAD", "Jenis",
               "Perusahaan", "Nomor Aju", "Kode Dokumen", "Nopen",
               "Tanggal Daftar", "Aplikasi", "Surat Permohonan",
               "Tanggal Surat Permohonan", "Status Dokumen", "Item Perbaikan"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data Perbaikan"

    hdr_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    hdr_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    thin = openpyxl.styles.Border(
        left=openpyxl.styles.Side(style="thin"),
        right=openpyxl.styles.Side(style="thin"),
        top=openpyxl.styles.Side(style="thin"),
        bottom=openpyxl.styles.Side(style="thin"),
    )

    # Header
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin

    # Data — kolom teks dipaksa format text (@) biar gak scientific notation
    for i, r in enumerate(rows, 2):
        for c, h in enumerate(headers, 1):
            val = r.get(h, "")
            cell = ws.cell(row=i, column=c, value=val)
            cell.border = thin
            if c in TEXT_COLUMNS:
                cell.number_format = "@"  # paksa teks
                if val != "":
                    cell.value = str(val)

    # Column widths
    for c, w in enumerate([5, 18, 18, 28, 18, 40, 16, 12, 30, 26, 12, 14, 14, 10, 24, 22, 14, 50], 1):
        ws.column_dimensions[chr(64 + c)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def save_local(values):
    """Simpan ke XLSX (format teks utk nomor panjang) + CSV lokal."""
    import csv

    headers = ["No", "Pegawai PDAD", "File Surat Persetujuan",
               "Surat Persetujuan Kepala Kantor", "Tanggal Surat Persetujuan",
               "Hal Surat Persetujuan", "Tanggal diterima PDAD", "Jenis",
               "Perusahaan", "Nomor Aju", "Kode Dokumen", "Nopen",
               "Tanggal Daftar", "Aplikasi", "Surat Permohonan",
               "Tanggal Surat Permohonan", "Status Dokumen", "Item Perbaikan"]

    rows = load_local_rows()
    new_row = dict(zip(headers, values))
    new_row["No"] = len(rows) + 1
    rows.append(new_row)

    # ── XLSX (utama) ──
    xlsx_bytes = build_xlsx_bytes(rows)
    with open(OUTPUT_XLSX, "wb") as f:
        f.write(xlsx_bytes)

    # ── CSV (cadangan) ──
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    st.info(f"💾 Tersimpan: `{OUTPUT_XLSX}` (Nomor Aju & Nopen format teks)")
    return xlsx_bytes


def load_local_rows():
    import csv
    if not os.path.exists(OUTPUT_CSV):
        return []
    with open(OUTPUT_CSV) as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    main()
