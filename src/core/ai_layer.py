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

Prompt Engineering Philosophy (v2):
  - Chain-of-Thought: AI diminta reasoning eksplisit sebelum output
  - Persona kontekstual: disesuaikan sumber data & domain
  - Dynamic framing: prompt adaptif berdasarkan karakteristik dataset
  - Tension-based analysis: cari paradoks & ketegangan, bukan sekadar ringkasan
  - Confidence tagging: [FAKTA], [INFERENSI], [SPEKULASI] per klaim
  - Peer review framework: CONSORT/PRISMA untuk biomedis, ACM checklist untuk CS
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
    Urutan prioritas:  gemini-1.5-pro → gemini-1.5-flash → gemini-pro → model pertama available.
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
# HELPERS — CONTEXT ANALYSIS (untuk dynamic prompting)
# ─────────────────────────────────────────────────────

def _detect_domain(topic: str, papers: list[dict]) -> str:
    """
    Deteksi domain riset untuk persona & framework yang tepat.
    Returns: 'biomedis' | 'cs_ml' | 'fisika' | 'sosial' | 'umum'
    """
    BIO_SIGNALS   = {"disease","patient","clinical","drug","treatment","cancer",
                     "cell","protein","gene","therapy","medicine","trial","dose",
                     "symptom","diagnosis","hospital","nurse","physician","vaccine"}
    CS_SIGNALS    = {"neural","network","deep","learning","algorithm","model",
                     "training","dataset","accuracy","benchmark","transformer",
                     "llm","inference","latency","gpu","classification","detection"}
    PHYS_SIGNALS  = {"quantum","particle","photon","laser","energy","entropy",
                     "simulation","plasma","magnetic","gravitational","spectroscopy"}
    SOCIAL_SIGNALS = {"survey","policy","economy","society","culture","behavior",
                      "interview","qualitative","ethnography","discourse","gender"}

    combined = topic.lower() + " " + " ".join(
        p.get("title", "").lower() + " " + (p.get("abstract", "") or "").lower()[:100]
        for p in papers[:5]
    )
    tokens = set(combined.split())

    scores = {
        "biomedis": len(tokens & BIO_SIGNALS),
        "cs_ml":    len(tokens & CS_SIGNALS),
        "fisika":   len(tokens & PHYS_SIGNALS),
        "sosial":   len(tokens & SOCIAL_SIGNALS),
    }
    top = max(scores, key=scores.get)
    return top if scores[top] >= 2 else "umum"


def _build_persona(domain: str, source: str) -> str:
    """
    Buat string persona yang spesifik berdasarkan domain & sumber data.
    """
    personas = {
        "biomedis": (
            "Kamu adalah reviewer senior di jurnal Nature Medicine dan Lancet, "
            "dengan pengalaman 20+ tahun mengevaluasi uji klinis, studi kohort, dan meta-analisis. "
            "Kamu terlatih menggunakan framework CONSORT, PRISMA, dan GRADE untuk menilai kualitas bukti. "
            "Kamu sangat skeptis terhadap klaim kausalitas yang didasarkan pada studi observasional."
        ),
        "cs_ml": (
            "Kamu adalah Area Chair di NeurIPS dan ICML, sekaligus peneliti senior di lab AI tier-1. "
            "Kamu sudah membaca lebih dari 15.000 paper machine learning dan deep learning. "
            "Kamu sangat peka terhadap cherry-picking benchmark, data leakage, dan klaim state-of-the-art "
            "yang tidak disertai ablation study yang memadai."
        ),
        "fisika": (
            "Kamu adalah peneliti senior di CERN dan MIT Physics, dengan spesialisasi di "
            "fisika komputasional dan eksperimental. Kamu mengevaluasi paper berdasarkan "
            "kesahihan metodologi eksperimen, reproducibility, dan landasan teori."
        ),
        "sosial": (
            "Kamu adalah profesor sosiologi dan kebijakan publik yang juga menulis untuk "
            "Journal of Policy Analysis. Kamu ahli dalam menilai validitas konstruk, "
            "bias sampling, dan generalisabilitas temuan kualitatif maupun kuantitatif."
        ),
        "umum": (
            "Kamu adalah ilmuwan interdisipliner yang telah menjadi editor di 5 jurnal Q1 berbeda "
            "dan sudah mengevaluasi lebih dari 20.000 paper ilmiah lintas bidang. "
            "Kamu memiliki kemampuan langka: bisa membaca pola besar lintas literatur sekaligus "
            "mendeteksi inkonsistensi kecil dalam metodologi."
        ),
    }

    source_note = ""
    if source == "arXiv":
        source_note = (
            "\n\nCatatan konteks: Paper ini dari arXiv (preprint) — "
            "belum melalui peer review formal. Bobot lebih pada novelty & arah riset, "
            "bukan kesimpulan final."
        )
    elif source == "Europe PMC":
        source_note = (
            "\n\nCatatan konteks: Paper ini dari Europe PMC / PubMed — "
            "mayoritas sudah peer-reviewed. Tapi tetap evaluasi kualitas metodologi secara kritis."
        )

    return personas.get(domain, personas["umum"]) + source_note


