"""
app.py
======
Tanggung jawab:
  - Konfigurasi halaman & CSS styling
  - Semua komponen UI Streamlit
  - Visualisasi chart (Plotly)
  - Mengorkestrasi data_layer, ai_layer, dan graph_layer
  - Entry point aplikasi: jalankan dengan `streamlit run app.py`

Dependensi internal:
  - data_layer.py  → search_papers()
  - ai_layer.py    → model, build_*_prompt()
  - graph_layer.py → build_knowledge_graph(), render_graph(), graph_stats()
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import pdfplumber

from data_layer import search_papers
from ai_layer import (
    model,
    build_analysis_prompt,
    build_summary_prompt,
    build_critique_prompt,
)
from graph_layer import (
    build_knowledge_graph,
    render_graph,
    graph_stats,
)
from graph_roadmap import render_roadmap, roadmap_stats
from graph_influence import render_influence, influence_stats
from graph_gap import render_gap, gap_stats


# ─────────────────────────────────────────────────────
# 1. KONFIGURASI HALAMAN
# ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Research Assistant Pro",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

.main-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2.2rem; font-weight: 600;
    letter-spacing: -1px; color: #0f172a; margin-bottom: 0;
}
.sub-caption {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem; color: #64748b;
    letter-spacing: 0.5px; margin-top: 2px;
}
.badge-high   { background:#dcfce7; color:#166534; padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }
.badge-medium { background:#fef9c3; color:#854d0e; padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }
.badge-low    { background:#f1f5f9; color:#475569; padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }

.graph-legend-dot {
    display: inline-block;
    width: 12px; height: 12px;
    border-radius: 50%; margin-right: 6px;
    vertical-align: middle;
}
.stButton > button {
    width: 100%; border-radius: 8px; height: 3em;
    background: #0f172a; color: white; border: none;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600; letter-spacing: 0.5px;
}
.stButton > button:hover { background: #1e293b; color: white; }
.debug-box {
    background: #1e1e1e; color: #4ade80;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem; padding: 16px;
    border-radius: 8px; border: 1px solid #333;
    white-space: pre-wrap; overflow-x: auto;
}
.warning-box {
    background: #fffbeb; border: 1px solid #fcd34d;
    border-radius: 10px; padding: 16px 20px; font-size: 0.85rem;
}
hr { border: none; border-top: 1px solid #e2e8f0; margin: 24px 0; }
</style>
""", unsafe_allow_html=True)

if model is None:
    st.error("❌ Gagal terhubung ke Gemini AI. Periksa API Key di secrets.toml.")
    st.stop()


# ─────────────────────────────────────────────────────
# 2. CHARTS
# ─────────────────────────────────────────────────────

def create_citation_chart(papers: list[dict]):
    try:
        df = pd.DataFrame([{
            "title": (p["title"][:45] + "…") if len(p["title"]) > 45 else p["title"],
            "citations": p["citations"]
        } for p in papers])
        fig = px.bar(
            df.sort_values("citations"), x="citations", y="title",
            orientation="h", title="<b>Sitasi per Paper</b>",
            labels={"citations": "Sitasi", "title": ""},
            template="plotly_white", color="citations",
            color_continuous_scale=["#e2e8f0", "#0f172a"]
        )
        fig.update_layout(height=350, margin=dict(l=0, r=20, t=45, b=0),
                          coloraxis_showscale=False)
        return fig
    except Exception:
        return None


def create_timeline_chart(papers: list[dict]):
    try:
        df = pd.DataFrame([{
            "year": int(p["year"]) if p["year"].isdigit() else None,
            "citations": p["citations"],
            "title": p["title"][:35]
        } for p in papers]).dropna()
        if df.empty:
            return None
        fig = px.scatter(
            df, x="year", y="citations", size="citations",
            hover_name="title", title="<b>Peta Temporal</b>",
            labels={"year": "Tahun", "citations": "Sitasi"},
            template="plotly_white", color="citations",
            color_continuous_scale=["#e2e8f0", "#0f172a"]
        )
        fig.update_layout(height=280, margin=dict(l=0, r=20, t=45, b=0),
                          coloraxis_showscale=False)
        return fig
    except Exception:
        return None


# ─────────────────────────────────────────────────────
# 3. SESSION STATE
# ─────────────────────────────────────────────────────

