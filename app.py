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
from graph_influence import render_influence, influence_stats
from graph_gap import render_gap, gap_stats
from topic_river import render_topic_river, river_stats
from contradiction_detector import render_contradiction

import re
import math
import collections


# ─────────────────────────────────────────────────────
# HELPER FUNCTIONS — NEW VISUALIZATIONS
# ─────────────────────────────────────────────────────

# Shared dark Plotly theme
_PLOTLY_DARK = dict(
    paper_bgcolor="#05111e",
    plot_bgcolor="#05111e",
    font=dict(family="JetBrains Mono, monospace", color="#7aa8cc", size=11),
    margin=dict(l=10, r=10, t=40, b=10),
)
# Applied per-chart (not in _PLOTLY_DARK to avoid key conflicts)
_AXIS_STYLE = dict(gridcolor="rgba(80,140,220,.08)", zerolinecolor="rgba(80,140,220,.12)")

_STOPWORDS = frozenset({
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","as","is","was","are","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","not",
    "this","that","these","those","it","its","we","our","their","they",
    "paper","study","research","propose","present","show","result","results",
    "approach","method","methods","using","used","use","based","novel","new",
    "existing","previous","however","also","which","such","than","more","most",
    "work","model","system","data","performance","two","three","one","large",
    "high","low","can","well","often","number","type","different","various",
})


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _top_keywords(papers: list[dict], n: int = 12) -> list[str]:
    """Get top n keywords across all paper titles+abstracts."""
    freq: dict[str, int] = collections.Counter()
    for p in papers:
        text = (p.get("title", "") or "") + " " + (p.get("abstract", "") or "")
        for t in _tokenize(text):
            freq[t] += 1
    return [kw for kw, _ in freq.most_common(n)]

def build_research_dna(papers: list[dict]):
    """
    Research DNA heatmap.
    FIX: bigger cells, bigger fonts, full paper titles on hover,
    color scale with more contrast, proper sizing.
    """
    import plotly.graph_objects as go
    import numpy as np

    keywords = _top_keywords(papers, n=12)   # fewer = bigger cells
    if not keywords:
        return None

    # Score matrix: paper × keyword
    matrix = []
    x_labels = []
    for p in papers:
        text = (p.get("title", "") or "") + " " + (p.get("abstract", "") or "")
        tokens = _tokenize(text)
        total = len(tokens) or 1
        freq  = collections.Counter(tokens)
        row   = [round(freq.get(kw, 0) / total * 100, 3) for kw in keywords]
        matrix.append(row)
        # Short label for x-axis: "YYYY · Title..."
        short = p["title"][:32] + "…" if len(p["title"]) > 32 else p["title"]
        x_labels.append(f"{p.get('year','?')} · {short}")

    # Transpose → keywords on Y, papers on X
    mat = np.array(matrix).T.tolist()

    # High-contrast colorscale: near-black → bright cyan → purple peak
    colorscale = [
        [0.00, "#04111e"],
        [0.10, "#062840"],
        [0.30, "#0a4d72"],
        [0.55, "#0097b2"],
        [0.78, "#00d4d4"],
        [1.00, "#c084fc"],
    ]

    # Hover text with full info
    hover_text = []
    for ki, kw in enumerate(keywords):
        row_hover = []
        for pi, p in enumerate(papers):
            score = mat[ki][pi]
            intensity = (
                "🔴 Sangat Dominan" if score > 2
                else "🟡 Cukup Relevan" if score > 0.5
                else "⚪ Jarang Muncul"
            )
            row_hover.append(
                f"<b>Keyword: {kw.upper()}</b><br>"
                f"Paper: {p['title'][:55]}…<br>"
                f"Tahun: {p.get('year','?')} · Sitasi: {p.get('citations',0):,}<br>"
                f"Bobot TF: {score:.3f}%<br>"
                f"{intensity}"
            )
        hover_text.append(row_hover)

    # Dynamic height: enough for keywords + label margin
    cell_h   = 38
    fig_h    = max(420, len(keywords) * cell_h + 160)

    fig = go.Figure(data=go.Heatmap(
        z=mat,
        x=x_labels,
        y=[kw.upper() for kw in keywords],
        colorscale=colorscale,
        showscale=True,
        colorbar=dict(
            title=dict(text="Bobot TF", font=dict(color="#7aa8cc", size=12)),
            tickfont=dict(color="#7aa8cc", size=11),
            bgcolor="rgba(5,17,30,.85)",
            bordercolor="rgba(80,140,220,.2)",
            len=0.9,
            thickness=16,
        ),
        hoverinfo="text",
        text=hover_text,
        xgap=3,
        ygap=3,
    ))

    fig.update_layout(
        title=dict(
            text="🧬 Research DNA — Sidik Jari Topik per Paper",
            font=dict(size=15, color="#e8f4ff", family="Inter, sans-serif"),
            x=0.02,
        ),
        xaxis=dict(
            title=dict(text="Paper", font=dict(size=13, color="#7aa8cc")),
            color="#9ac0e0",
            tickangle=-40,
            tickfont=dict(size=10, family="JetBrains Mono, monospace"),
            tickmode="array",
            tickvals=list(range(len(papers))),
            ticktext=x_labels,
        ),
        yaxis=dict(
            title=dict(text="Keyword", font=dict(size=13, color="#7aa8cc")),
            color="#9ac0e0",
            tickfont=dict(size=13, family="JetBrains Mono, monospace"),
            automargin=True,
        ),
        height=fig_h,
        margin=dict(l=130, r=20, t=60, b=140),
        **_PLOTLY_DARK,
    )
    return fig