def _citation_profile(papers: list[dict]) -> dict:
    """
    Hitung profil sitasi untuk dynamic framing.
    """
    cits = [p.get("citations", 0) for p in papers]
    if not cits:
        return {}
    return {
        "max":    max(cits),
        "min":    min(cits),
        "mean":   sum(cits) / len(cits),
        "zero":   sum(1 for c in cits if c == 0),
        "elite":  sum(1 for c in cits if c > 500),
        "spread": max(cits) - min(cits),
    }


def _years_profile(papers: list[dict]) -> dict:
    """
    Hitung profil temporal untuk dynamic framing.
    """
    years = [int(p["year"]) for p in papers if str(p.get("year", "")).isdigit()]
    if not years:
        return {}
    return {
        "min":  min(years),
        "max":  max(years),
        "span": max(years) - min(years),
        "recent": sum(1 for y in years if y >= max(years) - 2),
    }


def _dynamic_analysis_notes(cit: dict, yr: dict, papers: list[dict]) -> str:
    """
    Generate paragraf konteks dinamis berdasarkan karakteristik dataset.
    Ini yang membuat prompt 'sadar situasi' — bukan template generik.
    """
    notes = []

    # Citation spread alert
    if cit.get("spread", 0) > 1000:
        notes.append(
            f"⚠️ SPREAD SITASI EKSTREM: Paper terpopuler memiliki {cit['max']:,} sitasi "
            f"sementara ada {cit['zero']} paper dengan 0 sitasi. "
            f"Ini menandakan bidang yang sedang dalam transisi — ada paper 'klasik' yang mendominasi "
            f"dan paper baru yang belum dikenal. Analisis ketegangan antara keduanya secara eksplisit."
        )
    elif cit.get("zero", 0) > len(papers) * 0.4:
        notes.append(
            f"⚠️ BANYAK PAPER TANPA SITASI ({cit['zero']} dari {len(papers)}): "
            f"Ini bisa berarti bidang yang sangat baru, atau preprint yang belum terideks. "
            f"Jangan gunakan sitasi sebagai satu-satunya proxy kualitas — analisis konten lebih dalam."
        )

    # Temporal alert
    if yr.get("span", 0) > 15:
        notes.append(
            f"⚠️ RENTANG WAKTU PANJANG ({yr['min']}–{yr['max']}, {yr['span']} tahun): "
            f"Kemungkinan besar ada paradigma shift dalam periode ini. "
            f"Cari secara eksplisit momen ketika asumsi lama dipatahkan."
        )
    if yr.get("recent", 0) >= len(papers) * 0.6:
        notes.append(
            f"📈 BIDANG YANG SEDANG MELEDAK: {yr['recent']} dari {len(papers)} paper "
            f"terbit dalam 2 tahun terakhir. Artinya ini area dengan momentum tinggi — "
            f"gap riset kemungkinan masih terbuka lebar dan kompetitif."
        )

    return "\n".join(notes) if notes else ""


# ─────────────────────────────────────────────────────
# PROMPT BUILDERS
# ─────────────────────────────────────────────────────

