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
  · Hover kartu   → tooltip kaya: judul, penulis, abstrak, venue, urutan baca
  · Klik kartu    → mode fokus: panel detail terbuka
  · Klik di luar  → tutup focus mode
  · Slider tahun  → filter real-time tanpa reload
  · Toggle PATH   → tampilkan / sembunyikan jalur baca rekomendasi
  · Toggle VENUE  → warna kartu berdasarkan jurnal/konferensi
  · Toggle EDGE   → tampilkan edge kedekatan antar paper
  · Zoom In/Out   → tombol + scroll mouse
  · Pan           → drag canvas

Fungsi publik:
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
    try:
        y = int(str(val).strip())
        return y if 1900 < y <= 2030 else None
    except (ValueError, TypeError):
        return None


def _assign_tier(citations: int) -> str:
    if citations > 100:
        return "pioneer"
    elif citations >= 20:
        return "established"
    else:
        return "emerging"


def _compute_reading_path(nodes: list[dict]) -> list[str]:
    if not nodes:
        return []
    sorted_nodes = sorted(
        nodes,
        key=lambda n: (n.get("year", 9999), -n.get("citations", 0))
    )
    return [n["id"] for n in sorted_nodes]


def _build_proximity_edges(nodes: list[dict]) -> list[dict]:
    edges = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            diff = abs(a.get("year", 0) - b.get("year", 0))
            if 0 < diff <= 3:
                src, tgt = (a, b) if a["year"] <= b["year"] else (b, a)
                edges.append({
                    "source": src["id"],
                    "target": tgt["id"],
                    "weight": round(1 / (diff + 0.5), 3),
                    "type":   "proximity"
                })
    return edges


def build_roadmap_data(papers: list[dict]) -> dict:
    nodes    = []
    seen_ids = set()

    for i, p in enumerate(papers):
        link = p.get("link", "")
        if "semanticscholar.org/paper/" in link:
            pid = link.split("/paper/")[-1].strip("/")
        else:
            pid = f"p{i}_{p.get('title','x')[:20].replace(' ','_')}"

        if pid in seen_ids:
            pid = f"{pid}_{i}"
        seen_ids.add(pid)

        year      = _parse_year(p.get("year", "")) or 2020
        citations = max(0, int(p.get("citations") or 0))
        tier      = _assign_tier(citations)
        title     = p.get("title", "Untitled").strip()
        abstract  = (p.get("abstract", "") or "Abstrak tidak tersedia.").strip()

        nodes.append({
            "id":          pid,
            "title":       title,
            "title_short": (title[:58] + "…") if len(title) > 58 else title,
            "authors":     p.get("authors", "N/A") or "N/A",
            "year":        year,
            "citations":   citations,
            "tier":        tier,
            "venue":       (p.get("venue", "") or "Unknown Venue").strip() or "Unknown Venue",
            "abstract":    (abstract[:220] + "…") if len(abstract) > 220 else abstract,
            "link":        link,
            "source":      p.get("source", "unknown"),
        })

    years    = [n["year"] for n in nodes]
    year_min = min(years, default=2015) - 1
    year_max = max(years, default=2024) + 1

    tier_counts = {"pioneer": 0, "established": 0, "emerging": 0}
    for n in nodes:
        tier_counts[n["tier"]] += 1

    seen_v = set()
    venues = []
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
    Arsitektur baru:
      · HTML div cards  = teks presisi, CSS line-clamp, tidak pernah overflow
      · SVG overlay     = background bands, axis, reading path, edges
      · Zoom/pan system = mouse wheel + drag + tombol
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
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Share+Tech+Mono&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;overflow:hidden;
  background:#050b1a;color:#c8d6f0;
  font-family:'DM Sans',sans-serif;
  user-select:none;
}}

/* ── Design tokens ── */
:root{{
  --bg:         #050b1a;
  --bg2:        #091525;
  --border:     rgba(99,162,255,.14);
  --border-hi:  rgba(99,162,255,.42);
  --text-hi:    #e8f0ff;
  --text-mid:   #8daacf;
  --text-lo:    #4a6588;
  --accent:     #63a2ff;
  --path-c:     #f97316;
  --path-g:     rgba(249,115,22,.5);
  --mono:       'Share Tech Mono',monospace;
  --disp:       'Orbitron',monospace;
  --body:       'DM Sans',sans-serif;
  --pioneer-c:  #a78bfa;
  --estab-c:    #22d3ee;
  --emerg-c:    #60a5fa;
}}

/* ── Root wrapper ── */
#rw{{
  display:flex;flex-direction:column;
  width:100%;height:{height}px;
  background:var(--bg);
  position:relative;overflow:hidden;
}}
/* scanlines */
#rw::before{{
  content:'';position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(
    0deg,transparent,transparent 3px,
    rgba(0,20,60,.05) 3px,rgba(0,20,60,.05) 4px
  );
}}

