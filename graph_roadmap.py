"""
graph_roadmap.py
================
Research Roadmap — Fitur 1 dari Research Intelligence Center

Mengubah daftar paper menjadi peta perjalanan intelektual horizontal
yang dapat dinavigasi secara interaktif layaknya command center riset.

Layout:
  Sumbu X  = tahun publikasi (tertua → terbaru)
  Sumbu Y  = lapisan pengaruh berdasarkan jumlah sitasi:
              PIONEER     (>100 sitasi) — lapisan atas
              ESTABLISHED (20–100)      — lapisan tengah
              EMERGING    (<20)         — lapisan bawah

Interaksi:
  · Hover node      → tooltip kaya: judul, penulis, abstrak, venue, urutan baca
  · Klik node       → mode fokus: edge lain memudar, panel detail terbuka
  · Klik di luar    → tutup focus mode
  · Slider tahun    → filter real-time tanpa reload
  · Toggle PATH     → tampilkan / sembunyikan jalur baca rekomendasi (animated)
  · Toggle VENUE    → warna node berubah berdasarkan jurnal/konferensi
  · Toggle CONNECT  → tampilkan edge kedekatan antar paper

Fungsi publik (dipanggil dari graph_layer.py atau tab3_intelligence.py):
  render_roadmap(papers, height)  → str   (HTML siap embed di Streamlit)
  roadmap_stats(papers)           → dict  (ringkasan statistik untuk UI)
  build_roadmap_data(papers)      → dict  (data mentah — untuk testing)
"""

import json
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# 1. DATA PROCESSING
# ─────────────────────────────────────────────────────────────────

def _parse_year(val) -> Optional[int]:
    """Parse tahun dari berbagai format input. Kembalikan None jika tidak valid."""
    try:
        y = int(str(val).strip())
        return y if 1900 < y <= 2030 else None
    except (ValueError, TypeError):
        return None


def _assign_tier(citations: int) -> str:
    """Tentukan lapisan pengaruh berdasarkan jumlah sitasi."""
    if citations > 100:
        return "pioneer"
    elif citations >= 20:
        return "established"
    else:
        return "emerging"


def _compute_reading_path(nodes: list[dict]) -> list[str]:
    """
    Hitung urutan baca yang direkomendasikan.

    Algoritma:
      1. Urutkan secara kronologis (tahun ASC)
      2. Dalam tahun yang sama, prioritaskan citations tertinggi
      3. Hasil = jalur paling logis dari fondasi ke frontier

    Returns:
      list of paper ID dalam urutan rekomendasi
    """
    if not nodes:
        return []
    sorted_nodes = sorted(
        nodes,
        key=lambda n: (n.get("year", 9999), -n.get("citations", 0))
    )
    return [n["id"] for n in sorted_nodes]


def _build_proximity_edges(nodes: list[dict]) -> list[dict]:
    """
    Bangun edge berbasis kedekatan temporal.

    Dua paper terhubung jika:
      · Selisih tahun ≤ 3, DAN
      · Keduanya bukan dari tahun yang sama persis

    Bobot edge = 1 / (year_diff + 0.5) — makin dekat makin tebal.
    """
    edges = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            diff = abs(a.get("year", 0) - b.get("year", 0))
            if 0 < diff <= 3:
                # Edge dari yang lebih lama ke yang lebih baru
                src, tgt = (a, b) if a["year"] <= b["year"] else (b, a)
                edges.append({
                    "source": src["id"],
                    "target": tgt["id"],
                    "weight": round(1 / (diff + 0.5), 3),
                    "type":   "proximity"
                })
    return edges


def build_roadmap_data(papers: list[dict]) -> dict:
    """
    Konversi list paper menjadi struktur data terstruktur untuk
    visualisasi roadmap.

    Input:
      papers — list of dict dari search_papers() / data_layer.py
      Setiap dict harus memiliki: title, year, citations, authors,
      abstract, venue, link, source

    Output:
    {
      "nodes":        list[NodeDict],
      "edges":        list[EdgeDict],
      "reading_path": list[str],       # ID berurutan
      "year_range":   [int, int],      # [min-1, max+1]
      "tier_counts":  dict,
      "venues":       list[str]        # unique, terurut kemunculan
    }
    """
    nodes      = []
    seen_ids   = set()

    for i, p in enumerate(papers):
        # ── Buat ID stabil dari URL Semantic Scholar
        link = p.get("link", "")
        if "semanticscholar.org/paper/" in link:
            pid = link.split("/paper/")[-1].strip("/")
        else:
            pid = f"p{i}_{p.get('title','x')[:20].replace(' ','_')}"

        # Hindari duplikat
        if pid in seen_ids:
            pid = f"{pid}_{i}"
        seen_ids.add(pid)

        year      = _parse_year(p.get("year", "")) or 2020
        citations = max(0, int(p.get("citations") or 0))
        tier      = _assign_tier(citations)
        title     = p.get("title", "Untitled").strip()
        abstract  = (p.get("abstract", "") or "Abstrak tidak tersedia.").strip()

        nodes.append({
            "id":           pid,
            "title":        title,
            "title_short":  (title[:58] + "…") if len(title) > 58 else title,
            "authors":      p.get("authors", "N/A") or "N/A",
            "year":         year,
            "citations":    citations,
            "tier":         tier,
            "venue":        (p.get("venue", "") or "Unknown Venue").strip() or "Unknown Venue",
            "abstract":     (abstract[:220] + "…") if len(abstract) > 220 else abstract,
            "link":         link,
            "source":       p.get("source", "unknown"),
        })

    # ── Year range dengan padding
    years      = [n["year"] for n in nodes]
    year_min   = min(years, default=2015) - 1
    year_max   = max(years, default=2024) + 1

    # ── Tier counts
    tier_counts = {"pioneer": 0, "established": 0, "emerging": 0}
    for n in nodes:
        tier_counts[n["tier"]] += 1

    # ── Unique venues (urutan kemunculan pertama)
    seen_v = set()
    venues  = []
    for n in nodes:
        if n["venue"] not in seen_v:
            seen_v.add(n["venue"])
            venues.append(n["venue"])

    return {
        "nodes":        nodes,
        "edges":        _build_proximity_edges(nodes),
        "reading_path": _compute_reading_path(nodes),
        "year_range":   [year_min, year_max],
        "tier_counts":  tier_counts,
        "venues":       venues,
    }


