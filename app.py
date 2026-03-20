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


def build_topic_river(papers: list[dict]):
    """
    Returns a Plotly figure: keyword frequency streams over time.
    Each keyword = one filled area layer. X = year, Y = stacked count.
    """
    import plotly.graph_objects as go

    # Get all years
    years = sorted(set(
        int(p["year"]) for p in papers
        if str(p.get("year", "")).isdigit() and 1900 < int(p["year"]) <= 2030
    ))
    if len(years) < 2:
        return None

    keywords = _top_keywords(papers, n=10)
    if not keywords:
        return None

    # Count keyword frequency per year
    year_kw_counts: dict[int, dict[str, int]] = {y: {k: 0 for k in keywords} for y in years}
    for p in papers:
        y_raw = p.get("year", "")
        if not str(y_raw).isdigit():
            continue
        y = int(y_raw)
        if y not in year_kw_counts:
            continue
        text = (p.get("title", "") or "") + " " + (p.get("abstract", "") or "")
        for t in _tokenize(text):
            if t in year_kw_counts[y]:
                year_kw_counts[y][t] += 1

    # Color palette — cyan to purple
    colors = [
        "rgba(0,212,255,",   "rgba(100,180,255,",
        "rgba(179,157,250,", "rgba(30,232,214,",
        "rgba(255,122,26,",  "rgba(96,176,255,",
        "rgba(248,113,113,", "rgba(74,222,128,",
        "rgba(251,191,36,",  "rgba(232,121,249,",
    ]

    fig = go.Figure()
    cumulative = [0.0] * len(years)

    for ki, kw in enumerate(keywords):
        vals = [year_kw_counts[y][kw] for y in years]
        # Smooth: simple 1-2-1 average
        smoothed = []
        for i in range(len(vals)):
            neighbors = vals[max(0,i-1):i+2]
            smoothed.append(sum(neighbors) / len(neighbors))

        top_vals    = [c + s for c, s in zip(cumulative, smoothed)]
        base_vals   = cumulative[:]
        alpha_fill  = "0.55"
        alpha_line  = "0.9"
        c           = colors[ki % len(colors)]

        # Filled area between cumulative and cumulative+this keyword
        x_fill = years + years[::-1]
        y_fill = top_vals + base_vals[::-1]

        fig.add_trace(go.Scatter(
            x=x_fill, y=y_fill,
            fill="toself",
            mode="none",
            fillcolor=f"{c}{alpha_fill})",
            name=kw,
            hoverinfo="skip",
        ))
        # Top line
        fig.add_trace(go.Scatter(
            x=years, y=top_vals,
            mode="lines",
            line=dict(color=f"{c}{alpha_line})", width=1.5, shape="spline"),
            name=kw,
            hovertemplate=f"<b>{kw}</b><br>Tahun: %{{x}}<br>Frekuensi: {'{:.0f}'.format(0)}<extra></extra>",
            showlegend=True,
        ))
        # Update hover with actual values
        fig.data[-1].customdata = [[f"{v:.0f}"] for v in smoothed]
        fig.data[-1].hovertemplate = f"<b>{kw}</b><br>Tahun: %{{x}}<br>Frekuensi: %{{customdata[0]}}<extra></extra>"

        cumulative = top_vals

    fig.update_layout(
        title=dict(text="🌊 Topic River — Evolusi Topik Riset", font=dict(size=13, color="#e8f4ff")),
        xaxis=dict(title="Tahun", tickmode="linear", dtick=1, gridcolor="rgba(80,140,220,.08)", color="#7aa8cc"),
        yaxis=dict(title="Volume Topik", gridcolor="rgba(80,140,220,.08)", color="#7aa8cc"),
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
            font=dict(size=10, color="#7aa8cc"),
            bgcolor="rgba(5,17,30,.8)",
        ),
        height=400,
        **_PLOTLY_DARK,
    )
    return fig


