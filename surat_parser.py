#!/usr/bin/env python3
"""Parser Surat Persetujuan Kepala Kantor → field PDAD."""
import re
import fitz


def _join_names(names):
    """['JUMLAH SATUAN', 'NETTO'] -> 'Jumlah Satuan, dan Netto' (Title Case)."""
    names = [n.strip() for n in names if n.strip()]
    if not names:
        return ""
    pretty = [n.title() for n in names]
    if len(pretty) == 1:
        return pretty[0]
    return ", ".join(pretty[:-1]) + ", dan " + pretty[-1]


def parse_surat(text):
    """Parse Surat Persetujuan Kepala Kantor → dict field."""
    result = {}

    # D: Nomor surat — ambil nomor setelah "S-" saja (contoh: "1850" dari "S-1850/KBC.1102/2026")
    m = re.search(r'S-(\d+)', text)
    result["surat"] = m.group(1) if m else ""

    # E: Tanggal surat (beside nomor, Indonesian format)
    m = re.search(
        r'Nomor\s*\n?\s*:\s*\n?\s*[A-Z0-9\-/.]+[\s\n]*(\d{1,2}\s+\w+\s+\d{4})', text)
    result["tanggal_surat"] = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""

    # F: Hal
    m = re.search(r'Hal\s*\n?\s*:\s*\n?\s*(.+)', text)
    result["hal"] = m.group(1).strip() if m else ""

    # H: Jenis (Pembetulan/Pembatalan) — tidak diisi otomatis (revisi)
    result["jenis"] = ""

    # I: Perusahaan — from "Yth. Pimpinan X" or hal
    m = re.search(r'Yth\.\s*Pimpinan\s+(PT\.?\s*.+)', text)
    if not m:
        m = re.search(r'Hal\s*\n?\s*:\s*\n?\s*.+\s(PT\.?\s*.+)', text)
    result["perusahaan"] = m.group(1).strip() if m else ""

    # K: Kode Dokumen — "BC 4.0" or "BC 2.3" (dari "Jenis Dokumen TPB" atau "Pembetulan BC X.X")
    m = re.search(r'Jenis Dokumen TPB\s*\n?\s*:\s*\n?\s*BC\s*([\d.]+)', text)
    if not m:
        m = re.search(r'(?:Pembetulan|Pembatalan)\s+(?:Data\s+Dokumen\s+)?BC\s*([\d.]+)', text)
    result["kode_dokumen"] = m.group(1) if m else ""

    # J: Nomor Aju / Nomor Pengajuan — 2 format:
    #   A: 07134000643220260721001058 (26 digit)
    #   B: 000040-830962-20260727-000525 (dengan strip)
    m = re.search(r'Nomor Pengajuan\s*\n?\s*:\s*\n?\s*([0-9\-]+)', text)
    result["nomor_aju"] = m.group(1).strip('-') if m else ""

    # L, M: Nomor Pendaftaran / Tanggal — 2 format:
    #   A: "Nomor Pendaftaran / Tanggal : 002350 / 21-07-2026"
    #   B: "Nomol Pendaftaran : 002350" (typo asli) + "Tanggal Pendaftaran : 14 April 2026"
    m = re.search(
        r'Nomor Pendaftaran\s*/\s*Tanggal\s*\n?\s*:\s*\n?\s*(\d+)\s*/\s*(\d{2}-\d{2}-\d{4})',
        text)
    if m:
        result["nopen"] = m.group(1)
        result["tanggal_daftar"] = m.group(2)
    else:
        # Format B: Nomol/Nomor Pendaftaran (satu baris)
        m2 = re.search(r'(?:Nomor|Nomol)\s*Pendaftaran\s*\n?\s*:\s*\n?\s*(\d+)', text)
        result["nopen"] = m2.group(1) if m2 else ""
        # Tanggal Pendaftaran terpisah
        m3 = re.search(r'Tanggal\s*Pendaftaran\s*\n?\s*:\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
        if m3:
            result["tanggal_daftar"] = re.sub(r'\s+', ' ', m3.group(1)).strip()
        else:
            result["tanggal_daftar"] = ""

    # Q: Status Dokumen — ambil sampai akhir baris (bisa multi-kata: "Gate In TPB/KEK")
    m = re.search(r'Status Dokumen\s*\n?\s*:\s*\n?\s*(.+)', text)
    result["status"] = m.group(1).strip() if m else ""

    # O, P: Surat Permohonan & tanggal — case-insensitive (ada yang "nomor" kecil)
    m = re.search(
        r'surat Saudara\s+(?:Nomor|nomor)\s+(\S+)\s+tanggal\s+(\d{1,2}\s+\w+\s+\d{4})',
        text, re.IGNORECASE)
    if m:
        result["surat_permohonan"] = m.group(1)
        result["tanggal_permohonan"] = re.sub(r'\s+', ' ', m.group(2)).strip()
    else:
        result["surat_permohonan"] = ""
        result["tanggal_permohonan"] = ""

    # R: Item Perbaikan — ekstrak NAMA item saja (simple), beberapa format tabel:
    #   A: "ELEMEN DATA SEBELUMNYA SEHARUSNYA" (PDF Coats)
    #   B: "Menjadi/MENJADI/Terekam" dengan kolom KOLOM (PDF Tung Cia)
    #   C: "Menjadi" dengan kolom ELEMEN DATA (PDF Baramuda)
    m = re.search(
        r'ELEMEN DATA\s*\nSEBELUMNYA\s*\nSEHARUSNYA\s*\n(.+?)\n\s*\d+\.',
        text, re.DOTALL)
    if m:
        # Format A: "Kolom No. 29 No urut 1 – Jumlah\n1 PCE\n2 PCE" → ambil nama setelah "–"
        raw = m.group(1).strip()
        mm = re.search(r'–\s*([^\n]+)', raw)
        if mm:
            result["item_perbaikan"] = _join_names([mm.group(1)])
        else:
            result["item_perbaikan"] = re.sub(r'\s+', ' ', raw)
    else:
        # Format B & C: dari header "Menjadi/MENJADI/Terekam" sampai poin berikutnya
        m2 = re.search(r'(?:terekam|menjadi)\s*\n(.+?)\n\s*\d+\.\s*\n',
                       text, re.IGNORECASE | re.DOTALL)
        if m2:
            raw = m2.group(1).strip()
            lines = [ln.strip() for ln in raw.split('\n') if ln.strip()]
            # Skip header tabel jika muncul (No/KOLOM/SEBELUMNYA/MENJADI)
            skip_words = ('no', 'no urut', 'kolom', 'sebelumnya', 'menjadi',
                          'elemen data', 'terekam', 'urut', 'data')
            while lines and lines[0].lower() in skip_words:
                lines.pop(0)

            if re.search(r'KOLOM\s*\nSEBELUMNYA\s*\nMENJADI', text, re.IGNORECASE):
                # Format B (Tung Cia): tiap 4 baris = No, KOLOM, SEBELUMNYA, MENJADI
                names = lines[1::4]
                result["item_perbaikan"] = _join_names(names)
            else:
                # Format C (Baramuda): nama elemen = baris yg diikuti angka/baris kecil
                names = []
                i = 0
                while i < len(lines):
                    nxt = lines[i + 1] if i + 1 < len(lines) else ""
                    cur = lines[i]
                    is_num = re.fullmatch(r'[\d.,\s]+', nxt or "")
                    is_lower = bool(nxt) and nxt[0].islower()
                    if (is_num or is_lower) and not re.fullmatch(r'[\d.,\s]+', cur):
                        name = cur
                        if is_lower:
                            name += " " + nxt
                            i += 1
                        names.append(name)
                    i += 1
                result["item_perbaikan"] = _join_names(names) if names else " | ".join(lines)
        else:
            m3 = re.search(r'dilakukan pembetulan\s*:\s*\n(.+?)\n\s*\d+\.\s*\n',
                           text, re.DOTALL)
            result["item_perbaikan"] = re.sub(r'\s+', ' ', m3.group(1)).strip() if m3 else ""

    return result


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    r = parse_surat(text)
    for k, v in r.items():
        print(f"  {k:20s} = {v}")