def roadmap_stats(papers: list[dict]) -> dict:
    """
    Hitung statistik ringkas untuk ditampilkan di UI Streamlit
    (di atas / di bawah komponen roadmap).

    Returns dict:
      total_papers, year_span, pioneer_count, established_count,
      emerging_count, most_foundational, most_recent_title,
      most_recent_year, recommended_first, total_connections
    """
    if not papers:
        return {}

    data  = build_roadmap_data(papers)
    nodes = data["nodes"]
    if not nodes:
        return {}

    id_map = {n["id"]: n for n in nodes}

    most_foundational = max(nodes, key=lambda n: n["citations"], default=None)
    most_recent       = max(nodes, key=lambda n: n["year"],      default=None)

    first_id          = data["reading_path"][0] if data["reading_path"] else None
    recommended_first = id_map[first_id]["title_short"] if first_id and first_id in id_map else "-"

    yr = data["year_range"]
    return {
        "total_papers":      len(nodes),
        "year_span":         f"{yr[0]+1} – {yr[1]-1}",
        "pioneer_count":     data["tier_counts"]["pioneer"],
        "established_count": data["tier_counts"]["established"],
        "emerging_count":    data["tier_counts"]["emerging"],
        "most_foundational": most_foundational["title_short"] if most_foundational else "-",
        "most_recent_title": most_recent["title_short"] if most_recent else "-",
        "most_recent_year":  most_recent["year"] if most_recent else "-",
        "recommended_first": recommended_first,
        "total_connections": len(data["edges"]),
    }


# ─────────────────────────────────────────────────────────────────
# 2. HTML RENDERING
# ─────────────────────────────────────────────────────────────────

def render_roadmap(papers: list[dict], height: int = 680) -> str:
    """
    Render Research Roadmap sebagai HTML interaktif penuh.

    Gunakan di Streamlit:
        import streamlit.components.v1 as components
        components.html(render_roadmap(papers), height=700, scrolling=False)

    Returns:
        str — HTML lengkap siap embed
    """
    data      = build_roadmap_data(papers)
    data_json = (
        json.dumps(data, ensure_ascii=False)
        .replace('<', r'\u003c')
        .replace('/', r'\/')
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Research Roadmap</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Share+Tech+Mono&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;
  background:#050b1a;color:#c8d6f0;
  font-family:'DM Sans',sans-serif;
  overflow:hidden;user-select:none;
}}

/* ── Design Tokens ── */
:root{{
  --bg-deep:      #050b1a;
  --bg-panel:     #091525;
  --bg-card:      #0d1f3c;
  --border-dim:   rgba(99,162,255,0.13);
  --border-glow:  rgba(99,162,255,0.45);
  --text-hi:      #e8f0ff;
  --text-mid:     #8daacf;
  --text-lo:      #4a6588;
  --accent:       #63a2ff;

  --pioneer-c:    #a78bfa;
  --pioneer-g:    rgba(167,139,250,0.45);
  --estab-c:      #22d3ee;
  --estab-g:      rgba(34,211,238,0.35);
  --emerg-c:      #60a5fa;
  --emerg-g:      rgba(96,165,250,0.25);

  --path-c:       #f97316;
  --path-g:       rgba(249,115,22,0.55);
  --edge-c:       rgba(99,102,241,0.22);

  --mono:   'Share Tech Mono',monospace;
  --disp:   'Orbitron',monospace;
  --body:   'DM Sans',sans-serif;
}}

/* ── Root wrapper ── */
#rw{{
  display:flex;flex-direction:column;
  width:100%;height:{height}px;
  background:var(--bg-deep);position:relative;overflow:hidden;
}}

/* Scanline texture overlay */
#rw::before{{
  content:'';position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(
    0deg,transparent,transparent 3px,
    rgba(0,20,60,0.07) 3px,rgba(0,20,60,0.07) 4px
  );
}}

