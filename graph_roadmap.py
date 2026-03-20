"""
graph_roadmap.py
================
Research Roadmap — Fitur 1 dari Research Intelligence Center

Prinsip desain:
  · Kartu besar (240px), teks jelas terbaca langsung
  · Scroll horizontal native — seperti timeline, zero lag
  · Klik kartu → modal detail yang elegan
  · TIDAK ADA zoom/pan/drag — tidak perlu, tidak bikin bingung
  · 3 baris tier selalu terlihat penuh di layar

Fungsi publik:
  render_roadmap(papers, height)  → str
  roadmap_stats(papers)           → dict
  build_roadmap_data(papers)      → dict
"""

import json
from typing import Optional


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
    return [n["id"] for n in sorted(
        nodes,
        key=lambda n: (n.get("year", 9999), -n.get("citations", 0))
    )]


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
            "id":        pid,
            "title":     title,
            "authors":   p.get("authors", "N/A") or "N/A",
            "year":      year,
            "citations": citations,
            "tier":      tier,
            "venue":     (p.get("venue", "") or "Unknown Venue").strip() or "Unknown Venue",
            "abstract":  abstract,
            "link":      link,
            "source":    p.get("source", "unknown"),
        })

    years    = [n["year"] for n in nodes]
    year_min = min(years, default=2015) - 1
    year_max = max(years, default=2024) + 1

    tier_counts = {"pioneer": 0, "established": 0, "emerging": 0}
    for n in nodes:
        tier_counts[n["tier"]] += 1

    seen_v, venues = set(), []
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
    id_map            = {n["id"]: n for n in nodes}
    most_foundational = max(nodes, key=lambda n: n["citations"], default=None)
    most_recent       = max(nodes, key=lambda n: n["year"],      default=None)
    first_id          = data["reading_path"][0] if data["reading_path"] else None
    recommended_first = id_map[first_id]["title"] if first_id and first_id in id_map else "-"
    yr = data["year_range"]
    return {
        "total_papers":      len(nodes),
        "year_span":         f"{yr[0]+1} \u2013 {yr[1]-1}",
        "pioneer_count":     data["tier_counts"]["pioneer"],
        "established_count": data["tier_counts"]["established"],
        "emerging_count":    data["tier_counts"]["emerging"],
        "most_foundational": most_foundational["title"] if most_foundational else "-",
        "most_recent_title": most_recent["title"] if most_recent else "-",
        "most_recent_year":  most_recent["year"] if most_recent else "-",
        "recommended_first": recommended_first,
        "total_connections": len(data["edges"]),
    }


# ─────────────────────────────────────────────────────────────────
# HTML RENDERING
# ─────────────────────────────────────────────────────────────────