def build_contradiction_data(papers: list[dict]) -> list[dict]:
    """
    Find paper pairs with potential contradictions.
    Method: papers that share topic keywords but have opposing signal words.
    Returns list of dicts sorted by conflict_score desc.
    """
    POSITIVE_SIGNALS = {
        "improve","improves","improved","improvement","outperform","outperforms",
        "superior","better","effective","efficient","accurate","robust","strong",
        "significant","high","increase","enhance","advantage","novel","promising",
    }
    NEGATIVE_SIGNALS = {
        "fail","fails","failed","failure","poor","worse","inferior","ineffective",
        "inaccurate","weak","insignificant","low","decrease","limitation","drawback",
        "challenge","problem","issue","concern","limitation","limited","lacks",
    }
    CONTRADICTION_PAIRS = {
        ("improve", "fail"), ("effective", "ineffective"), ("accurate", "inaccurate"),
        ("robust", "weak"), ("superior", "inferior"), ("increase", "decrease"),
        ("high", "low"), ("strong", "weak"), ("better", "worse"),
    }

    def signals(text: str):
        tokens = set(re.findall(r"[a-z]+", text.lower()))
        return tokens & POSITIVE_SIGNALS, tokens & NEGATIVE_SIGNALS

    def shared_keywords(p1, p2):
        t1 = set(_tokenize((p1.get("title","") or "") + " " + (p1.get("abstract","") or "")))
        t2 = set(_tokenize((p2.get("title","") or "") + " " + (p2.get("abstract","") or "")))
        return (t1 & t2) - _STOPWORDS

    results = []
    for i, p1 in enumerate(papers):
        for p2 in papers[i+1:]:
            shared = shared_keywords(p1, p2)
            if len(shared) < 3:
                continue

            text1 = (p1.get("title","") or "") + " " + (p1.get("abstract","") or "")
            text2 = (p2.get("title","") or "") + " " + (p2.get("abstract","") or "")
            pos1, neg1 = signals(text1)
            pos2, neg2 = signals(text2)

            conflict_count = 0
            conflict_terms = []
            for a_pos, b_neg in [(pos1, neg2), (pos2, neg1)]:
                for a in a_pos:
                    for b in b_neg:
                        if (a, b) in CONTRADICTION_PAIRS or (b, a) in CONTRADICTION_PAIRS:
                            conflict_count += 1
                            conflict_terms.append(f"{a} ↔ {b}")

            base         = min(len(shared) * 4, 40)
            signal_score = min(conflict_count * 15, 45)
            try:
                yr_gap = abs(int(p1.get("year", 0)) - int(p2.get("year", 0)))
            except Exception:
                yr_gap = 0
            time_score   = min(yr_gap * 2, 15)
            conflict_score = min(100, base + signal_score + time_score)
            if conflict_score < 20:
                continue

            results.append({
                "paper1_title":   p1["title"],
                "paper2_title":   p2["title"],
                "paper1_year":    p1.get("year", "?"),
                "paper2_year":    p2.get("year", "?"),
                "paper1_cite":    p1.get("citations", 0),
                "paper2_cite":    p2.get("citations", 0),
                "shared_kws":     sorted(list(shared))[:6],
                "conflict_terms": list(set(conflict_terms))[:4],
                "conflict_score": conflict_score,
                "label": (
                    "⚡ KONFLIK TINGGI"      if conflict_score >= 65
                    else "⚠️ BERPOTENSI BERBEDA" if conflict_score >= 40
                    else "🔍 PERLU DICERMATI"
                ),
                "label_color": (
                    "#f87171" if conflict_score >= 65
                    else "#fb923c" if conflict_score >= 40
                    else "#facc15"
                ),
            })

    return sorted(results, key=lambda x: -x["conflict_score"])