/* ── Controls bar ── */
#ctrl{{
  display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  padding:9px 18px;
  background:rgba(9,21,37,0.97);
  border-bottom:1px solid var(--border-dim);
  z-index:20;position:relative;
}}
.c-label{{
  font-family:var(--mono);font-size:9px;letter-spacing:2.5px;
  color:var(--text-lo);text-transform:uppercase;white-space:nowrap;
}}
.c-sep{{width:1px;height:22px;background:var(--border-dim);}}
.c-btn{{
  display:flex;align-items:center;gap:5px;
  padding:4px 11px;border-radius:4px;cursor:pointer;
  font-family:var(--mono);font-size:9.5px;letter-spacing:1px;
  color:var(--text-mid);background:transparent;
  border:1px solid var(--border-dim);
  transition:all .18s ease;
}}
.c-btn:hover{{border-color:var(--border-glow);color:var(--text-hi);}}
.c-btn.on{{
  border-color:var(--path-c);color:var(--path-c);
  background:rgba(249,115,22,.08);
  box-shadow:0 0 8px rgba(249,115,22,.2);
}}
.c-btn.on-cyan{{
  border-color:var(--estab-c);color:var(--estab-c);
  background:rgba(34,211,238,.07);
}}
.c-btn.on-indigo{{
  border-color:#818cf8;color:#818cf8;
  background:rgba(129,140,248,.07);
}}
.c-dot{{width:6px;height:6px;border-radius:50%;background:currentColor;}}
#yr-grp{{display:flex;align-items:center;gap:8px;flex:1;min-width:180px;}}
#yr-a,#yr-b{{
  font-family:var(--mono);font-size:10px;
  color:var(--accent);min-width:30px;text-align:center;
}}
input[type=range]{{
  -webkit-appearance:none;height:2px;flex:1;cursor:pointer;
  background:linear-gradient(90deg,var(--accent),var(--pioneer-c));
  border-radius:2px;
}}
input[type=range]::-webkit-slider-thumb{{
  -webkit-appearance:none;width:11px;height:11px;
  border-radius:50%;background:var(--accent);
  border:2px solid var(--bg-deep);
  box-shadow:0 0 5px var(--accent);
}}

/* ── SVG area ── */
#sc{{flex:1;position:relative;overflow:hidden;}}
#svg{{width:100%;height:100%;display:block;}}

/* ── SVG text classes ── */
.tier-lbl{{
  font-family:var(--mono);font-size:8.5px;letter-spacing:3px;
  text-transform:uppercase;dominant-baseline:hanging;
}}
.yr-tick{{
  font-family:var(--mono);font-size:9px;fill:#4a6588;text-anchor:middle;
}}
.node-lbl{{
  font-family:var(--body);font-size:11px;fill:#dce8ff;
  pointer-events:none;dominant-baseline:hanging;
}}
.node-cite{{
  font-family:var(--mono);font-size:9px;fill:var(--text-lo);
  pointer-events:none;
}}
.node-yr{{
  font-family:var(--mono);font-size:10px;font-weight:600;
  text-anchor:middle;pointer-events:none;dominant-baseline:central;
}}
.cedge{{
  fill:none;stroke:var(--edge-c);
  transition:opacity .25s;
}}
.cedge.dim{{opacity:.04;}}
.pnode{{cursor:pointer;transition:opacity .25s;}}
.pnode.dim{{opacity:.12;}}
.rpath{{
  fill:none;stroke:var(--path-c);stroke-width:2.5;
  stroke-dasharray:9 5;stroke-linecap:round;
  filter:drop-shadow(0 0 5px var(--path-g));
  animation:march 1.6s linear infinite;
}}
@keyframes march{{to{{stroke-dashoffset:-56}}}}
.pb-c{{fill:var(--path-c);filter:drop-shadow(0 0 5px var(--path-g));}}
.pb-t{{
  font-family:var(--mono);font-size:7.5px;font-weight:700;
  fill:#fff;text-anchor:middle;dominant-baseline:central;pointer-events:none;
}}

/* ── Tooltip ── */
#tt{{
  position:absolute;display:none;pointer-events:none;z-index:200;
  background:rgba(4,12,30,0.97);
  border:1px solid rgba(99,162,255,.28);border-radius:9px;
  padding:14px 16px;max-width:295px;min-width:210px;
  box-shadow:0 10px 40px rgba(0,0,0,.7),0 0 18px rgba(99,162,255,.08);
  backdrop-filter:blur(14px);font-size:11.5px;line-height:1.55;
}}
.tt-title{{font-family:var(--body);font-size:12.5px;font-weight:600;color:var(--text-hi);margin-bottom:5px;line-height:1.35;}}
.tt-meta{{font-family:var(--mono);font-size:9px;color:var(--text-mid);letter-spacing:.4px;margin-bottom:3px;}}
.tt-badge{{
  display:inline-block;padding:2px 8px;border-radius:3px;
  font-family:var(--mono);font-size:8px;letter-spacing:1px;
  text-transform:uppercase;font-weight:700;margin:5px 0 7px;
}}
.tt-badge.pioneer{{background:rgba(167,139,250,.14);color:var(--pioneer-c);border:1px solid rgba(167,139,250,.3);}}
.tt-badge.established{{background:rgba(34,211,238,.1);color:var(--estab-c);border:1px solid rgba(34,211,238,.25);}}
.tt-badge.emerging{{background:rgba(96,165,250,.1);color:var(--emerg-c);border:1px solid rgba(96,165,250,.22);}}
.tt-abs{{
  font-family:var(--body);font-size:10px;color:var(--text-mid);line-height:1.5;
  border-top:1px solid var(--border-dim);padding-top:6px;margin-top:4px;
}}
.tt-hint{{font-family:var(--mono);font-size:8.5px;color:var(--path-c);margin-top:7px;}}