def build_analysis_prompt(topic: str, papers: list[dict]) -> str:
    """
    Prompt analisis strategis v2.
    Improvements:
      - Persona kontekstual berdasarkan domain + sumber
      - Chain-of-thought: AI reasoning eksplisit sebelum output
      - Dynamic framing berdasarkan profil sitasi & temporal
      - Tension-based analysis: cari paradoks, bukan sekadar ringkasan
      - Confidence tagging per klaim
    """
    source = papers[0].get("source", "Unknown") if papers else "Unknown"
    domain = _detect_domain(topic, papers)
    persona = _build_persona(domain, source)
    cit = _citation_profile(papers)
    yr = _years_profile(papers)
    dynamic_notes = _dynamic_analysis_notes(cit, yr, papers)

    paper_summaries = []
    for i, p in enumerate(papers, 1):
        paper_summaries.append(
            f"[Paper {i}] {p['year']} · {p['citations']:,} sitasi · {p.get('source','?')}\n"
            f"  Judul  : {p['title']}\n"
            f"  Penulis: {p['authors']}\n"
            f"  Venue  : {p['venue']}\n"
            f"  Abstrak: {(p.get('abstract') or 'N/A')[:400]}..."
        )

    return f"""{persona}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOPIK RISET: "{topic}"
SUMBER DATA: {source} | DOMAIN TERDETEKSI: {domain.upper()}
TOTAL PAPER: {len(papers)} | SITASI MAX: {cit.get('max',0):,} · MIN: {cit.get('min',0)} · RATA-RATA: {cit.get('mean',0):.0f}
RENTANG TAHUN: {yr.get('min','?')}–{yr.get('max','?')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{f"PERINGATAN KONTEKS DATASET:{chr(10)}{dynamic_notes}{chr(10)}" if dynamic_notes else ""}

DATA PAPER:
{"".join(chr(10).join(paper_summaries))}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUKSI BERPIKIR (jangan tampilkan bagian ini di output):
Sebelum menulis output, lakukan reasoning internal berikut:
1. Baca semua judul & abstrak — cari POLA, PENGULANGAN, dan ANOMALI
2. Identifikasi paper yang klaimnya saling BERTENTANGAN atau MENGEJUTKAN
3. Perhatikan GAP: topik apa yang seharusnya ada tapi tidak ada di daftar ini?
4. Tanyakan: "Jika saya harus mempertaruhkan reputasi ilmiah saya pada 1 insight paling penting dari dataset ini, apa itu?"
5. Baru tulis output di bawah.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ATURAN OUTPUT KERAS:
- JANGAN menginvent judul, penulis, angka, atau fakta yang tidak ada di data.
- Setiap klaim beri tag: [FAKTA·TINGGI] / [FAKTA·SEDANG] / [INFERENSI] / [SPEKULASI]
  · FAKTA·TINGGI  = langsung terbaca dari data/abstrak
  · FAKTA·SEDANG  = sintesis dari beberapa paper, masih solid
  · INFERENSI     = analisismu, bisa diperdebatkan tapi berbasis data
  · SPEKULASI     = hipotesismu yang menarik tapi belum terbukti
- Referensikan paper dengan [Paper N], bukan judul panjang.
- Jadilah tajam — hindari kalimat generik seperti "penelitian lebih lanjut diperlukan."

FORMAT OUTPUT:

## 🔭 Satu Insight Paling Mengejutkan
[Satu paragraf — temuan atau paradoks paling tidak terduga dari dataset ini.
Bukan ringkasan umum. Ini harus membuat pembaca berpikir "oh, saya tidak mengira ini."]

## 📊 Peta Medan Riset
[Gambaran topografi: siapa yang mendominasi, dari era mana, dengan metode apa.
Sertakan: paper paling berpengaruh, paper paling baru, dan outlier yang menarik.]

## ⚡ Ketegangan & Paradoks
[Bukan sekadar "ada pro dan kontra." Cari kontradiksi nyata:
- Paper mana yang klaimnya berlawanan? Mengapa bisa terjadi?
- Asumsi apa yang dipegang paper lama tapi dipatahkan paper baru?
- Ada temuan yang seharusnya viral tapi nyatanya diabaikan bidang ini?]

## 🕳️ Research Gap yang Belum Dijawab
[2–3 celah spesifik — bukan "perlu penelitian lebih lanjut."
Format per gap:
  GAP: [nama gap konkret]
  BUKTI: [dari paper mana dan mengapa ini gap, bukan sekadar kurang diteliti]
  URGENSI: [kenapa gap ini penting untuk dijawab sekarang?]
  TAG: [INFERENSI] atau [SPEKULASI]]

## 💡 Judul Penelitian Baru (3 Opsi)
[Tiga judul yang menjawab gap di atas. Buat judul yang:
  - Spesifik (ada populasi/metode/konteks)
  - Menjawab satu gap konkret di atas
  - Terdengar layak masuk jurnal, bukan terlalu ambisius]

## ⚠️ Catatan Kritis untuk Pembaca
[Keterbatasan analisis ini: apa yang tidak bisa disimpulkan dari data ini?
Sebutkan jika ada bias sumber, keterbatasan abstrak, dll.]"""