def build_contradiction_chart(pairs: list[dict]):
    """
    Contradiction bar chart.
    FIX: color gradient per score level, bigger fonts,
    score badge annotations, clear visual hierarchy.
    """
    import plotly.graph_objects as go

    if not pairs:
        return None

    top = pairs[:8]

    # Better labels: "A (YYYY) vs B (YYYY)"
    labels = []
    for p in top:
        a = p["paper1_title"][:30] + "…" if len(p["paper1_title"]) > 30 else p["paper1_title"]
        b = p["paper2_title"][:30] + "…" if len(p["paper2_title"]) > 30 else p["paper2_title"]
        labels.append(f"{a}  ↔  {b}")

    scores = [p["conflict_score"] for p in top]
    colors = [p["label_color"] for p in top]

    # Custom hover text
    hover = [
        f"<b>{p['label']}</b><br>"
        f"Score: <b>{p['conflict_score']}</b>/100<br>"
        f"Paper A: {p['paper1_title'][:60]}<br>"
        f"Paper B: {p['paper2_title'][:60]}<br>"
        f"Keyword bersama: {', '.join(p['shared_kws'][:4])}<br>"
        + (f"Sinyal berlawanan: {', '.join(p['conflict_terms'][:3])}" if p['conflict_terms'] else "")
        for p in top
    ]

    fig = go.Figure()

    # Colored bars with gradient opacity
    fig.add_trace(go.Bar(
        x=scores,
        y=labels,
        orientation="h",
        marker=dict(
            color=colors,
            opacity=[0.65 + 0.35 * (s / 100) for s in scores],
            line=dict(color="rgba(255,255,255,.15)", width=1),
        ),
        text=[f"  {s}" for s in scores],
        textposition="inside",
        textfont=dict(size=13, color="white", family="JetBrains Mono, monospace"),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover,
    ))

    # Add score reference lines
    for threshold, label, clr in [(65, "⚡ Konflik Tinggi", "#f87171"), (40, "⚠️ Berpotensi Beda", "#fb923c")]:
        fig.add_vline(
            x=threshold, line_dash="dash",
            line_color=clr, line_width=1.2, opacity=0.5,
            annotation=dict(
                text=label, font=dict(size=10, color=clr),
                yanchor="bottom", y=1.02,
            ),
        )

    row_h  = 52
    fig_h  = max(320, len(top) * row_h + 100)

    fig.update_layout(
        title=dict(
            text="⚡ Contradiction Radar — Pasangan Paper Berpotensi Kontradiktif",
            font=dict(size=15, color="#e8f4ff", family="Inter, sans-serif"),
            x=0.02,
        ),
        xaxis=dict(
            title=dict(text="Conflict Score  (0 = sejalan · 100 = bertentangan penuh)", font=dict(size=12, color="#7aa8cc")),
            range=[0, 108],
            color="#9ac0e0",
            tickfont=dict(size=12),
            gridcolor="rgba(80,140,220,.1)",
        ),
        yaxis=dict(
            color="#9ac0e0",
            tickfont=dict(size=11, family="JetBrains Mono, monospace"),
            automargin=True,
        ),
        height=fig_h,
        margin=dict(l=20, r=20, t=60, b=20),
        **_PLOTLY_DARK,
    )
    return fig