/* ── Focus Detail Panel ── */
#fp{{
  position:absolute;right:14px;top:56px;width:255px;
  background:rgba(9,21,37,.97);
  border:1px solid rgba(99,162,255,.22);border-radius:9px;
  padding:15px;display:none;z-index:80;
  backdrop-filter:blur(14px);
  box-shadow:0 10px 40px rgba(0,0,0,.55);
  animation:slin .22s ease;
}}
@keyframes slin{{from{{opacity:0;transform:translateX(14px)}}to{{opacity:1;transform:none}}}}
#fp.vis{{display:block;}}
.fp-hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;}}
.fp-title{{font-family:var(--body);font-size:12px;font-weight:600;color:var(--text-hi);line-height:1.4;flex:1;padding-right:8px;}}
.fp-x{{cursor:pointer;color:var(--text-lo);font-size:17px;line-height:1;transition:color .15s;}}
.fp-x:hover{{color:var(--text-hi);}}
.fp-row{{
  display:flex;justify-content:space-between;align-items:center;
  padding:5px 0;border-bottom:1px solid var(--border-dim);
}}
.fp-k{{font-family:var(--mono);font-size:9px;color:var(--text-lo);letter-spacing:.8px;text-transform:uppercase;}}
.fp-v{{font-family:var(--mono);font-size:11px;color:var(--accent);font-weight:600;}}
.fp-abs{{font-family:var(--body);font-size:10px;color:var(--text-mid);line-height:1.5;margin:9px 0;}}
.fp-link{{
  display:block;width:100%;padding:8px;text-align:center;
  background:rgba(99,162,255,.08);border:1px solid rgba(99,162,255,.25);
  border-radius:5px;color:var(--accent);cursor:pointer;
  font-family:var(--mono);font-size:8.5px;letter-spacing:1.5px;
  text-transform:uppercase;text-decoration:none;
  transition:all .18s;
}}
.fp-link:hover{{background:rgba(99,162,255,.18);border-color:rgba(99,162,255,.5);}}
.fp-path-badge{{
  display:inline-flex;align-items:center;gap:5px;margin-top:7px;
  padding:3px 9px;border-radius:3px;
  background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.28);
  color:var(--path-c);font-family:var(--mono);font-size:8.5px;
}}

/* ── Legend ── */
#leg{{
  position:absolute;bottom:14px;left:18px;
  display:flex;align-items:center;gap:16px;z-index:10;
}}
.leg-i{{display:flex;align-items:center;gap:5px;font-family:var(--mono);font-size:8.5px;color:var(--text-lo);}}
.leg-d{{width:9px;height:9px;border-radius:2px;flex-shrink:0;}}
</style>
</head>
<body>
<div id="rw">

  <!-- ── Controls ── -->
  <div id="ctrl">
    <span class="c-label">Research Roadmap ◈</span>
    <div class="c-sep"></div>
    <button class="c-btn on"     id="btn-path"  onclick="togglePath()">  <span class="c-dot"></span>READING PATH</button>
    <button class="c-btn"        id="btn-venue" onclick="toggleVenue()"> <span class="c-dot"></span>VENUE CLUSTER</button>
    <button class="c-btn"        id="btn-edge"  onclick="toggleEdge()">  <span class="c-dot"></span>CONNECTIONS</button>
    <div class="c-sep"></div>
    <div id="yr-grp">
      <span class="c-label">SPAN</span>
      <span id="yr-a">—</span>
      <input type="range" id="sl-min" oninput="onYear()">
      <input type="range" id="sl-max" oninput="onYear()">
      <span id="yr-b">—</span>
    </div>
  </div>

  <!-- ── SVG Canvas ── -->
  <div id="sc">
    <svg id="svg" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <filter id="f-pioneer" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="4" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="f-estab" x="-25%" y="-25%" width="150%" height="150%">
          <feGaussianBlur stdDeviation="3" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="f-emerg" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <linearGradient id="bg-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="#050b1a"/>
          <stop offset="100%" stop-color="#020810"/>
        </linearGradient>
        <marker id="arr" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
          <path d="M0,0 L0,7 L7,3.5 z" fill="rgba(99,102,241,0.35)"/>
        </marker>
      </defs>
      <rect width="100%" height="100%" fill="url(#bg-grad)"/>
      <g id="g-bg"></g>
      <g id="g-edge"></g>
      <g id="g-path"></g>
      <g id="g-nodes"></g>
      <g id="g-axis"></g>
    </svg>
  </div>

  <!-- ── Tooltip ── -->
  <div id="tt"></div>

  <!-- ── Focus Panel ── -->
  <div id="fp">
    <div class="fp-hdr">
      <div class="fp-title" id="fp-t">—</div>
      <span class="fp-x" onclick="closeFocus()">✕</span>
    </div>
    <div id="fp-stats"></div>
    <div class="fp-abs" id="fp-abs">—</div>
    <a class="fp-link" id="fp-url" href="#" target="_blank">↗ BUKA PAPER LENGKAP</a>
  </div>

  <!-- ── Legend ── -->
  <div id="leg">
    <span class="leg-i"><span class="leg-d" style="background:#a78bfa"></span>PIONEER &gt;100 sitasi</span>
    <span class="leg-i"><span class="leg-d" style="background:#22d3ee"></span>ESTABLISHED 20–100</span>
    <span class="leg-i"><span class="leg-d" style="background:#60a5fa"></span>EMERGING &lt;20</span>
    <span class="leg-i"><span class="leg-d" style="background:#f97316;border-radius:50%"></span>JALUR BACA</span>
  </div>