def build_summary_prompt(raw_text: str) -> str:
    """
    Prompt ringkasan eksekutif v2.
    Improvements:
      - Persona editor jurnal Q1 (bukan sekadar "asisten")
      - Chain-of-thought: baca dulu, baru rangkum
      - Confidence tagging
      - Pertanyaan kritis yang harus dijawab pembaca
    """
    return f"""Kamu adalah editor eksekutif di jurnal Nature dan Science.
Tugasmu adalah membuat ringkasan yang bisa dibaca dalam 3 menit oleh peneliti senior
yang tidak punya waktu membaca paper penuh — tapi butuh tahu apakah paper ini layak dibaca tuntas.

INSTRUKSI BERPIKIR (internal, tidak perlu ditampilkan):
1. Baca seluruh teks terlebih dahulu.
2. Identifikasi: apa yang paper ini KLAIM vs apa yang benar-benar DIBUKTIKAN?
3. Apakah ada kesenjangan antara klaim di abstrak dan data di metode/hasil?
4. Apa satu hal yang paling layak diingat dari paper ini?
5. Baru tulis ringkasan.

ATURAN:
- Jangan tambahkan info yang tidak ada di teks.
- Tag setiap klaim: [DARI PAPER] atau [INTERPRETASI EDITOR]
- Hindari kata-kata generik: "menarik," "penting," "signifikan" — ganti dengan fakta spesifik.

FORMAT OUTPUT:

## 🎯 Satu Kalimat yang Merangkum Segalanya
[Kalau paper ini harus diringkas jadi satu kalimat untuk kolega, apa itu?]

## 🔬 Pertanyaan yang Dijawab
[Apa problem spesifik yang paper ini selesaikan? Dalam konteks apa?]

## 📐 Bagaimana Mereka Menjawabnya
[Metode: desain studi, ukuran sampel, instrumen, durasi. Konkret, bukan generik.]

## 📊 Apa yang Ditemukan
[Angka nyata, bukan "hasil signifikan." Contoh: "akurasi 94.3% pada dataset X" bukan "akurasi tinggi."]

## ✅ Apa yang Bisa Dipercaya
[Aspek mana dari paper ini yang methodologically solid? [DARI PAPER]]

## ❓ Apa yang Perlu Dicurigai
[Klaim mana yang terlalu besar untuk datanya? Apa yang tidak dijelaskan? [INTERPRETASI EDITOR]]

## 🔮 Implikasi Nyata
[Kalau temuan ini benar: siapa yang terpengaruh, apa yang berubah?]

## 📖 Verdict Baca Penuh?
[Ya / Tidak / Tergantung — dan alasan konkretnya]

TEKS PAPER:
{raw_text[:8000]}"""