# ─────────────────────────────────────────────────────
# HELPER — FULLSCREEN TOGGLE
# ─────────────────────────────────────────────────────

def _with_fullscreen(html: str, label: str = "") -> str:
    """
    Inject tombol Fullscreen / Exit ke dalam HTML komponen.
    Tombol muncul di pojok kanan atas — klik masuk fullscreen,
    klik lagi keluar. Persis seperti YouTube.
    Tidak memodifikasi file graph_*.py sama sekali.
    """
    _label = label or "Fullscreen"
    _inject = f"""
<style>
#_fsbtn {{
  position: fixed;
  bottom: 16px; right: 16px;
  z-index: 99999;
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px;
  background: rgba(10, 20, 40, 0.75);
  border: 1px solid rgba(99, 162, 255, 0.35);
  border-radius: 7px;
  color: #a8c8ff;
  font-family: 'Share Tech Mono', 'Fira Code', monospace;
  font-size: 11px; letter-spacing: 1px;
  cursor: pointer;
  backdrop-filter: blur(10px);
  transition: all 0.18s ease;
  user-select: none;
}}
#_fsbtn:hover {{
  background: rgba(99, 162, 255, 0.18);
  border-color: rgba(99, 162, 255, 0.65);
  color: #e0f0ff;
  box-shadow: 0 0 12px rgba(99, 162, 255, 0.2);
}}
#_fsbtn.active {{
  border-color: rgba(249, 115, 22, 0.6);
  color: #fdba74;
  background: rgba(249, 115, 22, 0.1);
}}
/* Saat fullscreen: sembunyikan scrollbar, beri latar hitam */
:fullscreen, :-webkit-full-screen {{
  background: #050b1a !important;
  overflow: hidden;
}}
</style>

<button id="_fsbtn" onclick="_toggleFS()" title="Fullscreen / Exit">
  <svg id="_fs_icon" width="13" height="13" viewBox="0 0 24 24"
       fill="none" stroke="currentColor" stroke-width="2.2"
       stroke-linecap="round" stroke-linejoin="round">
    <polyline points="15 3 21 3 21 9"></polyline>
    <polyline points="9 21 3 21 3 15"></polyline>
    <line x1="21" y1="3" x2="14" y2="10"></line>
    <line x1="3" y1="21" x2="10" y2="14"></line>
  </svg>
  <span id="_fs_lbl">FULLSCREEN</span>
</button>

<script>
(function() {{
  var _inFS = false;
  var _ICON_ENTER = '<polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line>';
  var _ICON_EXIT  = '<polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="10" y1="14" x2="3" y2="21"></line><line x1="21" y1="3" x2="14" y2="10"></line>';

  window._toggleFS = function() {{
    var el  = document.documentElement;
    var btn = document.getElementById('_fsbtn');
    var lbl = document.getElementById('_fs_lbl');
    var ico = document.getElementById('_fs_icon');
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {{
      var req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen;
      if (req) req.call(el).catch(function(){{}});
    }} else {{
      var ex = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen;
      if (ex) ex.call(document).catch(function(){{}});
    }}
  }};

  function _onFSChange() {{
    var btn = document.getElementById('_fsbtn');
    var lbl = document.getElementById('_fs_lbl');
    var ico = document.getElementById('_fs_icon');
    if (!btn) return;
    _inFS = !!(document.fullscreenElement || document.webkitFullscreenElement);
    if (_inFS) {{
      lbl.textContent = 'EXIT';
      ico.innerHTML   = _ICON_EXIT;
      btn.classList.add('active');
    }} else {{
      lbl.textContent = 'FULLSCREEN';
      ico.innerHTML   = _ICON_ENTER;
      btn.classList.remove('active');
    }}
  }}

  document.addEventListener('fullscreenchange',       _onFSChange);
  document.addEventListener('webkitfullscreenchange', _onFSChange);
  document.addEventListener('mozfullscreenchange',    _onFSChange);
  document.addEventListener('MSFullscreenChange',     _onFSChange);

  // ESC key juga keluar fullscreen (native browser — sudah otomatis, ini untuk update UI)
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') setTimeout(_onFSChange, 80);
  }});
}})();
</script>
"""
    # Inject sebelum </body> agar tidak konflik dengan script lain
    if "</body>" in html:
        return html.replace("</body>", _inject + "</body>", 1)
    # Fallback: append di akhir
    return html + _inject


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
    # Tab 3 — 3 fitur baru
    "river_fig":            None,
    "river_analysis":       "",
    "dna_fig":              None,
    "dna_analysis":         "",
    "contra_pairs":         None,
    "contra_fig":           None,
    "contra_analysis":      "",
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
            papers, log = search_papers(topic, limit=50, debug=debug_mode)
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
            st.session_state.river_fig              = None
            st.session_state.river_analysis         = ""
            st.session_state.dna_fig                = None
            st.session_state.dna_analysis           = ""
            st.session_state.contra_pairs           = None
            st.session_state.contra_fig             = None
            st.session_state.contra_analysis        = ""

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
                            build_analysis_prompt(st.session_state.active_topic, papers[:20])
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
            f"**{len(papers)} paper** siap dianalisis. "
            "Klik tombol di setiap sub-tab untuk memulai analisis."
        )

        sub1, sub2, sub3, sub4, sub5 = st.tabs([
            "🌊 Topic River",
            "🧬 Research DNA",
            "⚡ Contradiction",
            "🎯 Influence Map",
            "🕳️ Gap Detector",
        ])

        # ──────────────────────────────────────────────
        # SUB-TAB 1 — TOPIC RIVER
        # ──────────────────────────────────────────────
        with sub1:
            st.markdown("##### 🌊 Topic River — Research Momentum Dashboard")
            st.caption(
                "3 panel terintegrasi: **Velocity Ranking** (keyword mana yang sedang meledak) · "
                "**Streamgraph** (sejarah volume) · **2-Year Forecast** (proyeksi tren). "
                "Klik keyword di panel kiri untuk focus semua panel serentak."
            )

            if st.button("▶️ Generate Topic River", key="btn_river", use_container_width=True):
                with st.spinner("Membangun dashboard…"):
                    try:
                        html = render_topic_river(papers, height=600)
                        rs   = river_stats(papers)
                        st.session_state.river_fig          = html
                        st.session_state.river_stats_data   = rs
                        st.session_state.river_analysis     = ""
                    except Exception as exc:
                        st.error(f"Gagal: {exc}")

            if st.session_state.river_fig:
                rs = st.session_state.get("river_stats_data") or {}

                # Metric cards
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Keyword",  rs.get("total_keywords", "—"))
                m2.metric("Rentang Tahun",  rs.get("year_span",       "—"))
                m3.metric("🔴 Topik Naik",  rs.get("top_rising",      "—"))
                m4.metric("🔵 Topik Turun", rs.get("top_declining",   "—"))
                st.markdown("---")

                components.html(
                    _with_fullscreen(st.session_state.river_fig),
                    height=622, scrolling=False
                )

                st.markdown("---")

                # Lazy AI analysis
                if st.session_state.river_analysis:
                    st.markdown(st.session_state.river_analysis)
                    if st.button("🔄 Regenerasi Analisis", key="btn_river_regen"):
                        st.session_state.river_analysis = ""
                        st.rerun()
                else:
                    if st.button("🔬 Analisis Mendalam — Apa yang terjadi di bidang ini?",
                                 key="btn_river_ai", use_container_width=True):
                        kws = rs.get("top_rising","") and [rs["top_rising"]] or []
                        years_list = sorted(set(
                            int(p["year"]) for p in papers
                            if str(p.get("year","")).isdigit()
                        ))
                        kw_list = ", ".join(
                            p["title"].split()[0] for p in papers[:5]
                        )
                        prompt = f"""Kamu adalah analis riset ilmiah senior.

Topik: "{topic}"
Rentang tahun: {min(years_list) if years_list else '?'}–{max(years_list) if years_list else '?'}
Jumlah paper: {len(papers)}
Keyword naik: {rs.get('top_rising','—')} · Keyword turun: {rs.get('top_declining','—')}

Data paper:
""" + "\n".join(f"- {p['title']} ({p.get('year','?')}) · {p.get('citations',0):,} sitasi" for p in papers) + """

Berikan analisis dalam format:

## 🌊 Arus Utama
[Topik apa yang mendominasi dan mengapa]

## 📈 Topik Naik Daun
[Keyword yang frekuensinya meningkat — apa artinya untuk riset baru?]

## 📉 Topik yang Mulai Ditinggalkan
[Keyword yang meredup — apakah sudah terjawab atau memang sudah tidak relevan?]

## 💡 Peluang Tersembunyi
[Celah yang muncul dari pola evolusi ini — cocok untuk topik penelitian baru]"""

                        with st.spinner("Gemini menganalisis arus topik…"):
                            try:
                                resp = model.generate_content(prompt)
                                st.session_state.river_analysis = resp.text
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal: {e}")

                if st.button("🔄 Reset", key="btn_river_reset"):
                    st.session_state.river_fig        = None
                    st.session_state.river_stats_data = None
                    st.session_state.river_analysis   = ""
                    st.rerun()

        # ──────────────────────────────────────────────
        # SUB-TAB 2 — RESEARCH DNA
        # ──────────────────────────────────────────────
        with sub2:
            st.markdown("##### 🧬 Research DNA")
            st.caption(
                "Sidik jari topik setiap paper. "
                "Setiap baris = satu paper. Setiap kolom = satu keyword. "
                "Warna terang = topik sangat dominan di paper tersebut."
            )

            if st.button("▶️ Generate Research DNA", key="btn_dna", use_container_width=True):
                with st.spinner("Membangun DNA matrix…"):
                    try:
                        fig = build_research_dna(papers)
                        st.session_state.dna_fig      = fig
                        st.session_state.dna_analysis = ""
                    except Exception as exc:
                        st.error(f"Gagal: {exc}")

            if st.session_state.dna_fig:
                st.plotly_chart(st.session_state.dna_fig, use_container_width=True)

                st.caption(
                    "💡 Kolom terang = paper sangat fokus pada topik itu · "
                    "Kolom gelap merata = paper generalis · "
                    "Hover untuk detail."
                )

                if st.session_state.dna_analysis:
                    st.markdown("---")
                    st.markdown(st.session_state.dna_analysis)
                    if st.button("🔄 Regenerasi", key="btn_dna_regen"):
                        st.session_state.dna_analysis = ""
                        st.rerun()
                else:
                    if st.button("🔬 Analisis Mendalam — Apa yang membuat tiap paper unik?",
                                 key="btn_dna_ai", use_container_width=True):
                        kws = _top_keywords(papers, n=10)
                        prompt = f"""Kamu adalah analis riset ilmiah senior.

Topik: "{topic}"
Keyword matrix (16 keyword × {len(papers)} paper) sudah dibuat.
Top keywords: {', '.join(kws)}

Data paper:
""" + "\n".join(
    f"- [{p.get('year','?')}] {p['title']} · {p.get('citations',0):,} sitasi · {p.get('venue','?')}"
    for p in papers
) + """

Berikan analisis dalam format:

## 🧬 Pola Spesialisasi
[Paper mana yang sangat spesifik vs generalis berdasarkan topik]

## 🔗 Kluster Tersembunyi
[Paper mana yang ternyata punya DNA topik yang mirip — kandidat untuk dibaca bersama]

## 🎯 Paper Paling Komprehensif
[Paper yang menyentuh paling banyak topik sekaligus — cocok sebagai starting point riset]

## ⚠️ Blank Spot
[Kombinasi keyword penting yang tidak dimiliki paper manapun — ini peluang riset baru]"""

                        with st.spinner("Gemini membaca DNA riset…"):
                            try:
                                resp = model.generate_content(prompt)
                                st.session_state.dna_analysis = resp.text
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal: {e}")

        # ──────────────────────────────────────────────
        # SUB-TAB 3 — CONTRADICTION DETECTOR
        # ──────────────────────────────────────────────
        with sub3:
            st.markdown("##### ⚡ Contradiction Detector")
            st.caption(
                "Pilih **Paper A** dan **Paper B** secara bebas dari dropdown. "
                "Contradiction Meter, sinyal berlawanan, dan verdict update **real-time** "
                "tanpa reload. Tekan ⇄ SWAP untuk tukar posisi."
            )

            if st.button("▶️ Buka Contradiction Arena",
                         key="btn_contra", use_container_width=True):
                with st.spinner("Membangun arena…"):
                    try:
                        html = render_contradiction(papers, height=620)
                        st.session_state.contra_pairs    = html   # reuse key, store HTML
                        st.session_state.contra_analysis = ""
                    except Exception as exc:
                        st.error(f"Gagal: {exc}")

            if st.session_state.contra_pairs:
                st.markdown("---")
                st.caption(
                    "💡 Ganti dropdown Paper A / B → semua panel update instan · "
                    "⇄ SWAP = tukar posisi · Sinyal 🟢 = klaim positif · 🔴 = klaim negatif"
                )
                components.html(
                    _with_fullscreen(st.session_state.contra_pairs),
                    height=642, scrolling=False
                )

                st.markdown("---")
                if st.session_state.contra_analysis:
                    st.markdown(st.session_state.contra_analysis)
                    if st.button("🔄 Regenerasi Analisis", key="btn_contra_regen"):
                        st.session_state.contra_analysis = ""
                        st.rerun()
                else:
                    if st.button("🔬 Analisis Mendalam — Apa implikasi kontradiksi ini?",
                                 key="btn_contra_ai", use_container_width=True):
                        prompt = f"""Kamu adalah metodolog riset ilmiah senior.

Topik: "{topic}"
Jumlah paper dianalisis: {len(papers)}

Data paper (judul + tahun + sitasi):
""" + "\n".join(
    f"- {p['title'][:70]} ({p.get('year','?')}) · {p.get('citations',0):,} sitasi"
    for p in papers[:15]
) + """

Berikan analisis dalam format:

## ⚡ Sumber Kontradiksi Umum
[Mengapa paper dalam bidang ini sering punya kesimpulan yang berbeda]

## 🔬 Yang Harus Diperhatikan Peneliti Baru
[Peringatan konkret saat membaca literatur yang saling bertentangan]

## 🛠️ Cara Mensintesis Temuan Bertentangan
[Strategi praktis: pilih yang mana, gabungkan bagaimana]

## 💡 Peluang dari Ketidaksepakatan
[Kontradiksi ini justru membuka celah riset apa?]"""

                        with st.spinner("Gemini menganalisis kontradiksi…"):
                            try:
                                resp = model.generate_content(prompt)
                                st.session_state.contra_analysis = resp.text
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal: {e}")

                if st.button("🔄 Reset", key="btn_contra_reset"):
                    st.session_state.contra_pairs    = None
                    st.session_state.contra_analysis = ""
                    st.rerun()

        # ──────────────────────────────────────────────
        # SUB-TAB 4 — INFLUENCE MAP
        # ──────────────────────────────────────────────
        with sub4:
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
                with st.spinner("Mengambil jaringan sitasi dari Semantic Scholar…"):
                    try:
                        st.session_state.influence_html       = render_influence(papers, height=700)
                        st.session_state.influence_stats_data = influence_stats(papers)
                    except Exception as exc:
                        st.error(f"Gagal membangun Influence Map: {exc}")

            if st.session_state.influence_html:
                ins = st.session_state.influence_stats_data or {}
                st.markdown("---")
                i1, i2, i3, i4 = st.columns(4)
                i1.metric("Total Paper",     ins.get("total_papers",     "—"))
                i2.metric("Total Node",      ins.get("total_nodes",      "—"))
                i3.metric("Leluhur Ring 1",  ins.get("ancestor_count",   "—"))
                i4.metric("Penerus Ring 2",  ins.get("descendant_count", "—"))
                st.markdown("---")
                ic1, ic2 = st.columns(2)
                ic1.markdown(f"**⭐ Pusat default**  \n_{ins.get('center_title','—')}_")
                ic2.markdown(f"**🌐 Jangkauan**  \n_{ins.get('influence_reach','—')} node_")
                st.markdown("---")
                st.caption("💡 Klik node → detail · ⊙ JADIKAN PUSAT · Toggle PARTICLES / ORBITS / HEATMAP / COMPARE")
                components.html(
                    _with_fullscreen(st.session_state.influence_html),
                    height=720, scrolling=False
                )
                if st.button("🔄 Rebuild", key="btn_influence_reset"):
                    st.session_state.influence_html       = None
                    st.session_state.influence_stats_data = None
                    st.rerun()

        # ──────────────────────────────────────────────
        # SUB-TAB 5 — GAP DETECTOR
        # ──────────────────────────────────────────────
        with sub5:
            st.markdown("##### 🕳️ Research Gap Detector")
            st.caption(
                "Analisis multidimensional celah riset. "
                "4 sub-view: Venn · Heatmap · Gap Score · Hidden Findings."
            )

            if st.button("🔨 Deteksi Research Gap",
                         key="btn_gap", use_container_width=True):
                with st.spinner("Menganalisis celah riset…"):
                    try:
                        st.session_state.gap_html       = render_gap(papers, height=720)
                        st.session_state.gap_stats_data = gap_stats(papers)
                    except Exception as exc:
                        st.error(f"Gagal mendeteksi Gap: {exc}")

            if st.session_state.gap_html:
                gs = st.session_state.gap_stats_data or {}
                st.markdown("---")
                g1, g2, g3, g4 = st.columns(4)
                g1.metric("Total Keyword",  gs.get("total_keywords",     "—"))
                g2.metric("Gap Kritis 🔴",  gs.get("critical_gaps",      "—"))
                g3.metric("Coverage",       f"{gs.get('coverage_score_pct', 0)}%")
                g4.metric("Topik Aman ✅",  f"{gs.get('covered_pct', 0)}%")
                st.markdown("---")
                gc1, gc2 = st.columns(2)
                gc1.markdown(f"**🔴 Gap paling kritis**  \n_{gs.get('top_gap_keyword','—')}_")
                gc2.markdown(f"**✅ Topik terlindungi**  \n_{gs.get('top_covered_keyword','—')}_")
                st.markdown("---")
                st.caption("💡 Tab VENN · HEATMAP · GAP SCORE · HIDDEN FINDINGS ada di dalam komponen · ⎘ SALIN = copy Gap Statement")
                components.html(
                    _with_fullscreen(st.session_state.gap_html),
                    height=740, scrolling=False
                )
                if st.button("🔄 Rebuild", key="btn_gap_reset"):
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