</div><!-- #rw -->

<script>
/* ══════════════════════════════════════════════════
   DATA (injected from Python)
══════════════════════════════════════════════════ */
const D = {data_json};

/* ══════════════════════════════════════════════════
   STATE
══════════════════════════════════════════════════ */
const S = {{
  path:     true,
  venue:    false,
  edges:    false,
  focus:    null,
  yMin:     D.year_range[0],
  yMax:     D.year_range[1],
}};

/* ══════════════════════════════════════════════════
   CONSTANTS
══════════════════════════════════════════════════ */
const TIER_CLR = {{pioneer:'#a78bfa', established:'#22d3ee', emerging:'#60a5fa'}};
const TIER_FIL = {{pioneer:'f-pioneer', established:'f-estab', emerging:'f-emerg'}};
const TIER_NM  = {{pioneer:'PIONEER', established:'ESTABLISHED', emerging:'EMERGING'}};
const VPALE = [
  '#f472b6','#fb923c','#facc15','#4ade80','#34d399',
  '#22d3ee','#818cf8','#c084fc','#f87171','#a3e635'
];
const CW=178, CH=76, PX=88, AXISH=44, TOPPAD=72;

/* ══════════════════════════════════════════════════
   DIMENSIONS
══════════════════════════════════════════════════ */
const svgEl  = () => document.getElementById('svg');
const scEl   = () => document.getElementById('sc');
const W      = () => scEl().clientWidth  || 900;
const H      = () => scEl().clientHeight || 490;

function xScale(yr) {{
  const [mn,mx] = D.year_range;
  return PX + ((yr - mn) / (mx - mn)) * (W() - PX*2);
}}

function tierCY(tier) {{
  const bands={{pioneer:0, established:1, emerging:2}};
  const bH = (H() - TOPPAD - AXISH) / 3;
  return TOPPAD + (bands[tier] + 0.5) * bH;
}}
function tierTop(tier) {{
  const bands={{pioneer:0, established:1, emerging:2}};
  return TOPPAD + bands[tier] * ((H() - TOPPAD - AXISH) / 3);
}}
function bandH() {{ return (H() - TOPPAD - AXISH) / 3; }}

/* ══════════════════════════════════════════════════
   LAYOUT — prevent card overlap in same tier+year
══════════════════════════════════════════════════ */
function layoutNodes(nodes) {{
  const GAP = 14;      // vertical gap between stacked cards
  const XSTEP = CW + 18; // horizontal step when staggering needed

  // Group by tier + year
  const grps = {{}};
  nodes.forEach(n => {{
    const k = `${{n.tier}}_${{n.year}}`;
    (grps[k] = grps[k]||[]).push(n);
  }});

  const pos = {{}};

  Object.values(grps).forEach(grp => {{
    const baseX  = xScale(grp[0].year);
    const bH     = bandH();
    const maxPerCol = Math.max(1, Math.floor((bH - 20) / (CH + GAP)));
    const nCols  = Math.ceil(grp.length / maxPerCol);
    const colW   = XSTEP;

    // Total width of all columns; center on baseX
    const totalW = nCols * colW - 18;
    const startX = baseX - totalW / 2;

    grp.forEach((n, i) => {{
      const col      = Math.floor(i / maxPerCol);
      const row      = i % maxPerCol;
      const colItems = grp.slice(col * maxPerCol, (col + 1) * maxPerCol).length;

      const cx   = startX + col * colW + CW / 2;
      const bCY  = tierCY(grp[0].tier);
      const spanH = colItems * (CH + GAP) - GAP;
      const startY = bCY - spanH / 2;
      const cy   = startY + row * (CH + GAP) + CH / 2;

      pos[n.id] = {{x: cx - CW/2, y: cy - CH/2, cx, cy}};
    }});
  }});

  return pos;
}}

/* ══════════════════════════════════════════════════
   SVG HELPERS
══════════════════════════════════════════════════ */
function ns(tag,attrs={{}}) {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));
  return el;
}}