for key, default in {
    "papers": None,
    "active_topic": "",
    "analysis_text": "",
    "debug_log": "",
    "last_api_status": None,
    # Tab 3 legacy (Knowledge Graph lama — dipertahankan agar tidak break)
    "graph_html": None,
    "graph_stats_data": None,
    "graph_analysis_text": "",
    # Tab 3 baru — Research Intelligence Center
    "roadmap_html":         None,
    "roadmap_stats_data":   None,
    "influence_html":       None,
    "influence_stats_data": None,
    "gap_html":             None,
    "gap_stats_data":       None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ─────────────────────────────────────────────────────
# 4. HEADER
# ─────────────────────────────────────────────────────

st.markdown('<p class="main-title">🧬 AI Research Assistant Pro</p>', unsafe_allow_html=True)
st.markdown(
    f'<p class="sub-caption">MODEL: {model.model_name.upper()} &nbsp;·&nbsp; '
    f'DATA: SEMANTIC SCHOLAR + CROSSREF FALLBACK</p>',
    unsafe_allow_html=True
)
st.markdown("---")


# ─────────────────────────────────────────────────────
# 5. TABS
# ─────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "🔎 Cari & Analisis Riset",
    "📄 Bedah Dokumen PDF",
    "🕸️ Knowledge Graph",
])