def render_roadmap(papers: list[dict], height: int = 680) -> str:
    data      = build_roadmap_data(papers)
    data_json = (
        json.dumps(data, ensure_ascii=False)
        .replace('<', r'\u003c')
        .replace('/', r'\/')
    )

    # Build year-grouped columns in Python for clean HTML output
    nodes = data["nodes"]
    reading_path = data["reading_path"]
    path_order = {pid: i+1 for i, pid in enumerate(reading_path)}

    # Group nodes per tier per year
    from collections import defaultdict
    grid = defaultdict(lambda: defaultdict(list))  # grid[tier][year]
    for n in nodes:
        grid[n["tier"]][n["year"]].append(n)

    # Collect all years present
    all_years = sorted(set(n["year"] for n in nodes))

    tier_info = {
        "pioneer":     {"label": "PIONEER",     "color": "#b39dfa", "bg": "rgba(179,157,250,.06)", "border": "rgba(179,157,250,.28)"},
        "established": {"label": "ESTABLISHED", "color": "#1ee8d6", "bg": "rgba(30,232,214,.05)",  "border": "rgba(30,232,214,.24)"},
        "emerging":    {"label": "EMERGING",     "color": "#60b0ff", "bg": "rgba(96,176,255,.04)",  "border": "rgba(96,176,255,.2)"},
    }

    venue_colors = [
        "#f472b6","#fb923c","#facc15","#4ade80",
        "#34d399","#818cf8","#c084fc","#f87171","#a3e635","#38bdf8"
    ]
    venue_map = {}
    for i, v in enumerate(data["venues"]):
        venue_map[v] = venue_colors[i % len(venue_colors)]

    # Build cards HTML per tier
    def make_card(n, path_num):
        tier = n["tier"]
        info = tier_info[tier]
        color = info["color"]
        authors_short = ", ".join(n["authors"].split(",")[:2])
        if len(n["authors"].split(",")) > 2:
            authors_short += " et al."
        path_badge = (
            f'<div class="path-badge">#{path_num} Jalur Baca</div>'
            if path_num else ""
        )
        cite_k = ""
        if n["citations"] > 1000:
            cite_k = f"{n['citations']//1000}K"
        elif n["citations"] > 0:
            cite_k = str(n["citations"])
        else:
            cite_k = "—"

        # Escape for HTML
        title_esc   = n["title"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')
        authors_esc = authors_short.replace("&","&amp;").replace("<","&lt;")
        abstract_esc= n["abstract"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')
        venue_esc   = n["venue"].replace("&","&amp;").replace("<","&lt;")
        link        = n["link"] or "#"
        nid         = n["id"].replace('"','').replace("'","")

        return f'''<div class="card tier-{tier}"
  style="--cc:{color}"
  onclick="openModal('{nid}')"
  data-id="{nid}">
  <div class="card-year">{n["year"]}</div>
  {path_badge}
  <div class="card-title">{title_esc}</div>
  <div class="card-authors">{authors_esc}</div>
  <div class="card-foot">
    <span class="card-cite">\u2191 {cite_k}</span>
    <span class="card-src">{n["source"]}</span>
  </div>
</div>'''

    # Build the timeline grid HTML
    # Each tier is a horizontal row with year columns
    tier_rows_html = ""
    for tier in ["pioneer", "established", "emerging"]:
        info = tier_info[tier]

        # Build columns for this tier — one column per year that has cards
        cols_html = ""
        for year in all_years:
            year_nodes = grid[tier].get(year, [])
            if not year_nodes:
                continue
            cards_in_col = "".join(
                make_card(n, path_order.get(n["id"]))
                for n in sorted(year_nodes, key=lambda x: -x["citations"])
            )
            cols_html += (
                f'<div class="col-wrap">'
                f'<div class="col-year">{year}</div>'
                f'{cards_in_col}'
                f'</div>'
            )

        # If tier has no cards at all, show empty placeholder
        if not cols_html:
            cols_html = '<div class="tier-empty-msg">Tidak ada paper di tier ini</div>'

        tier_rows_html += (
            f'<div class="tier-row" '
            f'style="--tier-bg:{info["bg"]};--tier-border:{info["border"]}">'
            f'<div class="tier-label" style="color:{info["color"]}">{info["label"]}</div>'
            f'<div class="tier-scroll">'
            f'<div class="tier-inner">{cols_html}</div>'
            f'</div>'
            f'</div>'
        )

    # Build modal data JSON for JS
    modal_map = {}
    for n in nodes:
        modal_map[n["id"]] = {
            "title":    n["title"],
            "authors":  n["authors"],
            "year":     n["year"],
            "citations":n["citations"],
            "venue":    n["venue"],
            "abstract": n["abstract"],
            "link":     n["link"],
            "tier":     n["tier"],
            "source":   n["source"],
            "path_num": path_order.get(n["id"]),
        }
    modal_json = json.dumps(modal_map, ensure_ascii=False).replace('<', r'\u003c').replace('/', r'\/')

    tier_label_html = "".join(
        f'<span class="leg-item"><span class="leg-dot" style="background:{info["color"]}"></span>{info["label"]}</span>'
        for tier, info in tier_info.items()
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Research Roadmap</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=JetBrains+Mono:wght@400;500&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;
  background:#05111e;
  font-family:'Inter',sans-serif;
  overflow:hidden;
  color:#c8daf0;
}}
:root{{
  --bg:#05111e;
  --bg2:#08192e;
  --border:rgba(80,140,220,.15);
  --text-hi:#e8f4ff;
  --text-mid:#7aa8cc;
  --text-lo:#3a5872;
  --accent:#4a9eff;
  --path-c:#ff7a1a;
  --mono:'JetBrains Mono',monospace;
  --sans:'Inter',sans-serif;
  --disp:'Orbitron',monospace;
}}

/* ── Layout ── */
#rw{{
  display:flex;flex-direction:column;
  height:{height}px;width:100%;
  background:var(--bg);
  position:relative;
}}