function wrapText(textEl, str, maxW, x) {{
  textEl.textContent = '';
  const words = str.split(' ');
  let line=[], lineN=0;
  const CHAR_W = 6.4;   // avg px per char at 11px DM Sans
  const LINE_H = 13;
  const MAX_LINES = 3;
  words.forEach(w => {{
    if (lineN >= MAX_LINES) return;
    line.push(w);
    if (line.join(' ').length * CHAR_W > maxW && line.length > 1) {{
      line.pop();
      const ts = ns('tspan',{{x, dy: lineN===0?'0':`${{LINE_H}}px`}});
      ts.textContent = line.join(' ');
      textEl.appendChild(ts);
      line=[w]; lineN++;
    }}
  }});
  if(line.length && lineN < MAX_LINES) {{
    const ts = ns('tspan',{{x, dy: lineN===0?'0':`${{LINE_H}}px`}});
    // Truncate last line if still too long
    let txt = line.join(' ');
    while(txt.length * CHAR_W > maxW && txt.length > 3)
      txt = txt.slice(0, -1);
    if(txt !== line.join(' ')) txt += '…';
    ts.textContent = txt;
    textEl.appendChild(ts);
  }}
}}

/* ══════════════════════════════════════════════════
   DRAW: BACKGROUND BANDS + GRID
══════════════════════════════════════════════════ */
function drawBG() {{
  const g = document.getElementById('g-bg');
  g.innerHTML='';
  const w=W(), h=H();
  const bandAlpha = {{pioneer:'rgba(167,139,250,.035)', established:'rgba(34,211,238,.025)', emerging:'rgba(96,165,250,.02)'}};

  ['pioneer','established','emerging'].forEach((t,i) => {{
    // Band fill
    g.appendChild(ns('rect',{{
      x:0, y:tierTop(t), width:w, height:bandH(),
      fill:bandAlpha[t]
    }}));
    // Divider
    if(i>0) {{
      const d = ns('line',{{
        x1:0, y1:tierTop(t), x2:w, y2:tierTop(t),
        stroke:'rgba(99,162,255,.07)', 'stroke-dasharray':'5 10'
      }});
      g.appendChild(d);
    }}
    // Tier label
    const lbl = ns('text',{{
      x:10, y:tierTop(t)+12,
      class:'tier-lbl', fill:TIER_CLR[t], opacity:.45
    }});
    lbl.textContent = TIER_NM[t];
    g.appendChild(lbl);
  }});

  // Vertical year grid lines
  const [mn,mx] = D.year_range;
  for(let y=mn+1; y<=mx-1; y++) {{
    const x = xScale(y);
    g.appendChild(ns('line',{{
      x1:x, y1:TOPPAD, x2:x, y2:h-AXISH,
      stroke:'rgba(99,162,255,.055)'
    }}));
  }}
}}

/* ══════════════════════════════════════════════════
   DRAW: YEAR AXIS
══════════════════════════════════════════════════ */
function drawAxis() {{
  const g = document.getElementById('g-axis');
  g.innerHTML='';
  const w=W(), h=H();
  const [mn,mx] = D.year_range;

  g.appendChild(ns('line',{{
    x1:PX/2, y1:h-AXISH, x2:w-PX/2, y2:h-AXISH,
    stroke:'rgba(99,162,255,.18)'
  }}));

  for(let y=mn+1; y<=mx-1; y++) {{
    const x = xScale(y);
    g.appendChild(ns('line',{{x1:x,y1:h-AXISH,x2:x,y2:h-AXISH+5,stroke:'rgba(99,162,255,.25)'}}));
    const t = ns('text',{{x, y:h-AXISH+18, class:'yr-tick'}});
    t.textContent = y;
    g.appendChild(t);
  }}
}}

/* ══════════════════════════════════════════════════
   DRAW: EDGES
══════════════════════════════════════════════════ */
function drawEdges(pos) {{
  const g = document.getElementById('g-edge');
  g.innerHTML='';
  if(!S.edges) return;

  const vis = visibleSet();
  D.edges.forEach(e => {{
    if(!vis.has(e.source)||!vis.has(e.target)) return;
    const a=pos[e.source], b=pos[e.target];
    if(!a||!b) return;
    const dx = b.cx - a.cx;
    const cpx1 = a.cx + dx*.4, cpx2 = b.cx - dx*.4;
    const p = ns('path',{{
      d:`M${{a.cx}},${{a.cy}} C${{cpx1}},${{a.cy}} ${{cpx2}},${{b.cy}} ${{b.cx}},${{b.cy}}`,
      class:'cedge',
      'stroke-width': Math.max(.5, e.weight*1.8),
      'marker-end':'url(#arr)'
    }});
    p.dataset.src=e.source; p.dataset.tgt=e.target;
    g.appendChild(p);
  }});
}}