/* ── Controls bar ── */
#ctrl{{
  display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  padding:8px 16px;min-height:46px;
  background:rgba(9,21,37,.97);
  border-bottom:1px solid var(--border);
  z-index:30;position:relative;flex-shrink:0;
}}
.c-label{{
  font-family:var(--mono);font-size:9px;letter-spacing:2.5px;
  color:var(--text-lo);text-transform:uppercase;white-space:nowrap;
}}
.c-sep{{width:1px;height:22px;background:var(--border);flex-shrink:0;}}
.c-btn{{
  display:flex;align-items:center;gap:5px;
  padding:5px 12px;border-radius:5px;cursor:pointer;
  font-family:var(--mono);font-size:9.5px;letter-spacing:.8px;
  color:var(--text-mid);background:transparent;
  border:1px solid var(--border);
  transition:all .15s;
}}
.c-btn:hover{{border-color:var(--border-hi);color:var(--text-hi);}}
.c-btn.on{{border-color:var(--path-c);color:var(--path-c);background:rgba(249,115,22,.08);box-shadow:0 0 8px rgba(249,115,22,.18);}}
.c-btn.on-cyan{{border-color:var(--estab-c);color:var(--estab-c);background:rgba(34,211,238,.07);}}
.c-btn.on-ind{{border-color:#818cf8;color:#818cf8;background:rgba(129,140,248,.07);}}
.c-dot{{width:6px;height:6px;border-radius:50%;background:currentColor;flex-shrink:0;}}

/* year slider group */
#yr-grp{{display:flex;align-items:center;gap:8px;flex:1;min-width:160px;}}
#yr-a,#yr-b{{font-family:var(--mono);font-size:10px;color:var(--accent);min-width:32px;text-align:center;}}
input[type=range]{{
  -webkit-appearance:none;height:2px;flex:1;cursor:pointer;
  background:linear-gradient(90deg,var(--accent),var(--pioneer-c));border-radius:2px;
}}
input[type=range]::-webkit-slider-thumb{{
  -webkit-appearance:none;width:12px;height:12px;border-radius:50%;
  background:var(--accent);border:2px solid var(--bg);box-shadow:0 0 5px var(--accent);
}}

/* ── Zoom controls ── */
#zoom-bar{{
  position:absolute;bottom:54px;right:14px;z-index:25;
  display:flex;flex-direction:column;gap:5px;
}}
.z-btn{{
  width:32px;height:32px;border-radius:6px;cursor:pointer;
  background:rgba(9,21,37,.9);border:1px solid var(--border);
  color:var(--text-mid);font-size:16px;line-height:1;
  display:flex;align-items:center;justify-content:center;
  transition:all .15s;
}}
.z-btn:hover{{border-color:var(--border-hi);color:var(--text-hi);background:rgba(99,162,255,.1);}}
#zoom-pct{{
  font-family:var(--mono);font-size:8.5px;color:var(--text-lo);
  text-align:center;letter-spacing:.5px;
}}

/* ── Viewport (canvas area) ── */
#vp{{
  flex:1;position:relative;overflow:hidden;cursor:grab;
}}
#vp.dragging{{cursor:grabbing;}}

/* ── World (transformed container) ── */
#world{{
  position:absolute;
  top:0;left:0;
  transform-origin:0 0;
  /* width/height set by JS */
}}

/* ── SVG background layer ── */
#bg-svg{{
  position:absolute;top:0;left:0;
  pointer-events:none;overflow:visible;
}}

/* SVG classes */
.tier-lbl{{
  font-family:var(--mono);font-size:9px;letter-spacing:3px;
  text-transform:uppercase;dominant-baseline:hanging;
}}
.yr-tick{{
  font-family:var(--mono);font-size:9px;fill:#3d5a78;text-anchor:middle;
}}
.cedge{{fill:none;stroke:rgba(99,102,241,.18);transition:opacity .25s;}}
.cedge.dim{{opacity:.04;}}
.rpath{{
  fill:none;stroke:var(--path-c);stroke-width:2.2;
  stroke-dasharray:8 5;stroke-linecap:round;
  filter:drop-shadow(0 0 4px var(--path-g));
  animation:march 1.5s linear infinite;
}}
@keyframes march{{to{{stroke-dashoffset:-52}}}}
.pb-c{{fill:var(--path-c);filter:drop-shadow(0 0 4px var(--path-g));}}
.pb-t{{
  font-family:var(--mono);font-size:7.5px;font-weight:700;
  fill:#fff;text-anchor:middle;dominant-baseline:central;pointer-events:none;
}}

/* ── HTML Cards layer ── */
#cards-layer{{
  position:absolute;top:0;left:0;
  /* width/height match bg-svg */
}}

/* ── Single card ── */
.rm-card{{
  position:absolute;
  width:182px;
  box-sizing:border-box;
  background:#0b1c37;
  border:1.4px solid rgba(99,162,255,.22);
  border-radius:8px;
  padding:8px 10px 7px 13px;
  cursor:pointer;
  transition:opacity .22s, border-color .18s, box-shadow .18s;
  overflow:hidden;
}}
.rm-card:hover{{
  border-color:rgba(99,162,255,.55);
  box-shadow:0 0 14px rgba(99,162,255,.14);
  z-index:10;
}}
.rm-card.dim{{opacity:.12;}}
.rm-card.focused{{
  border-color:var(--accent);
  box-shadow:0 0 18px rgba(99,162,255,.25);
  z-index:20;
}}