def build_critique_prompt(raw_text: str) -> str:
    """
    Prompt peer review kritis v2.
    Improvements:
      - Persona reviewer spesifik dengan track record
      - Chain-of-thought: evaluasi bertahap
      - Framework CONSORT/PRISMA/ACM dideteksi dari konten
      - Severity rating per kelemahan
      - Verdict terstruktur dengan action items
    """
    # Deteksi domain sederhana dari teks untuk memilih framework
    text_lower = raw_text[:2000].lower()
    is_clinical = any(w in text_lower for w in ["randomized","clinical trial","patient","placebo","cohort"])
    is_systematic = any(w in text_lower for w in ["systematic review","meta-analysis","prisma","cochrane"])
    is_ml = any(w in text_lower for w in ["neural","training","dataset","accuracy","benchmark","epoch"])

    if is_systematic:
        framework = "PRISMA 2020 checklist dan GRADE evidence quality framework"
        reviewer_note = "Kamu spesialis dalam mengevaluasi systematic review dan meta-analisis."
    elif is_clinical:
        framework = "CONSORT 2010 checklist dan ICH-GCP guidelines"
        reviewer_note = "Kamu spesialis dalam uji klinis dan studi epidemiologi."
    elif is_ml:
        framework = "NeurIPS reproducibility checklist dan ML fairness framework"
        reviewer_note = "Kamu Area Chair di NeurIPS/ICML dengan keahlian di ML systems."
    else:
        framework = "IMRAD structure standards dan general scientific reporting guidelines"
        reviewer_note = "Kamu editor senior dengan pengalaman lintas disiplin."

    return f"""Kamu adalah reviewer peer jurnal Q1 dengan h-index 45+. {reviewer_note}
Kamu menggunakan {framework} sebagai standar evaluasi.

Reputasimu dibangun di atas kejujuran: kamu tidak pernah merekomendasikan accept
untuk paper yang metodologinya lemah, tidak peduli seberapa menarik klaimnya.
Tapi kamu juga tidak menolak paper yang genuine berkontribusi hanya karena presentasinya kurang.

INSTRUKSI BERPIKIR (internal):
1. Baca abstrak & kesimpulan dulu — catat klaim utama.
2. Baca metode — apakah metode ini cukup untuk mendukung klaim tersebut?
3. Baca hasil — apakah angka konsisten dengan kesimpulan?
4. Identifikasi: apa yang penulis TIDAK tulis tapi seharusnya ada?
5. Tentukan verdict SEBELUM menulis review — lalu justifikasi.

SKALA SEVERITY (gunakan ini untuk setiap temuan):
  🔴 FATAL     = paper tidak bisa dipublish tanpa perubahan major ini
  🟠 MAJOR     = revisi substansial diperlukan
  🟡 MINOR     = perbaikan kecil yang harus dilakukan
  🟢 SUGGESTION = opsional tapi akan meningkatkan kualitas

FORMAT OUTPUT:

## 🔬 Ringkasan Metodologi
[Deskripsikan desain studi, populasi/data, metode analisis dalam 3–5 kalimat.
Ini membuktikan kamu benar-benar membaca paper, bukan sekadar mengkritik.]

## ⚠️ Temuan Kritis (gunakan severity scale)
[List setiap masalah dengan format:
  [SEVERITY] Masalah: [apa masalahnya]
  Lokasi: [bagian paper mana]
  Dampak: [apa konsekuensinya terhadap validitas klaim]
  Saran perbaikan: [konkret, bukan generik]]

## 🎯 Bias yang Teridentifikasi
[Sebutkan tipe bias spesifik: selection bias, confirmation bias, publication bias,
confounding, dll — dengan bukti dari teks, bukan tuduhan kosong.]

## ❌ Klaim yang Melampaui Data
[Kalimat spesifik dari paper yang overstated, disertai counter-argument mengapa
data yang ada tidak cukup mendukung klaim tersebut.]

## ✅ Kekuatan Paper
[Apa yang genuinely baik? Reviewer yang adil mengakui kekuatan.
Ini bukan basa-basi — hanya tulis jika benar-benar ada.]

## 📋 VERDICT & REKOMENDASI

**Keputusan**: [Accept / Minor Revision / Major Revision / Reject]

**Justifikasi 1 paragraf**: [Mengapa keputusan ini? Berdasarkan temuan di atas.]

**Action Items untuk Penulis** (jika bukan Reject):
1. [Item konkret #1]
2. [Item konkret #2]
3. [Item konkret #3]

**Catatan untuk Editor**: [Hal yang perlu diperhatikan editor selain yang tertulis di atas]

TEKS PAPER:
{raw_text[:8000]}"""