/* ── Toolbar ── */
#toolbar{{
  flex-shrink:0;
  display:flex;align-items:center;gap:12px;
  padding:0 18px;height:46px;
  background:rgba(5,17,30,.98);
  border-bottom:1px solid var(--border);
  z-index:20;
}}
.tb-title{{
  font-family:var(--disp);font-size:10px;font-weight:500;
  letter-spacing:3px;color:var(--text-lo);white-space:nowrap;
}}
.tb-sep{{width:1px;height:20px;background:var(--border);}}
.tb-hint{{
  font-family:var(--mono);font-size:9px;color:var(--text-lo);
  letter-spacing:.5px;
}}
.tb-hint span{{color:var(--accent);}}
/* legend */
#legend{{display:flex;align-items:center;gap:14px;margin-left:auto;}}
.leg-item{{
  display:flex;align-items:center;gap:6px;
  font-family:var(--mono);font-size:8.5px;color:var(--text-lo);
}}
.leg-dot{{width:9px;height:9px;border-radius:2px;}}
.leg-path{{
  display:flex;align-items:center;gap:6px;
  font-family:var(--mono);font-size:8.5px;color:var(--path-c);
}}
.leg-path-dot{{
  width:9px;height:9px;border-radius:50%;
  background:var(--path-c);
}}

/* ── Tier rows container ── */
#rows{{
  flex:1;
  display:flex;flex-direction:column;
  overflow:hidden;
  gap:0;
}}

/* ── Single tier row ── */
.tier-row{{
  flex:1;
  display:flex;align-items:stretch;
  border-bottom:1px solid var(--border);
  background:var(--tier-bg);
  min-height:0;
  position:relative;
}}
.tier-row::before{{
  content:'';
  position:absolute;inset:0;pointer-events:none;
  border-left:3px solid var(--tier-border);
}}

/* ── Tier label sidebar ── */
.tier-label{{
  flex-shrink:0;width:72px;
  display:flex;align-items:center;justify-content:center;
  font-family:var(--disp);font-size:8px;font-weight:700;
  letter-spacing:3px;writing-mode:vertical-rl;
  text-transform:uppercase;opacity:.7;
  border-right:1px solid var(--border);
  background:rgba(0,0,0,.15);
}}

/* ── Horizontal scroll area ── */
.tier-scroll{{
  flex:1;
  overflow-x:auto;overflow-y:hidden;
  display:flex;align-items:center;
  padding:10px 16px;
  /* smooth native scroll */
  scroll-behavior:smooth;
  -webkit-overflow-scrolling:touch;
}}
/* custom scrollbar — thin and styled */
.tier-scroll::-webkit-scrollbar{{height:4px;}}
.tier-scroll::-webkit-scrollbar-track{{background:rgba(255,255,255,.03);}}
.tier-scroll::-webkit-scrollbar-thumb{{background:rgba(80,140,220,.25);border-radius:4px;}}
.tier-scroll::-webkit-scrollbar-thumb:hover{{background:rgba(80,140,220,.45);}}

/* ── Inner flex row of year columns ── */
.tier-inner{{
  display:flex;align-items:flex-start;gap:0;
  min-width:max-content;
}}

/* ── Year column ── */
.col-wrap{{
  display:flex;flex-direction:column;align-items:center;
  gap:8px;
  padding:0 10px;
  border-right:1px dashed rgba(80,140,220,.1);
  min-width:260px;
}}
.col-year{{
  font-family:var(--mono);font-size:11px;font-weight:600;
  color:rgba(80,140,220,.45);letter-spacing:1.5px;
  margin-bottom:2px;
}}