def build_research_dna(papers: list[dict]):
    """
    Returns a Plotly heatmap figure: papers × keywords matrix.
    Each row = one paper. Each column = one keyword.
    Color intensity = how strongly that keyword appears in that paper.
    """
    import plotly.graph_objects as go

    keywords = _top_keywords(papers, n=16)
    if not keywords:
        return None

    # Score matrix
    matrix = []
    labels_y = []
    for p in papers:
        text = (p.get("title", "") or "") + " " + (p.get("abstract", "") or "")
        tokens = _tokenize(text)
        total = len(tokens) or 1
        freq = collections.Counter(tokens)
        row = [round(freq.get(kw, 0) / total * 100, 2) for kw in keywords]
        matrix.append(row)
        title_short = p["title"][:40] + "…" if len(p["title"]) > 40 else p["title"]
        labels_y.append(f"{p.get('year','?')}  {title_short}")

    # Transpose so keywords are on Y, papers on X
    import numpy as np
    mat = np.array(matrix).T.tolist()

    # Color: black → cyan (custom colorscale)
    colorscale = [
        [0.0,  "#05111e"],
        [0.15, "#0a2240"],
        [0.4,  "#0d4f6e"],
        [0.65, "#0096a8"],
        [0.85, "#00ccdd"],
        [1.0,  "#b39dfa"],
    ]

    hover_text = []
    for ki, kw in enumerate(keywords):
        row_hover = []
        for pi, p in enumerate(papers):
            score = mat[ki][pi]
            row_hover.append(
                f"<b>{kw}</b><br>"
                f"Paper: {p['title'][:50]}…<br>"
                f"Score: {score:.2f}%"
            )
        hover_text.append(row_hover)

    fig = go.Figure(data=go.Heatmap(
        z=mat,
        x=[f"{p.get('year','?')}" for p in papers],
        y=keywords,
        colorscale=colorscale,
        showscale=True,
        colorbar=dict(
            title=dict(text="Bobot", font=dict(color="#7aa8cc", size=10)),
            tickfont=dict(color="#7aa8cc", size=9),
            bgcolor="rgba(5,17,30,.8)",
            bordercolor="rgba(80,140,220,.2)",
        ),
        hoverinfo="text",
        text=hover_text,
        xgap=2,
        ygap=2,
    ))

    fig.update_layout(
        title=dict(text="🧬 Research DNA — Sidik Jari Topik per Paper", font=dict(size=13, color="#e8f4ff")),
        xaxis=dict(title="Paper (per Tahun)", color="#7aa8cc", tickangle=-35, tickfont=dict(size=9)),
        yaxis=dict(title="Keyword", color="#7aa8cc", tickfont=dict(size=10)),
        height=420,
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
        pos = tokens & POSITIVE_SIGNALS
        neg = tokens & NEGATIVE_SIGNALS
        return pos, neg

    def shared_keywords(p1, p2):
        t1 = set(_tokenize((p1.get("title","") or "") + " " + (p1.get("abstract","") or "")))
        t2 = set(_tokenize((p2.get("title","") or "") + " " + (p2.get("abstract","") or "")))
        shared = t1 & t2
        return shared - _STOPWORDS

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

            # Count direct opposing signals
            conflict_count = 0
            conflict_terms = []
            for a_pos, b_neg in [(pos1, neg2), (pos2, neg1)]:
                for a in a_pos:
                    for b in b_neg:
                        if (a, b) in CONTRADICTION_PAIRS or (b, a) in CONTRADICTION_PAIRS:
                            conflict_count += 1
                            conflict_terms.append(f"{a} ↔ {b}")

            # Base score on shared keywords + opposing signals
            base = min(len(shared) * 4, 40)
            signal_score = min(conflict_count * 15, 45)
            # Add score if year gap > 3 (older vs newer may contradict)
            try:
                yr_gap = abs(int(p1.get("year", 0)) - int(p2.get("year", 0)))
            except Exception:
                yr_gap = 0
            time_score = min(yr_gap * 2, 15)

            conflict_score = min(100, base + signal_score + time_score)
            if conflict_score < 20:
                continue

            results.append({
                "paper1_title": p1["title"],
                "paper2_title": p2["title"],
                "paper1_year":  p1.get("year", "?"),
                "paper2_year":  p2.get("year", "?"),
                "paper1_cite":  p1.get("citations", 0),
                "paper2_cite":  p2.get("citations", 0),
                "shared_kws":   sorted(list(shared))[:6],
                "conflict_terms": list(set(conflict_terms))[:4],
                "conflict_score": conflict_score,
                "label": (
                    "⚡ KONFLIK TINGGI" if conflict_score >= 65
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
    """Bar chart of top conflict pairs."""
    import plotly.graph_objects as go

    if not pairs:
        return None

    top = pairs[:8]
    labels = [
        f"{p['paper1_title'][:28]}… vs {p['paper2_title'][:28]}…"
        for p in top
    ]
    scores = [p["conflict_score"] for p in top]
    colors = [p["label_color"] for p in top]

    fig = go.Figure(go.Bar(
        x=scores,
        y=labels,
        orientation="h",
        marker=dict(
            color=colors,
            opacity=0.85,
            line=dict(color="rgba(255,255,255,.1)", width=0.5),
        ),
        hovertemplate=(
            "<b>Conflict Score: %{x}</b><br>"
            "%{y}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title=dict(text="⚡ Contradiction Score — Pasangan Paper Berpotensi Kontradiktif", font=dict(size=13, color="#e8f4ff")),
        xaxis=dict(title="Conflict Score (0–100)", range=[0, 105], color="#7aa8cc"),
        yaxis=dict(tickfont=dict(size=9), color="#7aa8cc"),
        height=max(280, len(top) * 42),
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
            st.markdown("##### 🌊 Topic River")
            st.caption(
                "Bagaimana topik riset berevolusi dari tahun ke tahun. "
                "Setiap aliran berwarna = satu keyword. Makin tebal = makin dominan."
            )

            if st.button("▶️ Generate Topic River", key="btn_river", use_container_width=True):
                with st.spinner("Menganalisis evolusi topik…"):
                    try:
                        fig = build_topic_river(papers)
                        st.session_state.river_fig      = fig
                        st.session_state.river_analysis = ""
                    except Exception as exc:
                        st.error(f"Gagal: {exc}")

            if st.session_state.river_fig:
                st.plotly_chart(st.session_state.river_fig, use_container_width=True)

                # Lazy AI analysis
                if st.session_state.river_analysis:
                    st.markdown("---")
                    st.markdown(st.session_state.river_analysis)
                    if st.button("🔄 Regenerasi", key="btn_river_regen"):
                        st.session_state.river_analysis = ""
                        st.rerun()
                else:
                    if st.button("🔬 Analisis Mendalam — Apa yang terjadi di bidang ini?",
                                 key="btn_river_ai", use_container_width=True):
                        kws = _top_keywords(papers, n=8)
                        years_list = sorted(set(
                            int(p["year"]) for p in papers
                            if str(p.get("year","")).isdigit()
                        ))
                        prompt = f"""Kamu adalah analis riset ilmiah senior.

Topik: "{topic}"
Rentang tahun: {min(years_list) if years_list else '?'}–{max(years_list) if years_list else '?'}
Jumlah paper: {len(papers)}
Keyword paling dominan: {', '.join(kws)}

Data paper:
""" + "\n".join(f"- {p['title']} ({p.get('year','?')}) · {p.get('citations',0):,} sitasi" for p in papers) + """

Berikan analisis singkat dan tajam (3-4 paragraf) dalam format:

## 🌊 Arus Utama
[Topik apa yang mendominasi dan mengapa]

## 📈 Topik Naik Daun
[Keyword mana yang frekuensinya meningkat belakangan ini]

## 📉 Topik yang Mulai Ditinggalkan
[Keyword yang dulu ramai tapi sekarang meredup]

## 💡 Peluang Tersembunyi
[Celah yang muncul dari pola evolusi ini]"""

                        with st.spinner("Gemini menganalisis arus topik…"):
                            try:
                                resp = model.generate_content(prompt)
                                st.session_state.river_analysis = resp.text
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal: {e}")

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
                "Paper mana yang klaimnya berpotensi saling bertentangan? "
                "Skor dihitung dari keyword yang sama tapi sinyal yang berlawanan."
            )

            if st.button("▶️ Deteksi Kontradiksi", key="btn_contra", use_container_width=True):
                with st.spinner("Menganalisis potensi kontradiksi antar paper…"):
                    try:
                        pairs = build_contradiction_data(papers)
                        fig   = build_contradiction_chart(pairs)
                        st.session_state.contra_pairs    = pairs
                        st.session_state.contra_fig      = fig
                        st.session_state.contra_analysis = ""
                    except Exception as exc:
                        st.error(f"Gagal: {exc}")

            if st.session_state.contra_pairs is not None:
                pairs = st.session_state.contra_pairs
                st.markdown("---")

                if not pairs:
                    st.info("✅ Tidak ditemukan potensi kontradiksi signifikan antar paper. Korpus ini cukup konsisten.")
                else:
                    # Metric summary
                    high   = sum(1 for p in pairs if p["conflict_score"] >= 65)
                    medium = sum(1 for p in pairs if 40 <= p["conflict_score"] < 65)
                    low    = sum(1 for p in pairs if p["conflict_score"] < 40)

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Total Pasangan", len(pairs))
                    m2.metric("⚡ Konflik Tinggi", high)
                    m3.metric("⚠️ Berpotensi Beda", medium)
                    m4.metric("🔍 Perlu Dicermati", low)
                    st.markdown("---")

                    # Bar chart
                    if st.session_state.contra_fig:
                        st.plotly_chart(st.session_state.contra_fig, use_container_width=True)

                    # Detail cards per pair
                    st.markdown("#### 📋 Detail Pasangan")
                    for pair in pairs[:6]:
                        with st.expander(
                            f"{pair['label']} · Score {pair['conflict_score']} · "
                            f"{pair['paper1_title'][:45]}… vs {pair['paper2_title'][:45]}…"
                        ):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown(f"**Paper A ({pair['paper1_year']})**")
                                st.markdown(f"_{pair['paper1_title']}_")
                                st.markdown(f"**Sitasi:** {pair['paper1_cite']:,}")
                            with c2:
                                st.markdown(f"**Paper B ({pair['paper2_year']})**")
                                st.markdown(f"_{pair['paper2_title']}_")
                                st.markdown(f"**Sitasi:** {pair['paper2_cite']:,}")
                            st.markdown(f"**Keyword bersama:** `{'` · `'.join(pair['shared_kws'])}`")
                            if pair["conflict_terms"]:
                                st.markdown(f"**Sinyal berlawanan:** `{'` · `'.join(pair['conflict_terms'])}`")

                    # Lazy AI
                    if st.session_state.contra_analysis:
                        st.markdown("---")
                        st.markdown(st.session_state.contra_analysis)
                        if st.button("🔄 Regenerasi", key="btn_contra_regen"):
                            st.session_state.contra_analysis = ""
                            st.rerun()
                    else:
                        if st.button("🔬 Analisis Mendalam — Apa implikasinya bagi riset?",
                                     key="btn_contra_ai", use_container_width=True):
                            top3 = pairs[:3]
                            pairs_text = "\n".join(
                                f"- [{p['conflict_score']}] \"{p['paper1_title'][:60]}\" ({p['paper1_year']}) "
                                f"vs \"{p['paper2_title'][:60]}\" ({p['paper2_year']})"
                                for p in top3
                            )
                            prompt = f"""Kamu adalah metodolog riset ilmiah senior.

Topik: "{topic}"
Jumlah paper: {len(papers)}
Pasangan berpotensi kontradiktif teratas:
{pairs_text}

Berikan analisis dalam format:

## ⚡ Akar Kontradiksi
[Mengapa paper-paper ini bisa berbeda kesimpulan — metodologi, dataset, definisi berbeda?]

## 🔬 Implikasi untuk Peneliti Baru
[Apa yang harus hati-hati dibaca jika ingin masuk ke bidang ini]

## 🛠️ Cara Mensintesis Temuan Bertentangan
[Strategi konkret untuk menggabungkan atau memilih antara klaim yang berlawanan]

## 💡 Peluang Riset dari Kontradiksi
[Justru dari ketidaksepakatan ini, riset apa yang sangat dibutuhkan?]"""

                            with st.spinner("Gemini menganalisis kontradiksi…"):
                                try:
                                    resp = model.generate_content(prompt)
                                    st.session_state.contra_analysis = resp.text
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Gagal: {e}")

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