/* ══════════════════════════════════════════════════
   DRAW: READING PATH
══════════════════════════════════════════════════ */
function drawPath(pos) {{
  const g = document.getElementById('g-path');
  g.innerHTML='';
  if(!S.path) return;

  const vis = visibleSet();
  const ids = D.reading_path.filter(id=>vis.has(id));
  const pts = ids.map(id=>pos[id]).filter(Boolean);
  if(pts.length<2) return;

  // Smooth cubic bezier path below each card
  let d = `M${{pts[0].cx}},${{pts[0].cy+CH/2+6}}`;
  for(let i=1;i<pts.length;i++) {{
    const a=pts[i-1], b=pts[i];
    const mx=(a.cx+b.cx)/2;
    d+=` C${{mx}},${{a.cy+CH/2+6}} ${{mx}},${{b.cy+CH/2+6}} ${{b.cx}},${{b.cy+CH/2+6}}`;
  }}
  g.appendChild(ns('path',{{d, class:'rpath'}}));

  // Numbered badges
  ids.forEach((id,i) => {{
    const p=pos[id];
    if(!p) return;
    const cy=p.cy+CH/2+6;
    g.appendChild(ns('circle',{{cx:p.cx, cy, r:9, class:'pb-c'}}));
    const t=ns('text',{{x:p.cx, y:cy, class:'pb-t'}});
    t.textContent=i+1;
    g.appendChild(t);
  }});
}}

/* ══════════════════════════════════════════════════
   DRAW: NODES
══════════════════════════════════════════════════ */
function drawNodes(pos) {{
  const g = document.getElementById('g-nodes');
  g.innerHTML='';

  const vis = visibleSet();
  const nodes = D.nodes.filter(n=>vis.has(n.id));

  // Venue → color map
  const vmap={{}};
  D.venues.forEach((v,i)=>{{ vmap[v]=VPALE[i%VPALE.length]; }});

  nodes.forEach(n => {{
    const p=pos[n.id];
    if(!p) return;

    const tc  = S.venue ? (vmap[n.venue]||TIER_CLR[n.tier]) : TIER_CLR[n.tier];
    const fil = TIER_FIL[n.tier];

    const grp = ns('g',{{class:'pnode', transform:`translate(${{p.x}},${{p.y}})`}});
    grp.dataset.id = n.id;

    // Outer glow ring
    grp.appendChild(ns('rect',{{
      x:-4,y:-4, width:CW+8, height:CH+8, rx:10,
      fill:'none', stroke:tc, 'stroke-width':'1', opacity:'.18',
      filter:`url(#${{fil}})`
    }}));

    // Card body
    grp.appendChild(ns('rect',{{
      width:CW, height:CH, rx:7,
      fill:'#0b1c37', stroke:tc, 'stroke-width':'1.4', opacity:'.88',
      class:'node-card'
    }}));

    // Left accent bar
    grp.appendChild(ns('rect',{{
      x:0,y:8, width:3, height:CH-16, rx:2,
      fill:tc, opacity:'.9'
    }}));

    // Year chip (top-right)
    grp.appendChild(ns('rect',{{
      x:CW-38,y:5, width:32,height:16, rx:3,
      fill:tc, opacity:'.13'
    }}));
    const yTxt=ns('text',{{x:CW-22,y:13.5,class:'node-yr',fill:tc}});
    yTxt.textContent=n.year;
    grp.appendChild(yTxt);

    // Title
    const tTxt=ns('text',{{x:10,y:22,class:'node-lbl'}});
    wrapText(tTxt, n.title_short, CW-52, 10);
    grp.appendChild(tTxt);

    // Citation line
    const cTxt=ns('text',{{x:10,y:CH-8,class:'node-cite',fill:tc}});
    cTxt.textContent=`↑ ${{n.citations.toLocaleString()}} · ${{n.source}}`;
    grp.appendChild(cTxt);

    // Events
    grp.addEventListener('mouseenter', e => showTT(e,n));
    grp.addEventListener('mouseleave', hideTT);
    grp.addEventListener('click', () => setFocus(n.id));
    g.appendChild(grp);
  }});
}}

