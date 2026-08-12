#!/usr/bin/env python3
"""Parser Surat Persetujuan Kepala Kantor → field PDAD.
v2: Support multi-aju dalam satu surat (list of dicts)."""
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


def _extract_common_fields(text):
    """Extract fields that are the same for all aju in the surat."""
    result = {}

    # D: Nomor surat — ambil nomor setelah "S-" saja (contoh: "1502" dari "S-1502/KBC.1102/2026")
    m = re.search(r'S-(\d+)', text)
    result["surat"] = m.group(1) if m else ""

    # E: Tanggal surat
    m = re.search(
        r'Nomor\s*\n?\s*:\s*\n?\s*[A-Z0-9\-/.]+[\s\n]*(\d{1,2}\s+\w+\s+\d{4})', text)
    result["tanggal_surat"] = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ""

    # F: Hal
    m = re.search(r'Hal\s*\n?\s*:\s*\n?\s*(.+)', text)
    result["hal"] = m.group(1).strip() if m else ""

    # H: Jenis — tidak diisi otomatis
    result["jenis"] = ""

    # I: Perusahaan
    m = re.search(r'Yth\.\s*Pimpinan\s+(PT\.?\s*.+)', text)
    if not m:
        m = re.search(r'Hal\s*\n?\s*:\s*\n?\s*.+\s(PT\.?\s*.+)', text)
    result["perusahaan"] = m.group(1).strip() if m else ""
    # Cleanup: hapus prefix "PT.", "PT ", lalu Title Case
    result["perusahaan"] = re.sub(r'^(PT\.?|CV\.?|PD\.?)\s+', '',
                                   result["perusahaan"], flags=re.IGNORECASE).strip()
    # Title Case (kapital di awal kata)
    result["perusahaan"] = " ".join(w.strip().title() for w in result["perusahaan"].split() if w.strip())

    # K: Kode Dokumen
    m = re.search(r'Jenis Dokumen TPB\s*\n?\s*:\s*\n?\s*BC\s*([\d.]+)', text)
    if not m:
        m = re.search(r'(?:Pembetulan|Pembatalan)\s+(?:Data\s+Dokumen\s+)?BC\s*([\d.]+)', text)
    result["kode_dokumen"] = m.group(1) if m else ""

    return result