/* Card accent bar (left edge, color per tier) */
.rm-card::before{{
  content:'';position:absolute;left:0;top:7px;bottom:7px;
  width:3px;border-radius:0 2px 2px 0;
  background:var(--card-accent, var(--accent));
}}

/* Card content */
.card-year-chip{{
  position:absolute;top:5px;right:6px;
  padding:2px 7px;border-radius:3px;
  font-family:var(--mono);font-size:9.5px;font-weight:600;
  background:rgba(99,162,255,.1);
  color:var(--card-accent, var(--accent));
  letter-spacing:.5px;
}}
.card-title{{
  font-family:var(--body);font-size:11.5px;font-weight:500;
  color:#d8e8ff;line-height:1.38;
  margin-top:2px;padding-right:36px;
  /* show max 3 lines, clip the rest */
  display:-webkit-box;
  -webkit-line-clamp:3;
  -webkit-box-orient:vertical;
  overflow:hidden;
}}
.card-cite{{
  margin-top:5px;
  font-family:var(--mono);font-size:8.5px;
  color:var(--text-lo);letter-spacing:.3px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}}

/* Tier-specific card colors */
.rm-card.pioneer{{
  --card-accent: var(--pioneer-c);
  border-color:rgba(167,139,250,.28);
  background:rgba(11,28,55,.95);
}}
.rm-card.pioneer:hover{{border-color:rgba(167,139,250,.6);box-shadow:0 0 16px rgba(167,139,250,.14);}}
.rm-card.established{{
  --card-accent: var(--estab-c);
  border-color:rgba(34,211,238,.22);
}}
.rm-card.established:hover{{border-color:rgba(34,211,238,.55);box-shadow:0 0 16px rgba(34,211,238,.12);}}
.rm-card.emerging{{
  --card-accent: var(--emerg-c);
  border-color:rgba(96,165,250,.2);
}}
.rm-card.emerging:hover{{border-color:rgba(96,165,250,.5);}}

/* Venue color override */
.rm-card.venue-colored{{ --card-accent: var(--venue-color, var(--accent)); }}

/* ── Tooltip ── */
#tt{{
  position:fixed;display:none;pointer-events:none;z-index:9999;
  background:rgba(4,12,30,.97);
  border:1px solid rgba(99,162,255,.3);border-radius:10px;
  padding:14px 16px;max-width:300px;min-width:220px;
  box-shadow:0 12px 40px rgba(0,0,0,.75),0 0 18px rgba(99,162,255,.07);
  backdrop-filter:blur(16px);font-size:12px;line-height:1.55;
}}
.tt-title{{font-family:var(--body);font-size:12.5px;font-weight:600;color:var(--text-hi);margin-bottom:6px;line-height:1.35;}}
.tt-meta{{font-family:var(--mono);font-size:9px;color:var(--text-mid);letter-spacing:.3px;margin-bottom:3px;}}
.tt-badge{{
  display:inline-block;padding:2px 8px;border-radius:3px;margin:5px 0 7px;
  font-family:var(--mono);font-size:8px;letter-spacing:1px;
  text-transform:uppercase;font-weight:700;
}}
.tt-badge.pioneer{{background:rgba(167,139,250,.14);color:var(--pioneer-c);border:1px solid rgba(167,139,250,.3);}}
.tt-badge.established{{background:rgba(34,211,238,.1);color:var(--estab-c);border:1px solid rgba(34,211,238,.25);}}
.tt-badge.emerging{{background:rgba(96,165,250,.1);color:var(--emerg-c);border:1px solid rgba(96,165,250,.22);}}
.tt-abs{{font-family:var(--body);font-size:10px;color:var(--text-mid);line-height:1.5;border-top:1px solid rgba(99,162,255,.1);padding-top:6px;margin-top:5px;}}
.tt-hint{{font-family:var(--mono);font-size:8.5px;color:var(--path-c);margin-top:6px;}}

/* ── Detail panel ── */
#dp{{
  position:absolute;right:14px;top:56px;width:265px;
  background:rgba(9,21,37,.97);
  border:1px solid rgba(99,162,255,.22);border-radius:10px;
  padding:16px;display:none;z-index:80;
  backdrop-filter:blur(14px);
  box-shadow:0 10px 40px rgba(0,0,0,.55);
  animation:dp-in .2s ease;
}}
@keyframes dp-in{{from{{opacity:0;transform:translateX(14px)}}to{{opacity:1;transform:none}}}}
#dp.vis{{display:block;}}
.dp-hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:11px;}}
.dp-title{{font-family:var(--body);font-size:12px;font-weight:600;color:var(--text-hi);line-height:1.4;flex:1;padding-right:8px;}}
.dp-x{{cursor:pointer;color:var(--text-lo);font-size:17px;line-height:1;transition:color .15s;}}
.dp-x:hover{{color:var(--text-hi);}}
.dp-row{{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid rgba(99,162,255,.08);}}
.dp-k{{font-family:var(--mono);font-size:8.5px;color:var(--text-lo);letter-spacing:.8px;text-transform:uppercase;}}
.dp-v{{font-family:var(--mono);font-size:10.5px;color:var(--accent);font-weight:600;}}
.dp-abs{{font-family:var(--body);font-size:10px;color:var(--text-mid);line-height:1.5;margin:10px 0;}}
.dp-link{{
  display:block;width:100%;padding:8px;text-align:center;
  background:rgba(99,162,255,.07);border:1px solid rgba(99,162,255,.22);
  border-radius:6px;color:var(--accent);cursor:pointer;
  font-family:var(--mono);font-size:8.5px;letter-spacing:1.5px;
  text-transform:uppercase;text-decoration:none;
  transition:all .15s;
}}
.dp-link:hover{{background:rgba(99,162,255,.16);border-color:rgba(99,162,255,.45);}}
.dp-path{{
  display:inline-flex;align-items:center;gap:5px;margin-top:8px;
  padding:3px 9px;border-radius:4px;
  background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.28);
  color:var(--path-c);font-family:var(--mono);font-size:8.5px;
}}

