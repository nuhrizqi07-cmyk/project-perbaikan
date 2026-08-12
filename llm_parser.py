#!/usr/bin/env python3
"""LLM-based parser for Surat Persetujuan — fallback when regex fails.
Uses DeepSeek API (OpenAI-compatible endpoint)."""

import json
import os
import re

# ── Konfigurasi ──
DEEPSEEK_MODEL = "deepseek-chat"  # V3 — cepat, murah, akurat untuk ekstraksi

def _get_api_key():
    """Ambient: Streamlit Secrets → env → hardcoded (local dev)."""
    try:
        import streamlit as st
        key = st.secrets.get("DEEPSEEK_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    # Fallback lokal (ganti atau override via env/Secrets)
    return "sk-72ba6276b8184436bec2f86cf0701445"


PROMPT_TEMPLATE = """Kamu asisten Bea Cukai yang mengekstrak data dari surat persetujuan pembetulan/pembatalan dokumen TPB.

Ekstrak SEMUA field berikut dari teks surat. Kalau field tidak ada, isi "" (string kosong).

BALAS HANYA JSON array. Satu elemen = satu nomor aju. Tanpa markdown, tanpa penjelasan apa pun.

[{
  "surat": "1924",
  "tanggal_surat": "10 Agustus 2026",
  "hal": "Persetujuan Pembetulan Data Dokumen TPB (BC 2.3)",
  "perusahaan": "Fronte Classic Indonesia",
  "aju": "000023-010832-20260728-000115",
  "nopen": "006057",
  "tanggal_daftar": "28-07-2026",
  "aplikasi": "CEISA 4.0",
  "status": "Gate In TPB/KEK",
  "surat_permohonan": "090/FCI/G/Ex/VIII/2026",
  "tanggal_permohonan": "4 Agustus 2026",
  "item_perbaikan": "Nilai CIF, Uraian Barang, Jumlah Nilai CIF, BM, BMT, PPN, PPh, TOTAL"
}]

ATURAN EKSTRAKSI:
- "surat": hanya angka setelah "S-" (contoh: "1924" dari "S-1924/KBC.1102/2026")
- "perusahaan": nama saja, HAPUS "PT.", "CV.", "PD." di depan, Title Case. Contoh: "Fronte Classic Indonesia"
- "aju": format lengkap dengan tanda hubung (000023-010832-20260728-000115), dari "Nomor Pengajuan"
- "nopen": angka saja dari "Nomor Pendaftaran", tanpa spasi
- "tanggal_surat" / "tanggal_daftar" / "tanggal_permohonan": format asli dari surat (contoh: "10 Agustus 2026" atau "28-07-2026")
- "item_perbaikan": nama kolom yang dibetulkan dari tabel Elemen Data, Title Case, dipisah koma. Contoh: "Nilai CIF, Uraian Barang, BM, BMT"
- "aplikasi": "CEISA 4.0" atau "CEISA TPB", dari konteks surat
- "status": dari "Status pada CEISA 4.0" atau "Status Dokumen", contoh: "Gate In TPB/KEK", "SPPD"

Teks surat:
---AWAL---
{text}
---AKHIR---"""


def parse_with_llm(text: str) -> list[dict]:
    """Parse surat dengan DeepSeek LLM.
    Return: list of dicts (format sama dengan parse_surat regex),
            atau list kosong [] kalau gagal.
    """
    import openai

    api_key = _get_api_key()
    if not api_key:
        return []

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": PROMPT_TEMPLATE.replace("{text}", text)}],
            temperature=0,
            max_tokens=3000,
        )
        content = resp.choices[0].message.content

        # Bersihkan markdown wrapper (LLM kadang "bandel" bungkus JSON)
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content.strip())

        data = json.loads(content)
        if isinstance(data, dict):
            data = [data]

        return data

    except json.JSONDecodeError:
        return []
    except Exception as e:
        print(f"[llm_parser] API error: {e}")
        return []


if __name__ == "__main__":
    import sys, fitz
    path = sys.argv[1]
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    results = parse_with_llm(text)
    print(f"Ditemukan {len(results)} aju via LLM:\n")
    for i, r in enumerate(results):
        print(f"--- Aju #{i+1} ---")
        for k, v in r.items():
            print(f"  {k:24s} = {v}")
