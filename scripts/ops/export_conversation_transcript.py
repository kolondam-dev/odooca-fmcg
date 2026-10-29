#!/usr/bin/env python3
"""Eksportir Transkrip Percakapan Sesi Antigravity ke Format Markdown (.md).

Membaca transcript_full.jsonl dari .system_generated/logs dan menyusun dokumen
markdown terstruktur dan rapi yang mencakup:
1. Metadata Sesi (Conversation ID, Tanggal, Cabang, Konteks Bisnis)
2. Daftar Isi Giliran Percakapan (Turn 1 s/d Turn 13)
3. Rincian Dialog Utuh:
   - Permintaan Pengguna (User Request)
   - Tindakan & Tools yang Dijalankan (Tool Execution Summary)
   - Jawaban Lengkap Asisten (Antigravity Assistant Full Response)
   - Artefak, Berkas yang Diubah, dan Referensi Commit Git
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
LOG_FILE = pathlib.Path(
    r"C:\Users\ACER\.gemini\antigravity-ide\brain\c4cc6a4d-24e8-4632-8403-2e8f8c2c762f\.system_generated\logs\transcript_full.jsonl"
)
OUTPUT_MD = ROOT / "docs" / "reviews" / "FULL_CONVERSATION_TRANSCRIPT_2026-10-25.md"


def clean_user_text(raw_text: str) -> str:
    """Mengekstrak teks user request murni tanpa tag XML pembungkus."""
    if "<USER_REQUEST>" in raw_text and "</USER_REQUEST>" in raw_text:
        match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", raw_text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return raw_text.strip()


def export_transcript():
    if not LOG_FILE.exists():
        print(f"File log tidak ditemukan di {LOG_FILE}")
        return

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    turns = []
    current_turn = {
        "user": "",
        "user_meta": "",
        "assistant_chunks": [],
        "tools_called": [],
    }

    turn_counter = 1

    for r in records:
        rtype = r.get("type")
        rsrc = r.get("source")

        if rtype == "USER_INPUT" or rsrc == "USER_EXPLICIT":
            # Jika turn sebelumnya sudah punya isi user, simpan
            if current_turn["user"]:
                turns.append(current_turn)
                turn_counter += 1
            raw_content = r.get("content", "")
            meta_str = ""
            if "<ADDITIONAL_METADATA>" in raw_content:
                meta_match = re.search(r"<ADDITIONAL_METADATA>(.*?)</ADDITIONAL_METADATA>", raw_content, re.DOTALL)
                if meta_match:
                    meta_str = meta_match.group(1).strip()

            current_turn = {
                "turn_index": turn_counter,
                "user": clean_user_text(raw_content),
                "user_meta": meta_str,
                "assistant_chunks": [],
                "tools_called": [],
            }

        elif rtype == "PLANNER_RESPONSE":
            content = r.get("content", "")
            if content:
                current_turn["assistant_chunks"].append(content)
            for call in r.get("tool_calls", []):
                tname = call.get("name", "")
                targs = call.get("args", {})
                current_turn["tools_called"].append((tname, targs))

    if current_turn["user"]:
        turns.append(current_turn)

    # Susun Markdown
    md = []
    md.append("# TRANSKRIP LENGKAP PERCAKAPAN SESI AUDIT, GEOSPASIAL & REKONSTRUKSI DATA DEMO FMCG")
    md.append("")
    md.append("**Sesi Kerja:** Rekonstruksi Seed Audit, Integrasi Master Geospasial Sulut, PJP Matrix, Okupansi Armada, dan Granular Perpetual Inventory Turnover  ")
    md.append("**Tanggal Sesi:** 24 - 25 Oktober 2026  ")
    md.append("**ID Percakapan (Conversation ID):** `c4cc6a4d-24e8-4632-8403-2e8f8c2c762f`  ")
    md.append("**Agen Pelaksana:** `antigravity` (Google DeepMind)  ")
    md.append("**Cabang Kerja:** `agen/rekonstruksi-seed-audit` $\\to$ `agen/transaksi-historis-perpetual`  ")
    md.append("**Konteks Bisnis:** Odoo 19 CE + OCA 19.0 Distributor FMCG Manado (PT Manado Distribusi Utama), 4 Principal Nasional, 150 SKU, 354 Partner Outlet, 9 Armada Logistik.  ")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## DAFTAR ISI PERCAKAPAN (TABLE OF CONTENTS)")
    md.append("")

    turn_titles = [
        "Audit Komprehensif Temuan Drift Eksekusi Demo Data Terdahulu",
        "Penetapan Batasan: Prioritas Native Fields, Hari Kerja Senin-Sabtu, dan Rencana Rekonstruksi",
        "Penambahan Master Customer Register, Poligon Geospasial, Pemodelan PJP, dan Day-to-Day Local Ledger",
        "Integrasi Master Wilayah Sulut Presisi (Kepmendagri 2025, 2.026 Wilayah, MultiPolygon Riil)",
        "Permintaan Tabel Matrix PJP Bulan Juli 2026 Lengkap (Format CSV)",
        "Analisis Rasio Omset Per Call, ARPU Customer, Jarak KM Tempuh, dan Struktur Biaya Delivery",
        "Analisis Okupansi Harian Armada Logistik Secara Kubikasi (CBM) dan Tonase (Space-Constrained)",
        "Pertanyaan Sinkronisasi Inventory Turnover Line-by-Line, Kausalitas Dokumen, dan Payroll Tgl 30/31",
        "Arahan Tambahan: Saldo Awal 1 Juli, PO In-Transit, Divisi Resmi FMCG, Non-Genap, DPP, dan Mitigasi SVL",
        "Pengarsipan Keputusan Arsitektur, Panduan Rollback, dan Persiapan Branch Baru",
        "Konfirmasi Status Seeding Database Odoo (Belum Ada Injeksi Data)",
        "Pemeriksaan Sinkronisasi Seluruh Branch dan Git Push ke Remote Repository",
        "Permintaan Ekspor Transkrip Sesi Percakapan ke Format File Markdown (.md)",
    ]

    for idx, t in enumerate(turns, start=1):
        title = turn_titles[idx - 1] if idx - 1 < len(turn_titles) else f"Giliran Percakapan #{idx}"
        md.append(f"{idx}. [Turn {idx}: {title}](#turn-{idx}-{title.lower().replace(' ', '-').replace(':', '').replace('/', '').replace('(', '').replace(')', '').replace(',', '')})")

    md.append("")
    md.append("---")
    md.append("")

    for idx, t in enumerate(turns, start=1):
        title = turn_titles[idx - 1] if idx - 1 < len(turn_titles) else f"Giliran Percakapan #{idx}"
        anchor = f"turn-{idx}-{title.lower().replace(' ', '-').replace(':', '').replace('/', '').replace('(', '').replace(')', '').replace(',', '')}"
        md.append(f"## <a id=\"{anchor}\"></a>Turn {idx}: {title}")
        md.append("")

        # User Request
        md.append("### 👤 User (Pemilik Repository)")
        md.append("```")
        md.append(t["user"])
        md.append("```")
        md.append("")

        if t["user_meta"]:
            # Ringkas metadata waktu
            time_match = re.search(r"The current local time is: (.*?)\.", t["user_meta"])
            if time_match:
                md.append(f"*Waktu Pengiriman Pesan:* `{time_match.group(1)}`  ")
            md.append("")

        # Tools executed summary
        if t["tools_called"]:
            md.append(f"**Ringkasan Tindakan Sistem & Alat ({len(t['tools_called'])} aksi):**")
            tool_names = {}
            for tname, _ in t["tools_called"]:
                tool_names[tname] = tool_names.get(tname, 0) + 1
            summary_str = ", ".join([f"`{name}` ({cnt}x)" for name, cnt in tool_names.items()])
            md.append(f"- *Panggilan Alat:* {summary_str}")
            md.append("")

        # Assistant Response
        md.append("### 🤖 Antigravity Assistant")
        asst_text = "\n\n".join(t["assistant_chunks"]).strip()
        if asst_text:
            md.append(asst_text)
        else:
            md.append("*(Sedang memproses dan menyusun ekspor dokumen transkrip ini)*")

        md.append("")
        md.append("---")
        md.append("")

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Sukses mengekspor transkrip lengkap ({len(turns)} turns) ke {OUTPUT_MD}")
    print(f"Ukuran berkas: {OUTPUT_MD.stat().st_size:,} bytes")


if __name__ == "__main__":
    export_transcript()