/* ── Legend ── */
#leg{{
  position:absolute;bottom:12px;left:16px;
  display:flex;align-items:center;gap:16px;z-index:20;
  pointer-events:none;
}}
.leg-i{{display:flex;align-items:center;gap:5px;font-family:var(--mono);font-size:8.5px;color:var(--text-lo);}}
.leg-d{{width:9px;height:9px;border-radius:2px;flex-shrink:0;}}
</style>
</head>
<body>
<div id="rw">

  <!-- Controls bar -->
  <div id="ctrl">
    <span class="c-label">Research Roadmap ◈</span>
    <div class="c-sep"></div>
    <button class="c-btn on"  id="btn-path"  onclick="togglePath()">  <span class="c-dot"></span>READING PATH</button>
    <button class="c-btn"     id="btn-venue" onclick="toggleVenue()"> <span class="c-dot"></span>VENUE CLUSTER</button>
    <button class="c-btn"     id="btn-edge"  onclick="toggleEdge()">  <span class="c-dot"></span>CONNECTIONS</button>
    <div class="c-sep"></div>
    <div id="yr-grp">
      <span class="c-label">SPAN</span>
      <span id="yr-a">—</span>
      <input type="range" id="sl-min" oninput="onYear()">
      <input type="range" id="sl-max" oninput="onYear()">
      <span id="yr-b">—</span>
    </div>
    <div class="c-sep"></div>
    <button class="c-btn" onclick="resetZoom()" title="Reset tampilan">⌖ RESET</button>
  </div>

  <!-- Viewport -->
  <div id="vp">

    <!-- World (scaled/translated) -->
    <div id="world">
      <!-- SVG: bands, axis, edges, path -->
      <svg id="bg-svg" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="arr" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
            <path d="M0,0 L0,7 L7,3.5 z" fill="rgba(99,102,241,.3)"/>
          </marker>
          <filter id="glow-path" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <g id="g-bands"></g>
        <g id="g-axis"></g>
        <g id="g-edges"></g>
        <g id="g-path"></g>
      </svg>

      <!-- HTML Cards -->
      <div id="cards-layer"></div>
    </div>

  </div><!-- #vp -->

  <!-- Zoom controls -->
  <div id="zoom-bar">
    <div class="z-btn" onclick="zoomBy(1.25)" title="Zoom In">+</div>
    <div id="zoom-pct">100%</div>
    <div class="z-btn" onclick="zoomBy(0.8)"  title="Zoom Out">−</div>
  </div>

  <!-- Tooltip -->
  <div id="tt"></div>

  <!-- Detail Panel -->
  <div id="dp">
    <div class="dp-hdr">
      <div class="dp-title" id="dp-title">—</div>
      <span class="dp-x" onclick="closePanel()">✕</span>
    </div>
    <div id="dp-rows"></div>
    <div class="dp-abs" id="dp-abs">—</div>
    <a class="dp-link" id="dp-link" href="#" target="_blank">↗ BUKA PAPER LENGKAP</a>
    <div id="dp-path"></div>
  </div>

  <!-- Legend -->
  <div id="leg">
    <span class="leg-i"><span class="leg-d" style="background:#a78bfa"></span>PIONEER &gt;100 sit.</span>
    <span class="leg-i"><span class="leg-d" style="background:#22d3ee"></span>ESTABLISHED 20–100</span>
    <span class="leg-i"><span class="leg-d" style="background:#60a5fa"></span>EMERGING &lt;20</span>
    <span class="leg-i"><span class="leg-d" style="background:#f97316;border-radius:50%"></span>JALUR BACA</span>
    <span class="leg-i" style="margin-left:8px;color:#5a7aa0">🖱 Drag=pan · Scroll=zoom</span>
  </div>

</div><!-- #rw -->

<script>
/* ════════════════════════════════════════
   DATA
════════════════════════════════════════ */
const D = {data_json};

/* ════════════════════════════════════════
   LAYOUT CONSTANTS
════════════════════════════════════════ */
const CW        = 182;   // card width  (px in virtual space)
const CH        = 104;   // card height (px in virtual space)
const GAP_H     = 18;    // min horizontal gap between cards
const GAP_V     = 12;    // vertical gap between stacked cards
const YEAR_STEP = 210;   // virtual px per year  ← key spacing constant
const LEFT_PAD  = 70;
const RIGHT_PAD = 90;
const TOP_PAD   = 50;    // space above first band
const BAND_H    = 220;   // height per tier band
const AXIS_H    = 52;    // bottom axis area

