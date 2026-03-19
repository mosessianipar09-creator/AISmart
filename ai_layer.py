"""
ai_layer.py
===========
Tanggung jawab:
  - Inisialisasi & koneksi ke Gemini AI model
  - Semua fungsi pembuat prompt (prompt engineering)
  - Fungsi publik: model, build_analysis_prompt(),
                   build_summary_prompt(), build_critique_prompt()

Cara import di app.py:
  from ai_layer import model, build_analysis_prompt,
                       build_summary_prompt, build_critique_prompt
"""

import os
import streamlit as st
import google.generativeai as genai

# ─────────────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────────────

os.environ["GOOGLE_API_USE_MTLS_ENDPOINT"] = "never"

API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)


# ─────────────────────────────────────────────────────
# INISIALISASI MODEL
# ─────────────────────────────────────────────────────

@st.cache_resource
def get_active_model():
    """
    Pilih model Gemini terbaik yang tersedia secara otomatis.
    Urutan prioritas: gemini-1.5-flash → gemini-1.5-pro → gemini-pro → model pertama available.
    Returns None jika tidak ada model yang bisa digunakan.
    """
    try:
        available = [
            m.name for m in genai.list_models()
            if 'generateContent' in m.supported_generation_methods
        ]
        for target in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']:
            if target in available:
                return genai.GenerativeModel(model_name=target)
        return genai.GenerativeModel(model_name=available[0]) if available else None
    except Exception:
        return None


# Singleton model — langsung tersedia saat modul di-import
model = get_active_model()


# ─────────────────────────────────────────────────────
# PROMPT BUILDERS
# ─────────────────────────────────────────────────────

def build_analysis_prompt(topic: str, papers: list[dict]) -> str:
    """
    Buat prompt analisis strategis berdasarkan daftar paper nyata.
    AI hanya boleh mereferensikan paper yang ada di daftar.
    """
    paper_summaries = []
    for i, p in enumerate(papers, 1):
        paper_summaries.append(
            f"[Paper {i}]\n"
            f"  Judul  : {p['title']}\n"
            f"  Penulis: {p['authors']}\n"
            f"  Tahun  : {p['year']}\n"
            f"  Sitasi : {p['citations']}\n"
            f"  Venue  : {p['venue']}\n"
            f"  Abstrak: {p['abstract'][:500]}..."
        )

    return f"""Kamu adalah asisten riset ilmiah senior.

ATURAN KERAS:
1. JANGAN menginvent judul paper, nama penulis, atau angka sitasi yang tidak ada di daftar.
2. Semua referensi harus pakai notasi [Paper N].
3. Pisahkan FAKTA (dari data) vs INFERENSI (analisismu).

TOPIK: "{topic}"
SUMBER DATA: {papers[0].get('source', 'Unknown')}

DATA PAPER:
{"".join(chr(10).join(paper_summaries))}

FORMAT OUTPUT WAJIB:

## 📊 Gambaran Umum
[Pola umum: periode, venue dominan, rentang sitasi]

## 🔍 Tren Utama
[3-5 tren dari abstrak, dengan referensi [Paper N]]

## 🕳️ Research Gap
[2-3 celah riset yang belum dijawab — ini INFERENSImu]

## 💡 Judul Penelitian Baru
[3 judul orisinal yang menjawab gap di atas]

## ⚠️ Limitasi Analisis
[Keterbatasan: jumlah paper, potensi bias, dll]"""


def build_summary_prompt(raw_text: str) -> str:
    """
    Buat prompt ringkasan eksekutif paper ilmiah dari teks mentah PDF.
    Membatasi input ke 8000 karakter pertama untuk efisiensi token.
    """
    return f"""Ringkas paper ilmiah ini:

## 🎯 Satu Kalimat Inti
## 🔬 Tujuan & Pertanyaan Riset
## 📐 Metode
## 📊 Hasil Utama
## ✅ Kesimpulan
## 🔮 Implikasi

Jangan tambahkan info yang tidak ada di teks.

TEKS:
{raw_text[:8000]}"""


def build_critique_prompt(raw_text: str) -> str:
    """
    Buat prompt analisis kritis (peer review) paper ilmiah dari teks mentah PDF.
    Membatasi input ke 8000 karakter pertama untuk efisiensi token.
    """
    return f"""Kamu adalah peer reviewer jurnal Q1.

## 🔬 Ringkasan Metodologi
## ⚠️ Kelemahan Metodologis
## 🎯 Bias yang Teridentifikasi
## ❌ Klaim Berlebihan
## 📋 Verdict (Accept/Minor/Major Revision/Reject + alasan)

TEKS:
{raw_text[:8000]}"""