/* ══════════════════════════════════════════════════
   TOOLTIP
══════════════════════════════════════════════════ */
function showTT(ev, n) {{
  const tt  = document.getElementById('tt');
  const pi  = D.reading_path.indexOf(n.id);
  const badgeC = TIER_CLR[n.tier];
  tt.innerHTML = `
    <div class="tt-title">${{n.title}}</div>
    <div class="tt-meta">👤 ${{n.authors.split(',').slice(0,2).join(', ')}}</div>
    <div class="tt-meta">📅 ${{n.year}} &nbsp;·&nbsp; ↑ ${{n.citations.toLocaleString()}} sitasi</div>
    <div class="tt-meta">🏛️ ${{n.venue}}</div>
    <span class="tt-badge ${{n.tier}}">${{TIER_NM[n.tier]}}</span>
    <div class="tt-abs">${{n.abstract}}</div>
    ${{pi>=0 ? `<div class="tt-hint">📍 Urutan Baca #${{pi+1}} dari ${{D.reading_path.length}}</div>` : ''}}
    <div class="tt-hint" style="color:var(--accent)">🖱️ Klik untuk detail lengkap</div>
  `;
  const sc = document.getElementById('sc').getBoundingClientRect();
  let tx = ev.clientX - sc.left + 14;
  let ty = ev.clientY - sc.top  - 10;
  if(tx+310>sc.width)  tx = ev.clientX - sc.left - 310;
  if(ty+220>sc.height) ty = ev.clientY - sc.top  - 220;
  tt.style.cssText=`display:block;left:${{tx}}px;top:${{ty}}px`;
}}
function hideTT() {{ document.getElementById('tt').style.display='none'; }}

/* ══════════════════════════════════════════════════
   FOCUS MODE
══════════════════════════════════════════════════ */
function setFocus(id) {{
  hideTT();
  S.focus = id;
  const n = D.nodes.find(x=>x.id===id);
  if(!n) return;

  // Update panel
  const pi = D.reading_path.indexOf(id);
  document.getElementById('fp-t').textContent   = n.title;
  document.getElementById('fp-abs').textContent = n.abstract;
  document.getElementById('fp-url').href        = n.link||'#';

  document.getElementById('fp-stats').innerHTML = `
    <div class="fp-row"><span class="fp-k">TAHUN</span><span class="fp-v">${{n.year}}</span></div>
    <div class="fp-row"><span class="fp-k">SITASI</span><span class="fp-v">${{n.citations.toLocaleString()}}</span></div>
    <div class="fp-row"><span class="fp-k">VENUE</span><span class="fp-v" style="font-size:8.5px">${{n.venue.substring(0,30)}}</span></div>
    <div class="fp-row"><span class="fp-k">TIER</span><span class="fp-v" style="color:${{TIER_CLR[n.tier]}}">${{TIER_NM[n.tier]}}</span></div>
    ${{pi>=0 ? `<div class="fp-path-badge"><span>📍</span>Urutan Baca #${{pi+1}} dari ${{D.reading_path.length}}</div>` : ''}}
  `;
  document.getElementById('fp').classList.add('vis');
  applyDim(id);
}}

function closeFocus() {{
  S.focus=null;
  document.getElementById('fp').classList.remove('vis');
  document.querySelectorAll('.pnode').forEach(e=>e.classList.remove('dim'));
  document.querySelectorAll('.cedge').forEach(e=>e.classList.remove('dim'));
}}

function applyDim(id) {{
  const conn=new Set([id]);
  D.edges.forEach(e=>{{
    if(e.source===id) conn.add(e.target);
    if(e.target===id) conn.add(e.source);
  }});
  const pi=D.reading_path.indexOf(id);
  if(pi>0)                     conn.add(D.reading_path[pi-1]);
  if(pi>=0&&pi<D.reading_path.length-1) conn.add(D.reading_path[pi+1]);

  document.querySelectorAll('.pnode').forEach(e=>{{
    e.classList.toggle('dim', !conn.has(e.dataset.id));
  }});
  document.querySelectorAll('.cedge').forEach(e=>{{
    e.classList.toggle('dim', e.dataset.src!==id && e.dataset.tgt!==id);
  }});
}}

/* ══════════════════════════════════════════════════
   CONTROLS
══════════════════════════════════════════════════ */
function togglePath() {{
  S.path=!S.path;
  document.getElementById('btn-path').className='c-btn'+(S.path?' on':'');
  render();
}}
function toggleVenue() {{
  S.venue=!S.venue;
  document.getElementById('btn-venue').className='c-btn'+(S.venue?' on-cyan':'');
  render();
}}
function toggleEdge() {{
  S.edges=!S.edges;
  document.getElementById('btn-edge').className='c-btn'+(S.edges?' on-indigo':'');
  render();
}}
function onYear() {{
  let a=+document.getElementById('sl-min').value;
  let b=+document.getElementById('sl-max').value;
  if(a>b){{ a=b; document.getElementById('sl-min').value=a; }}
  S.yMin=a; S.yMax=b;
  document.getElementById('yr-a').textContent=a;
  document.getElementById('yr-b').textContent=b;
  render();
}}
function initSliders() {{
  const [mn,mx]=D.year_range;
  ['sl-min','sl-max'].forEach(id=>{{
    const sl=document.getElementById(id);
    sl.min=mn; sl.max=mx;
    sl.value= id==='sl-min'?mn:mx;
  }});
  document.getElementById('yr-a').textContent=mn;
  document.getElementById('yr-b').textContent=mx;
}}

/* ══════════════════════════════════════════════════
   VISIBLE SET
══════════════════════════════════════════════════ */
function visibleSet() {{
  return new Set(D.nodes.filter(n=>n.year>=S.yMin&&n.year<=S.yMax).map(n=>n.id));
}}

/* ══════════════════════════════════════════════════
   MAIN RENDER
══════════════════════════════════════════════════ */
function render() {{
  const nodes = D.nodes.filter(n=>n.year>=S.yMin&&n.year<=S.yMax);
  const pos   = layoutNodes(nodes);
  drawBG();
  drawAxis();
  drawEdges(pos);
  drawPath(pos);
  drawNodes(pos);
  if(S.focus) applyDim(S.focus);
}}

/* ══════════════════════════════════════════════════
   INIT
══════════════════════════════════════════════════ */
function init() {{
  initSliders();
  render();

  // Resize handler
  let rt;
  window.addEventListener('resize', ()=>{{clearTimeout(rt);rt=setTimeout(render,90);}});

  // Click svg background → close focus
  document.getElementById('svg').addEventListener('click', ev=>{{
    if(ev.target.id==='svg'||ev.target.tagName==='rect'&&!ev.target.closest('.pnode'))
      closeFocus();
  }});
}}

document.readyState==='loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : setTimeout(init, 60);
</script>
</body>
</html>"""