// Derived virtual canvas size
const YEAR_MIN = D.year_range[0];
const YEAR_MAX = D.year_range[1];
const V_W = LEFT_PAD + (YEAR_MAX - YEAR_MIN) * YEAR_STEP + RIGHT_PAD;
const V_H = TOP_PAD + 3 * BAND_H + AXIS_H;

/* ════════════════════════════════════════
   VENUE COLOR MAP
════════════════════════════════════════ */
const VPALE = [
  '#f472b6','#fb923c','#facc15','#4ade80',
  '#34d399','#818cf8','#c084fc','#f87171','#a3e635','#38bdf8'
];
const venueMap = {{}};
D.venues.forEach((v,i) => {{ venueMap[v] = VPALE[i % VPALE.length]; }});

const TIER_CLR = {{pioneer:'#a78bfa', established:'#22d3ee', emerging:'#60a5fa'}};
const TIER_NM  = {{pioneer:'PIONEER', established:'ESTABLISHED', emerging:'EMERGING'}};

/* ════════════════════════════════════════
   STATE
════════════════════════════════════════ */
const S = {{
  path:    true,
  venue:   false,
  edges:   false,
  focus:   null,
  yMin:    YEAR_MIN,
  yMax:    YEAR_MAX,
}};

/* ════════════════════════════════════════
   ZOOM / PAN STATE
════════════════════════════════════════ */
const Z = {{
  scale: 1,
  tx: 0,
  ty: 0,
  dragging: false,
  startX: 0, startY: 0,
  startTx: 0, startTy: 0,
}};

function applyTransform() {{
  document.getElementById('world').style.transform =
    `translate(${{Z.tx}}px,${{Z.ty}}px) scale(${{Z.scale}})`;
  document.getElementById('zoom-pct').textContent =
    Math.round(Z.scale * 100) + '%';
}}

function clampZoom(s) {{ return Math.max(0.25, Math.min(4, s)); }}

function zoomBy(factor, pivotX, pivotY) {{
  const vp = document.getElementById('vp');
  const rect = vp.getBoundingClientRect();
  const px = (pivotX !== undefined) ? pivotX : rect.width  / 2;
  const py = (pivotY !== undefined) ? pivotY : rect.height / 2;

  const newScale = clampZoom(Z.scale * factor);
  const ratio    = newScale / Z.scale;
  Z.tx = px - (px - Z.tx) * ratio;
  Z.ty = py - (py - Z.ty) * ratio;
  Z.scale = newScale;
  applyTransform();
}}

function resetZoom() {{
  // Fit virtual canvas into viewport
  const vp   = document.getElementById('vp');
  const vpW  = vp.clientWidth;
  const vpH  = vp.clientHeight;
  const sX   = vpW / V_W;
  const sY   = vpH / V_H;
  Z.scale = clampZoom(Math.min(sX, sY) * 0.92);
  Z.tx = (vpW - V_W * Z.scale) / 2;
  Z.ty = (vpH - V_H * Z.scale) / 2;
  applyTransform();
}}

/* ── Wheel zoom ── */
document.getElementById('vp').addEventListener('wheel', e => {{
  e.preventDefault();
  const rect = document.getElementById('vp').getBoundingClientRect();
  const px = e.clientX - rect.left;
  const py = e.clientY - rect.top;
  zoomBy(e.deltaY < 0 ? 1.12 : 0.89, px, py);
}}, {{passive: false}});

/* ── Drag pan ── */
const vp = document.getElementById('vp');
vp.addEventListener('mousedown', e => {{
  if (e.button !== 0) return;
  Z.dragging = true;
  Z.startX = e.clientX; Z.startY = e.clientY;
  Z.startTx = Z.tx;     Z.startTy = Z.ty;
  vp.classList.add('dragging');
}});
window.addEventListener('mousemove', e => {{
  if (!Z.dragging) return;
  Z.tx = Z.startTx + (e.clientX - Z.startX);
  Z.ty = Z.startTy + (e.clientY - Z.startY);
  applyTransform();
}});
window.addEventListener('mouseup', () => {{
  Z.dragging = false;
  vp.classList.remove('dragging');
}});

/* ── Touch pan/pinch ── */
let _touches = [];
vp.addEventListener('touchstart', e => {{
  _touches = [...e.touches];
}}, {{passive: true}});
vp.addEventListener('touchmove', e => {{
  if (e.touches.length === 1 && _touches.length === 1) {{
    const dx = e.touches[0].clientX - _touches[0].clientX;
    const dy = e.touches[0].clientY - _touches[0].clientY;
    Z.tx += dx; Z.ty += dy;
    applyTransform();
    _touches = [...e.touches];
  }} else if (e.touches.length === 2 && _touches.length === 2) {{
    const d0 = Math.hypot(_touches[0].clientX-_touches[1].clientX,
                          _touches[0].clientY-_touches[1].clientY);
    const d1 = Math.hypot(e.touches[0].clientX-e.touches[1].clientX,
                          e.touches[0].clientY-e.touches[1].clientY);
    zoomBy(d1/d0);
    _touches = [...e.touches];
  }}
}}, {{passive: true}});