/* ── Card ── */
.card{{
  width:240px;
  background:#0a1d35;
  border:1.5px solid rgba(80,140,220,.18);
  border-radius:10px;
  padding:13px 14px 12px 17px;
  cursor:pointer;
  position:relative;
  transition:border-color .2s, box-shadow .2s, transform .15s;
  overflow:hidden;
}}
/* left accent bar */
.card::before{{
  content:'';
  position:absolute;left:0;top:10px;bottom:10px;
  width:3.5px;border-radius:0 3px 3px 0;
  background:var(--cc,var(--accent));
  box-shadow:0 0 8px var(--cc,var(--accent));
  opacity:.9;
}}
.card:hover{{
  border-color:var(--cc,var(--accent));
  box-shadow:0 4px 20px rgba(0,0,0,.45), 0 0 16px rgba(var(--cc-rgb,77,159,255),.1);
  transform:translateY(-2px);
  z-index:5;
}}
/* tier card colors */
.tier-pioneer .card{{
  --cc:#b39dfa;
  border-color:rgba(179,157,250,.22);
  background:linear-gradient(135deg,#0d1c3a 0%,#0a1830 100%);
}}
.tier-pioneer .card:hover{{border-color:#b39dfa;box-shadow:0 4px 20px rgba(0,0,0,.5),0 0 16px rgba(179,157,250,.12);}}
.tier-established .card{{
  --cc:#1ee8d6;
  border-color:rgba(30,232,214,.2);
  background:linear-gradient(135deg,#091d30 0%,#071626 100%);
}}
.tier-established .card:hover{{border-color:#1ee8d6;box-shadow:0 4px 20px rgba(0,0,0,.5),0 0 16px rgba(30,232,214,.1);}}
.tier-emerging .card{{
  --cc:#60b0ff;
  border-color:rgba(96,176,255,.16);
}}
.tier-emerging .card:hover{{border-color:#60b0ff;}}

/* ── Card content ── */
.card-year{{
  position:absolute;top:9px;right:10px;
  font-family:var(--mono);font-size:10px;font-weight:600;
  color:var(--cc,var(--accent));
  padding:2px 8px;border-radius:4px;
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.07);
  letter-spacing:.5px;
}}
.path-badge{{
  display:inline-flex;align-items:center;
  font-family:var(--mono);font-size:8px;letter-spacing:.5px;
  color:var(--path-c);
  margin-bottom:5px;
  background:rgba(255,122,26,.1);
  border:1px solid rgba(255,122,26,.25);
  border-radius:4px;padding:2px 7px;
}}
.card-title{{
  font-family:var(--sans);font-size:13px;font-weight:600;
  color:var(--text-hi);line-height:1.42;
  padding-right:48px;
  /* show full text, no clamp — card height is flexible */
  word-break:break-word;
  margin-bottom:6px;
}}
.card-authors{{
  font-family:var(--sans);font-size:10.5px;
  color:var(--text-mid);opacity:.85;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  margin-bottom:7px;
}}
.card-foot{{
  display:flex;align-items:center;justify-content:space-between;
  border-top:1px solid rgba(255,255,255,.06);
  padding-top:6px;margin-top:2px;
}}
.card-cite{{
  font-family:var(--mono);font-size:9.5px;
  color:var(--cc,var(--accent));font-weight:600;
}}
.card-src{{
  font-family:var(--mono);font-size:8px;
  color:var(--text-lo);
  padding:2px 6px;border-radius:3px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.06);
}}

/* ── Modal overlay ── */
#modal-bg{{
  position:fixed;inset:0;z-index:999;
  background:rgba(2,8,20,.82);
  backdrop-filter:blur(8px);
  display:none;
  align-items:center;justify-content:center;
}}
#modal-bg.open{{display:flex;}}
#modal{{
  width:520px;max-width:90vw;max-height:85vh;
  background:rgba(8,22,42,.99);
  border:1px solid rgba(80,140,220,.28);
  border-radius:14px;padding:28px 30px;
  overflow-y:auto;
  box-shadow:0 24px 80px rgba(0,0,0,.85);
  position:relative;
  animation:modal-in .22s ease;
}}
@keyframes modal-in{{from{{opacity:0;transform:scale(.95)translateY(10px)}}to{{opacity:1;transform:none}}}}
#modal-close{{
  position:absolute;top:16px;right:18px;
  font-size:20px;cursor:pointer;
  color:var(--text-lo);transition:color .15s;line-height:1;
}}
#modal-close:hover{{color:var(--text-hi);}}
.m-tier-badge{{
  display:inline-block;padding:3px 10px;border-radius:4px;margin-bottom:12px;
  font-family:var(--mono);font-size:8px;letter-spacing:1.5px;text-transform:uppercase;font-weight:700;
}}
.m-pioneer{{background:rgba(179,157,250,.14);color:#b39dfa;border:1px solid rgba(179,157,250,.3);}}
.m-established{{background:rgba(30,232,214,.1);color:#1ee8d6;border:1px solid rgba(30,232,214,.25);}}
.m-emerging{{background:rgba(96,176,255,.1);color:#60b0ff;border:1px solid rgba(96,176,255,.22);}}
.m-title{{
  font-family:var(--sans);font-size:18px;font-weight:700;
  color:var(--text-hi);line-height:1.38;margin-bottom:14px;
}}
.m-meta{{
  display:grid;grid-template-columns:1fr 1fr;gap:8px;
  margin-bottom:18px;
}}
.m-row{{
  background:rgba(255,255,255,.03);border:1px solid rgba(80,140,220,.1);
  border-radius:7px;padding:9px 12px;
}}
.m-k{{font-family:var(--mono);font-size:8px;color:var(--text-lo);letter-spacing:1px;text-transform:uppercase;margin-bottom:3px;}}
.m-v{{font-family:var(--mono);font-size:12px;color:var(--accent);font-weight:600;}}
.m-abs-title{{
  font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--text-lo);
  text-transform:uppercase;margin-bottom:8px;
}}
.m-abs{{
  font-family:var(--sans);font-size:13px;color:var(--text-mid);
  line-height:1.65;margin-bottom:20px;
}}
.m-path{{
  display:inline-flex;align-items:center;gap:7px;
  padding:6px 14px;border-radius:6px;margin-bottom:16px;
  background:rgba(255,122,26,.1);border:1px solid rgba(255,122,26,.28);
  color:var(--path-c);font-family:var(--mono);font-size:10px;
}}
.m-btn{{
  display:block;width:100%;padding:12px;text-align:center;
  background:rgba(74,158,255,.08);border:1px solid rgba(74,158,255,.25);
  border-radius:8px;color:var(--accent);
  font-family:var(--mono);font-size:9.5px;letter-spacing:1.5px;
  text-transform:uppercase;text-decoration:none;
  transition:all .15s;
}}
.m-btn:hover{{background:rgba(74,158,255,.18);border-color:rgba(74,158,255,.5);}}
.tier-empty-msg{{
  font-family:var(--mono);font-size:9px;color:var(--text-lo);
  letter-spacing:1px;padding:20px;opacity:.5;
}}
</style>
</head>
<body>
<div id="rw">

<!-- Toolbar -->
<div id="toolbar">
  <span class="tb-title">Research Roadmap ◈</span>
  <div class="tb-sep"></div>
  <span class="tb-hint">Scroll <span>&rarr;</span> untuk navigasi waktu &nbsp;&middot;&nbsp; Klik kartu untuk detail lengkap</span>
  <div id="legend">
    {tier_label_html}
    <span class="leg-path"><span class="leg-path-dot"></span>JALUR BACA</span>
  </div>
</div>

<!-- Tier rows -->
<div id="rows">
{tier_rows_html}
</div>

</div><!-- #rw -->

<!-- Modal -->
<div id="modal-bg" onclick="closeModal(event)">
  <div id="modal">
    <span id="modal-close" onclick="closeModalDirect()">&times;</span>
    <div id="modal-inner"></div>
  </div>
</div>

<script>
const PAPERS = {modal_json};
const PATH_CLR = '#ff7a1a';
const TIER_CLR = {{pioneer:'#b39dfa',established:'#1ee8d6',emerging:'#60b0ff'}};
const TIER_NM  = {{pioneer:'PIONEER',established:'ESTABLISHED',emerging:'EMERGING'}};

function esc(s) {{
  return String(s??'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function openModal(id) {{
  const p = PAPERS[id];
  if (!p) return;

  const tierColor = TIER_CLR[p.tier] || '#4a9eff';
  const cite = p.citations > 1000
    ? Math.round(p.citations/100)/10 + 'K'
    : String(p.citations||'—');

  const pathHtml = p.path_num
    ? `<div class="m-path">&#128205; Urutan Baca #${{p.path_num}} dari {len(reading_path)}</div>`
    : '';

  document.getElementById('modal-inner').innerHTML = `
    <span class="m-tier-badge m-${{p.tier}}">${{TIER_NM[p.tier]}}</span>
    <div class="m-title">${{esc(p.title)}}</div>
    ${{pathHtml}}
    <div class="m-meta">
      <div class="m-row">
        <div class="m-k">TAHUN</div>
        <div class="m-v" style="color:${{tierColor}}">${{p.year}}</div>
      </div>
      <div class="m-row">
        <div class="m-k">SITASI</div>
        <div class="m-v" style="color:${{tierColor}}">&#8593; ${{cite}}</div>
      </div>
      <div class="m-row" style="grid-column:1/-1">
        <div class="m-k">PENULIS</div>
        <div class="m-v" style="font-size:11px;color:var(--text-mid);line-height:1.4;word-break:break-word">${{esc(p.authors)}}</div>
      </div>
      <div class="m-row" style="grid-column:1/-1">
        <div class="m-k">VENUE</div>
        <div class="m-v" style="font-size:11px;color:var(--text-mid)">${{esc(p.venue)}}</div>
      </div>
    </div>
    <div class="m-abs-title">Abstrak</div>
    <div class="m-abs">${{esc(p.abstract||'Abstrak tidak tersedia.')}}</div>
    <a class="m-btn" href="${{esc(p.link||'#')}}" target="_blank">&#8599; Buka Paper Lengkap</a>
  `;

  document.getElementById('modal-bg').classList.add('open');
}}

function closeModal(e) {{
  if (e.target === document.getElementById('modal-bg'))
    document.getElementById('modal-bg').classList.remove('open');
}}
function closeModalDirect() {{
  document.getElementById('modal-bg').classList.remove('open');
}}

// ESC key
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape')
    document.getElementById('modal-bg').classList.remove('open');
}});
</script>
</body>
</html>"""