def _extract_ajo_block(text):
    """Extract one aju's fields from a text block starting at 'Nomor Pengajuan'."""
    result = {}

    # J: Nomor Aju
    m = re.search(r'Nomor Pengajuan\s*\n?\s*:\s*\n?\s*([0-9\-]+)', text)
    result["nomor_aju"] = m.group(1).strip('-') if m else ""

    # L, M: Nomor Pendaftaran / Tanggal
    m = re.search(
        r'Nomor Pendaftaran\s*/?\s*Tanggal\s*\n?\s*:\s*\n?\s*(\d+)\s*/?\s*(\d{2}-\d{2}-\d{4})',
        text)
    if m:
        result["nopen"] = m.group(1)
        result["tanggal_daftar"] = m.group(2)
    else:
        m2 = re.search(r'(?:Nomor|Nomol)\s*Pendaftaran\s*\n?\s*:\s*\n?\s*(\d+)', text)
        result["nopen"] = m2.group(1) if m2 else ""
        m3 = re.search(r'Tanggal\s*Pendaftaran\s*\n?\s*:\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
        if m3:
            result["tanggal_daftar"] = re.sub(r'\s+', ' ', m3.group(1)).strip()
        else:
            result["tanggal_daftar"] = ""

    # Q: Status Dokumen — cover 2 varian: "Status Dokumen : X" atau "Status pada CEISA 4.0 : X"
    m = re.search(r'Status\s+(?:Dokumen|pada\s+CEISA\s*4\.0)\s*\\n?\s*:\s*\\n?\s*(.+)', text)
    result["status"] = m.group(1).strip() if m else ""

    # R: Item Perbaikan — ambil NAMA kolom dari tabel "Elemen data..."
    item_names = []
    # Cari tabel "Elemen data" — stop di: aju berikutnya, permohonan, atau dokumen penutup
    table_pattern = re.compile(
        r'Elemen data yang disetujui untuk dilakukan pembetulan\s*:\s*\n(.+?)(?=\n\s*'
        r'(?:►|Nomor Pengajuan|Jenis Dokumen TPB|\d+\.[ \t]*(?=[A-Z])'
        r'|Plt\.|Ditandatangani|Dokumen ini telah)'
        r'|$)',
        re.DOTALL | re.IGNORECASE)
    for m_table in table_pattern.finditer(text):
        table_text = m_table.group(1)
        # Ekstrak nama kolom — format: "No  KOLOM  SEBELUMNYA  MENJADI"
        lines = [ln.strip() for ln in table_text.split('\n') if ln.strip()]
        # Filter: buang baris "Elemen data..." yang nyelip (header tabel ke-2)
        lines = [ln for ln in lines if not ln.lower().startswith('elemen data')]
        skip_set = {'no', 'no urut', 'kolom', 'sebelumnya', 'menjadi', 'elemen data',
                    'terekam', 'urut', 'data'}
        # Format Tung Cia: tiap grup 4 baris = No, KOLOM, SEBELUMNYA, MENJADI
        if any('KOLOM' in ln.upper() and 'SEBELUMNYA' in table_text.upper() for ln in lines[:5]):
            # Ambil nama dari posisi KOLOM (baris ke-1 dari setiap grup 4)
            for i in range(0, len(lines), 4):
                if i + 1 < len(lines) and lines[i+1].lower() not in skip_set:
                    item_names.append(lines[i+1])
        else:
            # Format lain: tiap grup 4 baris = No, nama kolom, SEBELUMNYA, MENJADI
            for i in range(0, len(lines), 4):
                if i + 1 < len(lines):
                    name = lines[i+1]
                    if name.lower() not in skip_set and not re.fullmatch(r'[\d.,\s]+', name):
                        item_names.append(name)

    # Dedupe + join + cleanup trailing numbers
    seen = set()
    unique = []
    for n in item_names:
        if n.lower() not in seen:
            seen.add(n.lower())
            unique.append(n)
    result["item_perbaikan"] = _join_names(unique)
    # Cleanup: hapus ", dan X." di ekor (sisa marker aju berikutnya)
    result["item_perbaikan"] = re.sub(r',?\s*dan\s+\d+\.?\s*$', '',
                                       result["item_perbaikan"])

    return result


def _extract_zero_permohonan(text):
    """Extract surat_permohonan & tanggal from '► Nomor Permohonan' marker."""
    m = re.search(
        r'►?\s*Nomor\s*Permohonan\s*:\s*(\S+)\s*Tanggal\s*(\d{1,2}\s+\w+\s+\d{4})',
        text, re.IGNORECASE)
    if m:
        return m.group(1), re.sub(r'\s+', ' ', m.group(2)).strip()
    # Fallback: "surat Saudara nomor X tanggal Y"
    m = re.search(
        r'surat Saudara\s+(?:Nomor|nomor)\s+(\S+)\s+tanggal\s+(\d{1,2}\s+\w+\s+\d{4})',
        text, re.IGNORECASE)
    if m:
        return m.group(1), re.sub(r'\s+', ' ', m.group(2)).strip()
    return "", ""


def parse_surat(text):
    """Parse Surat Persetujuan → list of dicts, satu dict per aju.
    Kalau gak ada multi-aju, balikin list dgn 1 elemen (backward-compat)."""
    common = _extract_common_fields(text)
    results = []

    # Cari semua blok "Nomor Pengajuan" — satu per aju
    aju_pattern = re.compile(r'Nomor Pengajuan\s*\n?\s*:')
    positions = [m.start() for m in aju_pattern.finditer(text)]

    if not positions:
        # Fallback: parsing cara lama (single)
        result = dict(common)
        # Isi field single
        single = _extract_ajo_block(text)
        result.update(single)
        surat_oh, tgl_oh = _extract_zero_permohonan(text)
        result["surat_permohonan"] = surat_oh
        result["tanggal_permohonan"] = tgl_oh
        return [result]

    # Multi-aju: ekstrak setiap blok
    for i, pos in enumerate(positions):
        start = pos
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        block = text[start:end]

        result = dict(common)
        result.update(_extract_ajo_block(block))

        # Cari permohonan terdekat sebelum blok ini
        before = text[:start]
        perm_matches = list(re.finditer(
            r'►?\s*Nomor\s*Permohonan\s*:\s*(\S+)\s*Tanggal\s*(\d{1,2}\s+\w+\s+\d{4})',
            before, re.IGNORECASE))
        if perm_matches:
            last_perm = perm_matches[-1]
            result["surat_permohonan"] = last_perm.group(1)
            result["tanggal_permohonan"] = re.sub(r'\s+', ' ', last_perm.group(2)).strip()
        else:
            result["surat_permohonan"] = ""
            result["tanggal_permohonan"] = ""

        results.append(result)

    # ── LLM Fallback: kalau regex nggak nemu aju sama sekali ──
    # (format surat baru / luar biasa → pakai AI)
    if not results or all(r.get("nomor_aju", "") == "" for r in results):
        try:
            from llm_parser import parse_with_llm
            llm_results = parse_with_llm(text)
            if llm_results:
                normalized = []
                for lr in llm_results:
                    r = dict(common)
                    # Field per-aju
                    r["nomor_aju"] = lr.get("aju", "")
                    r["nopen"] = str(lr.get("nopen", ""))
                    r["tanggal_daftar"] = lr.get("tanggal_daftar", "")
                    r["status"] = lr.get("status", "")
                    r["item_perbaikan"] = lr.get("item_perbaikan", "")
                    r["surat_permohonan"] = lr.get("surat_permohonan", "")
                    r["tanggal_permohonan"] = lr.get("tanggal_permohonan", "")
                    # Override common fields kalau LLM kasih nilai lebih baik
                    if lr.get("surat"):
                        r["surat"] = lr["surat"]
                    if lr.get("tanggal_surat"):
                        r["tanggal_surat"] = lr["tanggal_surat"]
                    if lr.get("hal"):
                        r["hal"] = lr["hal"]
                    if lr.get("perusahaan"):
                        r["perusahaan"] = lr["perusahaan"]
                    normalized.append(r)
                return normalized
        except ImportError:
            pass  # openai belum terinstall → skip LLM fallback

    return results


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    results = parse_surat(text)
    print(f"Found {len(results)} aju:\n")
    for i, r in enumerate(results):
        print(f"--- Aju #{i+1} ---")
        for k, v in r.items():
            print(f"  {k:22s} = {v}")