# ══════════════════════════════════════════════════════
# TAB 1 — PENCARIAN & ANALISIS
# ══════════════════════════════════════════════════════
with tab1:

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        topic = st.text_input(
            "Topik",
            placeholder="Contoh: leukemia treatment immunotherapy",
            label_visibility="collapsed"
        )
    with c2:
        btn_search = st.button("🔍 Cari Paper", use_container_width=True)
    with c3:
        debug_mode = st.toggle("🐛 Debug", value=False)

    st.caption("💡 Tip: Gunakan bahasa Inggris. Contoh: *leukemia* bukan *leukimia*")

    if btn_search and topic:
        with st.spinner("Menghubungi API..."):
            papers, log = search_papers(topic, limit=8, debug=debug_mode)
            st.session_state.papers       = papers
            st.session_state.active_topic = topic
            st.session_state.analysis_text = ""
            st.session_state.debug_log    = log
            # Reset SEMUA graph/visualisasi ketika topik baru dicari
            st.session_state.graph_html             = None
            st.session_state.graph_stats_data       = None
            st.session_state.graph_analysis_text    = ""
            st.session_state.roadmap_html           = None
            st.session_state.roadmap_stats_data     = None
            st.session_state.influence_html         = None
            st.session_state.influence_stats_data   = None
            st.session_state.gap_html               = None
            st.session_state.gap_stats_data         = None

    if debug_mode and st.session_state.debug_log:
        st.markdown("**🐛 Debug Log:**")
        st.markdown(
            f'<div class="debug-box">{st.session_state.debug_log}</div>',
            unsafe_allow_html=True
        )

    if st.session_state.papers:
        papers = st.session_state.papers

        source = papers[0].get("source", "Unknown")
        if source == "CrossRef":
            st.info("ℹ️ Hasil dari **CrossRef** (fallback) — Semantic Scholar tidak merespons atau kosong")

        total_cits = sum(p["citations"] for p in papers)
        avg_cits   = total_cits / len(papers)
        years      = [int(p["year"]) for p in papers if p["year"].isdigit()]
        year_range = f"{min(years)}–{max(years)}" if years else "?"

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Paper", len(papers))
        col_b.metric("Total Sitasi", f"{total_cits:,}")
        col_c.metric("Rata-rata Sitasi", f"{avg_cits:.0f}")
        col_d.metric("Rentang Tahun", year_range)
        st.markdown("---")

        col_papers, col_vis = st.columns([3, 2])

        with col_papers:
            st.markdown("#### 📚 Daftar Paper")
            for i, p in enumerate(papers, 1):
                badge_class = {
                    "high": "badge-high",
                    "medium": "badge-medium",
                    "low": "badge-low"
                }.get(p["impact_level"], "badge-low")
                with st.expander(f"[{i}] {p['title']} ({p['year']})"):
                    ci, cii = st.columns([2, 1])
                    with ci:
                        st.markdown(f"**👤** {p['authors']}")
                        st.markdown(f"**📰** {p['venue']}")
                    with cii:
                        st.markdown(
                            f'<span class="{badge_class}">{p["impact_label"]}</span>',
                            unsafe_allow_html=True
                        )
                        st.markdown(f"**🔥 {p['citations']:,}** sitasi")
                    st.info(p["abstract"])
                    st.link_button("🌐 Buka Paper", p["link"], use_container_width=True)

            df_export = pd.DataFrame([{
                "No": i, "Judul": p["title"], "Penulis": p["authors"],
                "Tahun": p["year"], "Sitasi": p["citations"],
                "Venue": p["venue"], "Sumber": p["source"], "Link": p["link"]
            } for i, p in enumerate(papers, 1)])
            st.download_button(
                "⬇️ Export CSV",
                data=df_export.to_csv(index=False).encode("utf-8"),
                file_name=f"riset_{st.session_state.active_topic[:25].replace(' ','_')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col_vis:
            st.markdown("#### 📊 Visualisasi")
            fig1 = create_citation_chart(papers)
            if fig1:
                st.plotly_chart(fig1, use_container_width=True)
            fig2 = create_timeline_chart(papers)
            if fig2:
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🧠 Analisis Strategis AI")

        if st.session_state.analysis_text:
            st.markdown(st.session_state.analysis_text)
            if st.button("🔄 Regenerasi Analisis"):
                st.session_state.analysis_text = ""
                st.rerun()
        else:
            if st.button("▶️ Jalankan Analisis AI", use_container_width=True):
                with st.spinner("Gemini menganalisis..."):
                    try:
                        resp = model.generate_content(
                            build_analysis_prompt(st.session_state.active_topic, papers)
                        )
                        st.session_state.analysis_text = resp.text
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal: {e}")

        st.markdown(
            '<div class="warning-box">⚠️ <b>Transparansi:</b> Analisis berdasarkan paper '
            'nyata dari database ilmiah. AI tidak menginvent data.</div>',
            unsafe_allow_html=True
        )

    elif btn_search and not st.session_state.papers:
        st.error("❌ Tidak ada paper ditemukan dari kedua sumber.")
        if st.session_state.debug_log:
            st.markdown("**Detail kegagalan:**")
            st.markdown(
                f'<div class="debug-box">{st.session_state.debug_log}</div>',
                unsafe_allow_html=True
            )


# ══════════════════════════════════════════════════════
# TAB 2 — BEDAH PDF
# ══════════════════════════════════════════════════════
with tab2:
    st.markdown("#### 📄 Upload Paper untuk Dibedah")
    file = st.file_uploader("PDF", type=["pdf"], label_visibility="collapsed")

    if file:
        with st.spinner("Membaca PDF..."):
            try:
                with pdfplumber.open(file) as pdf:
                    total_pages = len(pdf.pages)
                    raw_text = "".join([p.extract_text() or "" for p in pdf.pages[:5]])
            except Exception as e:
                st.error(f"Gagal membaca PDF: {e}")
                st.stop()

        if not raw_text.strip():
            st.error("PDF tidak mengandung teks. Mungkin file scan/gambar.")
        else:
            st.success(f"✅ {total_pages} halaman · {len(raw_text):,} karakter")
            cb1, cb2 = st.columns(2)
            with cb1:
                btn_sum = st.button("📝 Ringkasan Eksekutif", use_container_width=True)
            with cb2:
                btn_crit = st.button("⚖️ Analisis Kritis", use_container_width=True)

            if btn_sum:
                with st.spinner("Meringkas..."):
                    try:
                        st.markdown(model.generate_content(build_summary_prompt(raw_text)).text)
                    except Exception as e:
                        st.error(f"Error: {e}")

            if btn_crit:
                with st.spinner("Peer reviewing..."):
                    try:
                        st.markdown(model.generate_content(build_critique_prompt(raw_text)).text)
                    except Exception as e:
                        st.error(f"Error: {e}")


# ══════════════════════════════════════════════════════
# TAB 3 — RESEARCH INTELLIGENCE CENTER
# ══════════════════════════════════════════════════════
with tab3:

    if not st.session_state.papers:
        st.info("🔎 Cari paper dulu di tab **Cari & Analisis Riset**, lalu kembali ke sini.")

    else:
        papers = st.session_state.papers
        topic  = st.session_state.active_topic

        st.markdown(f"#### 🧠 Research Intelligence Center — *{topic}*")
        st.caption(
            f"**{len(papers)} paper** siap dianalisis dari 3 dimensi berbeda. "
            "Setiap fitur di-build secara independen — hasilnya tersimpan otomatis."
        )

        sub1, sub2, sub3 = st.tabs([
            "🗺️ Research Roadmap",
            "🎯 Influence Map",
            "🕳️ Gap Detector",
        ])

        # ──────────────────────────────────────────────
        # SUB-TAB 1 — RESEARCH ROADMAP
        # ──────────────────────────────────────────────
        with sub1:
            st.markdown("##### 🗺️ Research Roadmap")
            st.caption(
                "Peta perjalanan intelektual berbentuk timeline horizontal. "
                "Sumbu X = tahun terbit · Tier = jumlah sitasi · "
                "Garis oranye = jalur baca yang direkomendasikan."
            )

            if st.button("🔨 Bangun Research Roadmap",
                         key="btn_roadmap", use_container_width=True):
                with st.spinner("Membangun roadmap… (~2 detik)"):
                    try:
                        st.session_state.roadmap_html       = render_roadmap(papers, height=680)
                        st.session_state.roadmap_stats_data = roadmap_stats(papers)
                    except Exception as exc:
                        st.error(f"Gagal membangun Roadmap: {exc}")

            if st.session_state.roadmap_html:
                rs = st.session_state.roadmap_stats_data or {}
                st.markdown("---")

                # ── Metric cards
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Total Paper",          rs.get("total_papers",      "—"))
                r2.metric("Rentang Tahun",         rs.get("year_span",         "—"))
                r3.metric("Pioneer (>100 sit)",    rs.get("pioneer_count",     "—"))
                r4.metric("Emerging (<20 sit)",    rs.get("emerging_count",    "—"))

                st.markdown("---")
                rc1, rc2 = st.columns(2)
                rc1.markdown(
                    f"**📚 Paper paling berpengaruh**  \n"
                    f"_{rs.get('most_foundational', '—')}_"
                )
                rc2.markdown(
                    f"**🚀 Mulai membaca dari**  \n"
                    f"_{rs.get('recommended_first', '—')}_"
                )
                st.markdown("---")

                st.caption(
                    "💡 Hover kartu → detail · "
                    "Klik kartu → focus mode · "
                    "Toggle **PATH / VENUE / CONNECTIONS** di toolbar · "
                    "Slider = filter rentang tahun secara real-time"
                )
                components.html(
                    st.session_state.roadmap_html, height=700, scrolling=False
                )

                if st.button("🔄 Rebuild Roadmap", key="btn_roadmap_reset"):
                    st.session_state.roadmap_html       = None
                    st.session_state.roadmap_stats_data = None
                    st.rerun()

        # ──────────────────────────────────────────────
        # SUB-TAB 2 — INFLUENCE MAP
        # ──────────────────────────────────────────────
        with sub2:
            st.markdown("##### 🎯 Influence Map")
            st.caption(
                "Peta tata surya pengaruh ilmiah. "
                "Paper pilihan = matahari emas di tengah · "
                "Ring 🔵 = leluhur intelektual · "
                "Ring 🟢 = penerus/keturunan · "
                "Ring ⚪ = tetangga tidak langsung."
            )
            st.markdown(
                '<div class="warning-box">⏱️ <b>Perhatian:</b> '
                'Fitur ini mengambil data jaringan sitasi dari Semantic Scholar '
                'untuk setiap paper — proses pertama membutuhkan ~15–30 detik. '
                'Hasil akan ter-cache 1 jam sehingga build berikutnya instan.</div>',
                unsafe_allow_html=True
            )
            st.markdown("")

            if st.button("🔨 Bangun Influence Map",
                         key="btn_influence", use_container_width=True):
                with st.spinner(
                    "Mengambil jaringan sitasi dari Semantic Scholar… "
                    "(~15–30 detik untuk build pertama)"
                ):
                    try:
                        st.session_state.influence_html       = render_influence(papers, height=700)
                        st.session_state.influence_stats_data = influence_stats(papers)
                    except Exception as exc:
                        st.error(f"Gagal membangun Influence Map: {exc}")

            if st.session_state.influence_html:
                ins = st.session_state.influence_stats_data or {}
                st.markdown("---")

                # ── Metric cards
                i1, i2, i3, i4 = st.columns(4)
                i1.metric("Total Paper",       ins.get("total_papers",     "—"))
                i2.metric("Total Node",         ins.get("total_nodes",      "—"))
                i3.metric("Leluhur (Ring 1)",   ins.get("ancestor_count",   "—"))
                i4.metric("Penerus (Ring 2)",   ins.get("descendant_count", "—"))

                st.markdown("---")
                ic1, ic2 = st.columns(2)
                ic1.markdown(
                    f"**⭐ Pusat default**  \n"
                    f"_{ins.get('center_title', '—')}_"
                )
                ic2.markdown(
                    f"**🌐 Jangkauan pengaruh**  \n"
                    f"_{ins.get('influence_reach', '—')} node terhubung_"
                )
                st.markdown("---")

                st.caption(
                    "💡 Klik node → panel detail · "
                    "Tombol **⊙ JADIKAN PUSAT** → re-center instan · "
                    "Toggle **PARTICLES / ORBITS / HEATMAP** · "
                    "**COMPARE** → split-view 2 paper side-by-side"
                )
                components.html(
                    st.session_state.influence_html, height=720, scrolling=False
                )

                if st.button("🔄 Rebuild Influence Map", key="btn_influence_reset"):
                    st.session_state.influence_html       = None
                    st.session_state.influence_stats_data = None
                    st.rerun()

        # ──────────────────────────────────────────────
        # SUB-TAB 3 — GAP DETECTOR
        # ──────────────────────────────────────────────
        with sub3:
            st.markdown("##### 🕳️ Research Gap Detector")
            st.caption(
                "Analisis multidimensional celah riset. "
                "4 sub-view terintegrasi: "
                "**Venn Diagram** · **Heatmap** topik × paper · "
                "**Gap Score** radar chart · "
                "**Hidden Findings** + Gap Statement siap-pakai."
            )

            if st.button("🔨 Deteksi Research Gap",
                         key="btn_gap", use_container_width=True):
                with st.spinner("Menganalisis celah riset… (~3 detik)"):
                    try:
                        st.session_state.gap_html       = render_gap(papers, height=720)
                        st.session_state.gap_stats_data = gap_stats(papers)
                    except Exception as exc:
                        st.error(f"Gagal mendeteksi Gap: {exc}")

            if st.session_state.gap_html:
                gs = st.session_state.gap_stats_data or {}
                st.markdown("---")

                # ── Metric cards
                g1, g2, g3, g4 = st.columns(4)
                g1.metric("Total Keyword",    gs.get("total_keywords",     "—"))
                g2.metric("Gap Kritis 🔴",    gs.get("critical_gaps",      "—"))
                g3.metric("Coverage Score",   f"{gs.get('coverage_score_pct', 0)}%")
                g4.metric("Topik Aman ✅",    f"{gs.get('covered_pct',     0)}%")

                st.markdown("---")
                gc1, gc2 = st.columns(2)
                gc1.markdown(
                    f"**🔴 Gap paling kritis**  \n"
                    f"_{gs.get('top_gap_keyword', '—')}_"
                )
                gc2.markdown(
                    f"**✅ Topik terlindungi**  \n"
                    f"_{gs.get('top_covered_keyword', '—')}_"
                )
                st.markdown("---")

                st.caption(
                    "💡 Tab **VENN · HEATMAP · GAP SCORE · HIDDEN FINDINGS** "
                    "ada di dalam komponen di bawah ini · "
                    "Tombol **⎘ SALIN** = copy Gap Statement ke clipboard"
                )
                components.html(
                    st.session_state.gap_html, height=740, scrolling=False
                )

                if st.button("🔄 Rebuild Gap Detector", key="btn_gap_reset"):
                    st.session_state.gap_html       = None
                    st.session_state.gap_stats_data = None
                    st.rerun()

        st.markdown("---")
        st.markdown(
            '<div class="warning-box">⚠️ <b>Transparansi:</b> Semua analisis '
            'berbasis data nyata dari hasil pencarian. '
            'Tidak ada data yang diinvent oleh AI.</div>',
            unsafe_allow_html=True
        )