/* ════════════════════════════════════════
   HELPERS
════════════════════════════════════════ */
function ns(tag, attrs={{}}) {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k,v));
  return el;
}}

function esc(s) {{
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function virtualX(year) {{
  return LEFT_PAD + (year - YEAR_MIN) * YEAR_STEP;
}}

function tierBandTop(tier) {{
  return TOP_PAD + {{pioneer:0, established:1, emerging:2}}[tier] * BAND_H;
}}

function tierBandCY(tier) {{
  return tierBandTop(tier) + BAND_H / 2;
}}

/* ════════════════════════════════════════
   LAYOUT — collision-free card placement
════════════════════════════════════════ */
function computeLayout(nodes) {{
  const MAX_PER_COL = Math.max(1, Math.floor((BAND_H - 30) / (CH + GAP_V)));
  const pos = {{}};

  ['pioneer','established','emerging'].forEach(tier => {{
    const cards = nodes.filter(n => n.tier === tier);
    if (!cards.length) return;

    // Sort by year ASC, then citations DESC
    cards.sort((a,b) => a.year !== b.year
      ? a.year - b.year
      : b.citations - a.citations
    );

    // Group same-year cards
    const yearGroups = {{}};
    cards.forEach(n => {{
      (yearGroups[n.year] = yearGroups[n.year]||[]).push(n);
    }});
    const years = Object.keys(yearGroups).map(Number).sort((a,b)=>a-b);

    let prevRight = -Infinity; // right edge of previous year-group

    years.forEach(year => {{
      const group = yearGroups[year];
      const nCols = Math.ceil(group.length / MAX_PER_COL);
      const groupW = nCols * CW + (nCols-1) * GAP_H;

      // Ideal center X for this year
      const idealCX = virtualX(year);
      // Actual start X: never overlap previous group
      const startX = Math.max(idealCX - groupW/2, prevRight + GAP_H);

      const bandCY = tierBandCY(tier);

      group.forEach((n, gi) => {{
        const col = Math.floor(gi / MAX_PER_COL);
        const row = gi % MAX_PER_COL;
        const colSize = Math.min(MAX_PER_COL, group.length - col * MAX_PER_COL);
        const colH = colSize * CH + (colSize-1) * GAP_V;

        const cx = startX + col * (CW + GAP_H) + CW/2;
        const cy = bandCY - colH/2 + row * (CH + GAP_V) + CH/2;

        pos[n.id] = {{
          left: cx - CW/2,
          top:  cy - CH/2,
          cx, cy
        }};
      }});

      prevRight = startX + groupW;
    }});
  }});

  return pos;
}}

/* ════════════════════════════════════════
   VISIBLE SET (year filter)
════════════════════════════════════════ */
function visibleSet() {{
  return new Set(
    D.nodes.filter(n => n.year >= S.yMin && n.year <= S.yMax).map(n => n.id)
  );
}}

/* ════════════════════════════════════════
   RENDER: SVG BACKGROUND
════════════════════════════════════════ */
function renderBands() {{
  const g = document.getElementById('g-bands');
  g.innerHTML = '';

  const bandAlpha = {{
    pioneer:     'rgba(167,139,250,.03)',
    established: 'rgba(34,211,238,.025)',
    emerging:    'rgba(96,165,250,.02)'
  }};

  ['pioneer','established','emerging'].forEach((t, i) => {{
    const ty = tierBandTop(t);
    // Band fill
    g.appendChild(ns('rect',{{
      x:0, y:ty, width:V_W, height:BAND_H,
      fill: bandAlpha[t]
    }}));
    // Divider
    if (i > 0) {{
      g.appendChild(ns('line',{{
        x1:0, y1:ty, x2:V_W, y2:ty,
        stroke:'rgba(99,162,255,.07)','stroke-dasharray':'4 10'
      }}));
    }}
    // Tier label
    const lbl = ns('text',{{
      x:10, y:ty+14,
      class:'tier-lbl',
      fill: TIER_CLR[t], opacity:'.5'
    }});
    lbl.textContent = TIER_NM[t];
    g.appendChild(lbl);
  }});

  // Vertical year gridlines
  for (let y = YEAR_MIN+1; y <= YEAR_MAX-1; y++) {{
    const x = virtualX(y);
    g.appendChild(ns('line',{{
      x1:x, y1:TOP_PAD, x2:x, y2:V_H - AXIS_H,
      stroke:'rgba(99,162,255,.05)'
    }}));
  }}
}}

function renderAxis() {{
  const g = document.getElementById('g-axis');
  g.innerHTML = '';
  const ay = V_H - AXIS_H;

  g.appendChild(ns('line',{{
    x1:LEFT_PAD/2, y1:ay, x2:V_W - RIGHT_PAD/2, y2:ay,
    stroke:'rgba(99,162,255,.15)'
  }}));

  for (let y = YEAR_MIN+1; y <= YEAR_MAX-1; y++) {{
    const x = virtualX(y);
    g.appendChild(ns('line',{{x1:x,y1:ay,x2:x,y2:ay+5,stroke:'rgba(99,162,255,.2)'}}));
    const t = ns('text',{{x, y:ay+18, class:'yr-tick'}});
    t.textContent = y;
    g.appendChild(t);
  }}
}}

/* ════════════════════════════════════════
   RENDER: EDGES
════════════════════════════════════════ */
function renderEdges(pos) {{
  const g = document.getElementById('g-edges');
  g.innerHTML = '';
  if (!S.edges) return;

  const vis = visibleSet();
  D.edges.forEach(e => {{
    if (!vis.has(e.source) || !vis.has(e.target)) return;
    const a = pos[e.source], b = pos[e.target];
    if (!a || !b) return;

    const mx = (a.cx + b.cx) / 2;
    const p = ns('path', {{
      d:`M${{a.cx}},${{a.cy}} C${{mx}},${{a.cy}} ${{mx}},${{b.cy}} ${{b.cx}},${{b.cy}}`,
      class:'cedge',
      'stroke-width': Math.max(.5, e.weight * 2),
      'marker-end':'url(#arr)'
    }});
    p.dataset.src = e.source;
    p.dataset.tgt = e.target;
    g.appendChild(p);
  }});
}}

/* ════════════════════════════════════════
   RENDER: READING PATH
════════════════════════════════════════ */
function renderPath(pos) {{
  const g = document.getElementById('g-path');
  g.innerHTML = '';
  if (!S.path) return;

  const vis = visibleSet();
  const ids = D.reading_path.filter(id => vis.has(id));
  const pts = ids.map(id => pos[id]).filter(Boolean);
  if (pts.length < 2) return;

  // Smooth bezier through bottom of cards
  const by = pt => pt.cy + CH/2 + 8;
  let d = `M${{pts[0].cx}},${{by(pts[0])}}`;
  for (let i = 1; i < pts.length; i++) {{
    const a = pts[i-1], b = pts[i];
    const mx = (a.cx + b.cx) / 2;
    d += ` C${{mx}},${{by(a)}} ${{mx}},${{by(b)}} ${{b.cx}},${{by(b)}}`;
  }}
  g.appendChild(ns('path',{{d, class:'rpath', filter:'url(#glow-path)'}}));

  // Numbered badges
  ids.forEach((id, i) => {{
    const p = pos[id];
    if (!p) return;
    const cy = by(p);
    g.appendChild(ns('circle',{{cx:p.cx, cy, r:10, class:'pb-c'}}));
    const t = ns('text',{{x:p.cx, y:cy, class:'pb-t'}});
    t.textContent = i+1;
    g.appendChild(t);
  }});
}}

/* ════════════════════════════════════════
   RENDER: HTML CARDS
════════════════════════════════════════ */
function renderCards(pos) {{
  const layer = document.getElementById('cards-layer');
  layer.innerHTML = '';

  const vis = visibleSet();
  const nodes = D.nodes.filter(n => vis.has(n.id));

  nodes.forEach(n => {{
    const p = pos[n.id];
    if (!p) return;

    const tierColor = TIER_CLR[n.tier];
    const venueColor = venueMap[n.venue] || tierColor;
    const cardColor = S.venue ? venueColor : tierColor;

    const div = document.createElement('div');
    div.className = `rm-card ${{n.tier}}${{S.venue ? ' venue-colored' : ''}}${{S.focus===n.id ? ' focused' : ''}}`;
    div.dataset.id = n.id;
    div.style.left  = p.left + 'px';
    div.style.top   = p.top  + 'px';
    if (S.venue) div.style.setProperty('--venue-color', venueColor);
    if (S.focus && S.focus !== n.id) div.classList.add('dim');

    div.innerHTML = `
      <div class="card-year-chip">${{n.year}}</div>
      <div class="card-title">${{esc(n.title)}}</div>
      <div class="card-cite">↑ ${{n.citations.toLocaleString()}} &nbsp;·&nbsp; ${{esc(n.source)}}</div>
    `;

    // Events
    div.addEventListener('mouseenter', e => showTT(e, n, cardColor));
    div.addEventListener('mouseleave', hideTT);
    div.addEventListener('click', e => {{ e.stopPropagation(); openPanel(n); }});
    layer.appendChild(div);
  }});
}}

/* ════════════════════════════════════════
   TOOLTIP
════════════════════════════════════════ */
function showTT(ev, n, color) {{
  const tt  = document.getElementById('tt');
  const pi  = D.reading_path.indexOf(n.id);
  tt.innerHTML = `
    <div class="tt-title">${{esc(n.title)}}</div>
    <div class="tt-meta">👤 ${{esc(n.authors.split(',').slice(0,2).join(', '))}}</div>
    <div class="tt-meta">📅 ${{n.year}} &nbsp;·&nbsp; ↑ ${{n.citations.toLocaleString()}} sitasi</div>
    <div class="tt-meta">🏛 ${{esc(n.venue)}}</div>
    <span class="tt-badge ${{n.tier}}">${{TIER_NM[n.tier]}}</span>
    <div class="tt-abs">${{esc(n.abstract)}}</div>
    ${{pi>=0 ? `<div class="tt-hint">📍 Urutan Baca #${{pi+1}} dari ${{D.reading_path.length}}</div>` : ''}}
    <div class="tt-hint" style="color:var(--accent)">🖱 Klik untuk detail lengkap</div>
  `;
  const mx = ev.clientX + 16;
  const my = ev.clientY - 10;
  const W  = window.innerWidth;
  const H  = window.innerHeight;
  tt.style.cssText = `display:block;left:${{mx+310>W?ev.clientX-320:mx}}px;top:${{my+280>H?ev.clientY-280:my}}px`;
}}
function hideTT() {{ document.getElementById('tt').style.display='none'; }}

/* ════════════════════════════════════════
   DETAIL PANEL
════════════════════════════════════════ */
function openPanel(n) {{
  S.focus = n.id;

  const pi = D.reading_path.indexOf(n.id);
  document.getElementById('dp-title').textContent = n.title;
  document.getElementById('dp-abs').textContent   = n.abstract;
  document.getElementById('dp-link').href         = n.link || '#';

  document.getElementById('dp-rows').innerHTML = `
    <div class="dp-row"><span class="dp-k">TAHUN</span>  <span class="dp-v">${{n.year}}</span></div>
    <div class="dp-row"><span class="dp-k">SITASI</span> <span class="dp-v">${{n.citations.toLocaleString()}}</span></div>
    <div class="dp-row"><span class="dp-k">TIER</span>   <span class="dp-v" style="color:${{TIER_CLR[n.tier]}}">${{TIER_NM[n.tier]}}</span></div>
    <div class="dp-row"><span class="dp-k">VENUE</span>  <span class="dp-v" style="font-size:9px">${{esc(n.venue.substring(0,32))}}</span></div>
  `;

  document.getElementById('dp-path').innerHTML = pi >= 0
    ? `<div class="dp-path">📍 Urutan Baca #${{pi+1}} dari ${{D.reading_path.length}}</div>`
    : '';

  document.getElementById('dp').classList.add('vis');
  renderAll(); // redraw with dim effect
}}

function closePanel() {{
  S.focus = null;
  document.getElementById('dp').classList.remove('vis');
  renderAll();
}}

/* ════════════════════════════════════════
   CONTROLS
════════════════════════════════════════ */
function togglePath() {{
  S.path = !S.path;
  document.getElementById('btn-path').className = 'c-btn' + (S.path ? ' on' : '');
  renderAll();
}}
function toggleVenue() {{
  S.venue = !S.venue;
  document.getElementById('btn-venue').className = 'c-btn' + (S.venue ? ' on-cyan' : '');
  renderAll();
}}
function toggleEdge() {{
  S.edges = !S.edges;
  document.getElementById('btn-edge').className = 'c-btn' + (S.edges ? ' on-ind' : '');
  renderAll();
}}
function onYear() {{
  let a = +document.getElementById('sl-min').value;
  let b = +document.getElementById('sl-max').value;
  if (a > b) {{ a = b; document.getElementById('sl-min').value = a; }}
  S.yMin = a; S.yMax = b;
  document.getElementById('yr-a').textContent = a;
  document.getElementById('yr-b').textContent = b;
  renderAll();
}}

/* ════════════════════════════════════════
   MAIN RENDER
════════════════════════════════════════ */
function renderAll() {{
  const vis   = visibleSet();
  const nodes = D.nodes.filter(n => vis.has(n.id));
  const pos   = computeLayout(nodes);

  renderBands();
  renderAxis();
  renderEdges(pos);
  renderPath(pos);
  renderCards(pos);
}}

/* ════════════════════════════════════════
   INIT
════════════════════════════════════════ */
function init() {{
  // Set virtual canvas size
  const world = document.getElementById('world');
  world.style.width  = V_W + 'px';
  world.style.height = V_H + 'px';

  const svg = document.getElementById('bg-svg');
  svg.style.width  = V_W + 'px';
  svg.style.height = V_H + 'px';
  svg.setAttribute('viewBox', `0 0 ${{V_W}} ${{V_H}}`);

  const cl = document.getElementById('cards-layer');
  cl.style.width  = V_W + 'px';
  cl.style.height = V_H + 'px';

  // Year sliders
  const [mn,mx] = D.year_range;
  ['sl-min','sl-max'].forEach(id => {{
    const sl = document.getElementById(id);
    sl.min = mn; sl.max = mx;
    sl.value = id === 'sl-min' ? mn : mx;
  }});
  document.getElementById('yr-a').textContent = mn;
  document.getElementById('yr-b').textContent = mx;

  renderAll();
  resetZoom(); // fit on load

  // Click outside → close panel
  document.getElementById('vp').addEventListener('click', e => {{
    if (!e.target.closest('.rm-card') && !e.target.closest('#dp'))
      closePanel();
  }});

  // Resize
  let rt;
  window.addEventListener('resize', () => {{
    clearTimeout(rt);
    rt = setTimeout(resetZoom, 120);
  }});
}}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : setTimeout(init, 60);
</script>
</body>
</html>"""
