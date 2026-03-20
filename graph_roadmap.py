"""
graph_roadmap.py
================
Research Roadmap — Fitur 1 dari Research Intelligence Center

Filosofi desain:
  · Kartu besar dan langsung terbaca tanpa perlu zoom
  · Navigasi = drag horizontal (scroll waktu)
  · Zoom dikekang: tidak bisa zoom out sampai void kosong
  · Canvas tingginya pas dengan viewport

Fungsi publik:
  render_roadmap(papers, height)  -> str
  roadmap_stats(papers)           -> dict
  build_roadmap_data(papers)      -> dict
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
            "abstract":    (abstract[:280] + "…") if len(abstract) > 280 else abstract,
            "link":        link,
            "source":      p.get("source", "unknown"),
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


def render_roadmap(papers: list[dict], height: int = 680) -> str:
    data      = build_roadmap_data(papers)
    data_json = (
        json.dumps(data, ensure_ascii=False)
        .replace('<', r'\u003c')
        .replace('/', r'\/')
    )
    return _build_html(data_json, height)


def _build_html(data_json: str, height: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Research Roadmap</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;overflow:hidden;
  background:#06101f;font-family:'Inter',sans-serif;
  user-select:none;-webkit-user-select:none;
}}
:root{{
  --bg:#06101f;--bg-card:#0c1e3a;
  --border:rgba(99,162,255,.18);--border-hi:rgba(99,162,255,.5);
  --text-hi:#eaf2ff;--text-mid:#7fa8d0;--text-lo:#3d5e82;
  --accent:#4d9fff;--path-c:#ff7a1a;
  --pc:#b39dfa;--ec:#1ee8d6;--mc:#60b0ff;
  --mono:'JetBrains Mono',monospace;
  --sans:'Inter',sans-serif;
}}
#rw{{
  display:flex;flex-direction:column;
  width:100%;height:{height}px;
  background:var(--bg);position:relative;overflow:hidden;
}}
#rw::before{{
  content:'';position:absolute;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(ellipse 60% 40% at 20% 50%,rgba(40,60,120,.16) 0%,transparent 70%),
    radial-gradient(ellipse 50% 35% at 80% 50%,rgba(20,50,100,.12) 0%,transparent 70%);
}}
/* toolbar */
#ctrl{{
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:9px 18px;min-height:48px;
  background:rgba(6,16,31,.98);border-bottom:1px solid var(--border);
  z-index:50;position:relative;flex-shrink:0;
}}
.c-lbl{{font-family:var(--mono);font-size:9px;letter-spacing:2.5px;color:var(--text-lo);text-transform:uppercase;white-space:nowrap;}}
.c-sep{{width:1px;height:22px;background:var(--border);flex-shrink:0;}}
.c-btn{{
  display:inline-flex;align-items:center;gap:5px;
  padding:5px 13px;border-radius:5px;cursor:pointer;
  font-family:var(--mono);font-size:9px;letter-spacing:.8px;
  color:var(--text-mid);background:transparent;border:1px solid var(--border);
  transition:all .15s;white-space:nowrap;
}}
.c-btn:hover{{border-color:var(--border-hi);color:var(--text-hi);}}
.c-btn.on{{border-color:var(--path-c);color:var(--path-c);background:rgba(255,122,26,.08);box-shadow:0 0 8px rgba(255,122,26,.2);}}
.c-btn.on-t{{border-color:var(--ec);color:var(--ec);background:rgba(30,232,214,.07);}}
.c-btn.on-b{{border-color:var(--mc);color:var(--mc);background:rgba(96,176,255,.07);}}
.c-dot{{width:7px;height:7px;border-radius:50%;background:currentColor;flex-shrink:0;}}
#yr-grp{{display:flex;align-items:center;gap:9px;min-width:180px;flex:1;}}
.yr-v{{
  font-family:var(--mono);font-size:10px;color:var(--accent);min-width:34px;text-align:center;
  padding:2px 6px;background:rgba(77,159,255,.08);border-radius:3px;border:1px solid rgba(77,159,255,.2);
}}
input[type=range]{{
  -webkit-appearance:none;appearance:none;height:3px;flex:1;cursor:pointer;border-radius:3px;
  background:linear-gradient(90deg,var(--accent),var(--pc));
}}
input[type=range]::-webkit-slider-thumb{{
  -webkit-appearance:none;width:13px;height:13px;border-radius:50%;
  background:var(--accent);border:2px solid var(--bg);box-shadow:0 0 6px var(--accent);
}}
/* zoom controls */
#zm{{
  position:absolute;top:58px;right:16px;z-index:60;
  display:flex;flex-direction:column;align-items:center;gap:4px;
}}
.zb{{
  width:34px;height:34px;border-radius:7px;
  background:rgba(6,22,42,.92);border:1px solid var(--border);
  color:var(--text-mid);font-size:18px;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;transition:all .15s;
}}
.zb:hover{{background:rgba(77,159,255,.12);border-color:var(--border-hi);color:var(--text-hi);}}
#zm-pct{{font-family:var(--mono);font-size:8px;color:var(--text-lo);letter-spacing:.5px;padding:2px 4px;}}
.zb.sm{{font-size:10px;font-family:var(--mono);letter-spacing:.5px;}}
/* viewport */
#vp{{flex:1;position:relative;overflow:hidden;cursor:grab;}}
#vp.drag{{cursor:grabbing;}}
#world{{position:absolute;top:0;left:0;transform-origin:0 0;will-change:transform;}}
/* svg */
#bg-svg{{position:absolute;top:0;left:0;pointer-events:none;overflow:visible;}}
.tier-lbl{{font-family:var(--mono);font-size:10px;letter-spacing:3px;text-transform:uppercase;dominant-baseline:hanging;font-weight:500;}}
.yr-tick{{font-family:var(--mono);font-size:10px;fill:#2d4a68;text-anchor:middle;}}
.cedge{{fill:none;stroke:rgba(99,130,255,.18);transition:opacity .25s;}}
.cedge.dim{{opacity:.03;}}
.rpath{{
  fill:none;stroke:var(--path-c);stroke-width:2.5;
  stroke-dasharray:10 6;stroke-linecap:round;
  filter:drop-shadow(0 0 5px rgba(255,122,26,.6));
  animation:march 1.6s linear infinite;
}}
@keyframes march{{to{{stroke-dashoffset:-64}}}}
.pb-c{{fill:var(--path-c);filter:drop-shadow(0 0 5px rgba(255,122,26,.7));}}
.pb-t{{font-family:var(--mono);font-size:8.5px;font-weight:700;fill:#fff;text-anchor:middle;dominant-baseline:central;pointer-events:none;}}
/* cards layer */
#cl{{position:absolute;top:0;left:0;}}
/* card */
.card{{
  position:absolute;width:220px;
  background:var(--bg-card);border-radius:10px;
  border:1.5px solid rgba(99,162,255,.2);
  padding:12px 13px 11px 17px;
  cursor:pointer;overflow:hidden;
  transition:border-color .18s,box-shadow .18s,opacity .22s;
}}
.card::before{{
  content:'';position:absolute;left:0;top:10px;bottom:10px;
  width:4px;border-radius:0 3px 3px 0;
  background:var(--cc,var(--accent));
  box-shadow:0 0 8px var(--cc,var(--accent));
}}
.card:hover{{border-color:rgba(99,162,255,.55);box-shadow:0 4px 24px rgba(0,0,0,.4),0 0 18px rgba(99,162,255,.1);z-index:10;}}
.card.focused{{border-color:var(--accent);box-shadow:0 6px 28px rgba(0,0,0,.5),0 0 22px rgba(77,159,255,.2);z-index:20;}}
.card.dim{{opacity:.1;pointer-events:none;}}
.card.pioneer{{--cc:var(--pc);border-color:rgba(179,157,250,.25);background:linear-gradient(135deg,#0e1d3e,#0c1a38);}}
.card.pioneer:hover{{border-color:rgba(179,157,250,.6);box-shadow:0 4px 24px rgba(0,0,0,.5),0 0 18px rgba(179,157,250,.12);}}
.card.established{{--cc:var(--ec);border-color:rgba(30,232,214,.22);background:linear-gradient(135deg,#091e32,#081828);}}
.card.established:hover{{border-color:rgba(30,232,214,.55);box-shadow:0 4px 24px rgba(0,0,0,.4),0 0 18px rgba(30,232,214,.1);}}
.card.emerging{{--cc:var(--mc);border-color:rgba(96,176,255,.18);}}
.card.vc{{--cc:var(--vc,var(--accent));}}
/* card content */
.c-chip{{
  position:absolute;top:8px;right:9px;
  font-family:var(--mono);font-size:10px;font-weight:600;
  padding:3px 8px;border-radius:4px;
  background:rgba(255,255,255,.05);
  color:var(--cc,var(--accent));letter-spacing:.5px;
  border:1px solid rgba(255,255,255,.07);
}}
.c-title{{
  font-family:var(--sans);font-size:13px;font-weight:600;
  color:var(--text-hi);line-height:1.42;
  padding-right:42px;margin-top:1px;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;
  min-height:54px;
}}
.c-authors{{
  font-family:var(--sans);font-size:10.5px;color:var(--text-mid);
  margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.85;
}}
.c-foot{{display:flex;align-items:center;justify-content:space-between;margin-top:7px;}}
.c-cite{{font-family:var(--mono);font-size:9.5px;color:var(--cc,var(--accent));font-weight:500;letter-spacing:.3px;}}
.c-src{{font-family:var(--mono);font-size:8px;color:var(--text-lo);padding:2px 6px;background:rgba(255,255,255,.04);border-radius:3px;border:1px solid rgba(255,255,255,.06);}}
/* tooltip */
#tt{{
  position:fixed;display:none;pointer-events:none;z-index:9999;
  background:rgba(5,14,30,.97);border:1px solid rgba(99,162,255,.32);border-radius:12px;
  padding:16px 18px;max-width:320px;min-width:240px;
  box-shadow:0 16px 48px rgba(0,0,0,.8);backdrop-filter:blur(18px);
}}
.tt-t{{font-family:var(--sans);font-size:13.5px;font-weight:700;color:var(--text-hi);margin-bottom:8px;line-height:1.35;}}
.tt-m{{font-family:var(--mono);font-size:9.5px;color:var(--text-mid);letter-spacing:.3px;margin-bottom:4px;}}
.tt-badge{{display:inline-block;padding:3px 9px;border-radius:4px;margin:6px 0 8px;font-family:var(--mono);font-size:8px;letter-spacing:1px;text-transform:uppercase;font-weight:700;}}
.tt-badge.pioneer{{background:rgba(179,157,250,.14);color:var(--pc);border:1px solid rgba(179,157,250,.32);}}
.tt-badge.established{{background:rgba(30,232,214,.1);color:var(--ec);border:1px solid rgba(30,232,214,.28);}}
.tt-badge.emerging{{background:rgba(96,176,255,.1);color:var(--mc);border:1px solid rgba(96,176,255,.25);}}
.tt-abs{{font-family:var(--sans);font-size:10.5px;color:var(--text-mid);line-height:1.55;border-top:1px solid rgba(99,162,255,.1);padding-top:8px;margin-top:6px;}}
.tt-hint{{font-family:var(--mono);font-size:8.5px;color:var(--path-c);margin-top:8px;}}
/* detail panel */
#dp{{
  position:absolute;right:16px;top:60px;width:280px;
  background:rgba(7,18,36,.98);border:1px solid rgba(99,162,255,.24);border-radius:12px;
  padding:18px;display:none;z-index:80;backdrop-filter:blur(18px);
  box-shadow:0 14px 48px rgba(0,0,0,.65);animation:dp-in .2s ease;
}}
@keyframes dp-in{{from{{opacity:0;transform:translateX(16px)}}to{{opacity:1;transform:none}}}}
#dp.vis{{display:block;}}
.dp-hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;}}
.dp-ttl{{font-family:var(--sans);font-size:13px;font-weight:700;color:var(--text-hi);line-height:1.4;flex:1;padding-right:10px;}}
.dp-x{{cursor:pointer;color:var(--text-lo);font-size:18px;transition:color .15s;}}
.dp-x:hover{{color:var(--text-hi);}}
.dp-row{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(99,162,255,.07);}}
.dp-k{{font-family:var(--mono);font-size:8.5px;color:var(--text-lo);letter-spacing:1px;text-transform:uppercase;}}
.dp-v{{font-family:var(--mono);font-size:11px;color:var(--accent);font-weight:600;}}
.dp-abs{{font-family:var(--sans);font-size:10.5px;color:var(--text-mid);line-height:1.55;margin:12px 0;}}
.dp-btn{{
  display:block;width:100%;padding:9px;text-align:center;
  background:rgba(77,159,255,.07);border:1px solid rgba(77,159,255,.24);
  border-radius:7px;color:var(--accent);cursor:pointer;
  font-family:var(--mono);font-size:9px;letter-spacing:1.5px;
  text-transform:uppercase;text-decoration:none;transition:all .15s;
}}
.dp-btn:hover{{background:rgba(77,159,255,.18);border-color:rgba(77,159,255,.5);}}
.dp-path{{
  display:inline-flex;align-items:center;gap:6px;margin-top:10px;
  padding:4px 10px;border-radius:4px;
  background:rgba(255,122,26,.1);border:1px solid rgba(255,122,26,.3);
  color:var(--path-c);font-family:var(--mono);font-size:9px;
}}
/* legend */
#leg{{position:absolute;bottom:10px;left:18px;display:flex;align-items:center;gap:18px;z-index:20;pointer-events:none;}}
.li{{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:9px;color:var(--text-lo);}}
.ld{{width:10px;height:10px;border-radius:2px;flex-shrink:0;}}
.lh{{font-family:var(--mono);font-size:8px;color:#1e3450;margin-left:10px;}}
</style>
</head>
<body>
<div id="rw">
<div id="ctrl">
  <span class="c-lbl">Research Roadmap ◈</span>
  <div class="c-sep"></div>
  <button class="c-btn on"  id="btn-path"  onclick="togglePath()">  <span class="c-dot"></span>READING PATH</button>
  <button class="c-btn"     id="btn-venue" onclick="toggleVenue()"> <span class="c-dot"></span>VENUE CLUSTER</button>
  <button class="c-btn"     id="btn-edge"  onclick="toggleEdge()">  <span class="c-dot"></span>CONNECTIONS</button>
  <div class="c-sep"></div>
  <div id="yr-grp">
    <span class="c-lbl">SPAN</span>
    <span class="yr-v" id="yr-a">—</span>
    <input type="range" id="sl-min" oninput="onYear()">
    <input type="range" id="sl-max" oninput="onYear()">
    <span class="yr-v" id="yr-b">—</span>
  </div>
</div>
<div id="vp">
  <div id="world">
    <svg id="bg-svg" xmlns="http://www.w3.org/2000/svg">
      <g id="g-bands"></g><g id="g-axis"></g>
      <g id="g-edges"></g><g id="g-path"></g>
    </svg>
    <div id="cl"></div>
  </div>
</div>
<div id="zm">
  <div class="zb" onclick="zoomStep(1.18)" title="Zoom In">+</div>
  <div id="zm-pct">100%</div>
  <div class="zb" onclick="zoomStep(0.85)" title="Zoom Out">−</div>
  <div class="zb sm" onclick="fitView()" title="Fit View">FIT</div>
</div>
<div id="tt"></div>
<div id="dp">
  <div class="dp-hdr">
    <div class="dp-ttl" id="dp-ttl">—</div>
    <span class="dp-x" onclick="closePanel()">✕</span>
  </div>
  <div id="dp-rows"></div>
  <div class="dp-abs" id="dp-abs"></div>
  <a class="dp-btn" id="dp-link" href="#" target="_blank">↗ BUKA PAPER LENGKAP</a>
  <div id="dp-path"></div>
</div>
<div id="leg">
  <span class="li"><span class="ld" style="background:#b39dfa"></span>PIONEER &gt;100</span>
  <span class="li"><span class="ld" style="background:#1ee8d6"></span>ESTABLISHED 20–100</span>
  <span class="li"><span class="ld" style="background:#60b0ff"></span>EMERGING &lt;20</span>
  <span class="li"><span class="ld" style="background:#ff7a1a;border-radius:50%"></span>JALUR BACA</span>
  <span class="lh">← Drag=pan · Scroll=zoom</span>
</div>
</div>
<script>
const D = {data_json};

/* Layout constants — CARD_W/H besar agar terbaca */
const CARD_W=220, CARD_H=118;
const YEAR_STEP=260, GAP_H=20, GAP_V=14;
const LEFT_PAD=80, RIGHT_PAD=100, TOP_PAD=52, AXIS_H=56;
const BAND_H = CARD_H*2 + GAP_V*3 + 24;
const YEAR_MIN=D.year_range[0], YEAR_MAX=D.year_range[1];
const V_W = LEFT_PAD + (YEAR_MAX-YEAR_MIN)*YEAR_STEP + RIGHT_PAD;
const V_H = TOP_PAD + 3*BAND_H + AXIS_H + 16;

const TIER_CLR = {{pioneer:'#b39dfa',established:'#1ee8d6',emerging:'#60b0ff'}};
const TIER_NM  = {{pioneer:'PIONEER',established:'ESTABLISHED',emerging:'EMERGING'}};
const VPALE = ['#f472b6','#fb923c','#facc15','#4ade80','#34d399','#818cf8','#c084fc','#f87171','#a3e635','#38bdf8'];
const VM={{}};
D.venues.forEach((v,i)=>VM[v]=VPALE[i%VPALE.length]);

const S={{path:true,venue:false,edges:false,focus:null,yMin:YEAR_MIN,yMax:YEAR_MAX}};
const Z={{s:1,tx:0,ty:0,ox:0,oy:0,px:0,py:0,down:false}};

function vpW(){{return document.getElementById('vp').clientWidth;}}
function vpH(){{return document.getElementById('vp').clientHeight;}}
function minS(){{return Math.max(vpW()/V_W, vpH()/V_H)*0.98;}}
function clampS(s){{return Math.max(minS(),Math.min(3,s));}}
function clampXY(s,tx,ty){{
  return {{
    tx:Math.min(0,Math.max(vpW()-V_W*s,tx)),
    ty:Math.min(0,Math.max(vpH()-V_H*s,ty))
  }};
}}
function applyZ(){{
  const {{tx,ty}}=clampXY(Z.s,Z.tx,Z.ty);
  Z.tx=tx;Z.ty=ty;
  document.getElementById('world').style.transform=`translate(${{tx}}px,${{ty}}px) scale(${{Z.s}})`;
  document.getElementById('zm-pct').textContent=Math.round(Z.s*100)+'%';
}}
function zoomAt(f,cx,cy){{
  const ns=clampS(Z.s*f), r=ns/Z.s;
  Z.tx=cx-(cx-Z.tx)*r; Z.ty=cy-(cy-Z.ty)*r; Z.s=ns; applyZ();
}}
function zoomStep(f){{
  const r=document.getElementById('vp').getBoundingClientRect();
  zoomAt(f,r.width/2,r.height/2);
}}
function fitView(){{
  Z.s=clampS(Math.min(vpW()/V_W,vpH()/V_H)*0.96);
  Z.tx=(vpW()-V_W*Z.s)/2; Z.ty=(vpH()-V_H*Z.s)/2; applyZ();
}}
function initZoom(){{
  /* Start at scale where cards fill the height and are readable */
  Z.s=clampS(Math.max(0.72, vpH()/V_H*0.97));
  Z.tx=0; Z.ty=(vpH()-V_H*Z.s)/2;
  const {{tx,ty}}=clampXY(Z.s,Z.tx,Z.ty);
  Z.tx=tx;Z.ty=ty;applyZ();
}}

document.getElementById('vp').addEventListener('wheel',e=>{{
  e.preventDefault();
  const r=document.getElementById('vp').getBoundingClientRect();
  zoomAt(e.deltaY<0?1.1:0.91,e.clientX-r.left,e.clientY-r.top);
}},{{passive:false}});

const vpEl=document.getElementById('vp');
vpEl.addEventListener('mousedown',e=>{{
  if(e.button!==0)return;
  Z.down=true;Z.px=e.clientX;Z.py=e.clientY;Z.ox=Z.tx;Z.oy=Z.ty;
  vpEl.classList.add('drag');
}});
window.addEventListener('mousemove',e=>{{
  if(!Z.down)return;
  Z.tx=Z.ox+(e.clientX-Z.px);Z.ty=Z.oy+(e.clientY-Z.py);applyZ();
}});
window.addEventListener('mouseup',()=>{{Z.down=false;vpEl.classList.remove('drag');}});

let _tc=[];
vpEl.addEventListener('touchstart',e=>{{_tc=[...e.touches];}},{{passive:true}});
vpEl.addEventListener('touchmove',e=>{{
  if(e.touches.length===1&&_tc.length>=1){{
    Z.tx+=e.touches[0].clientX-_tc[0].clientX;
    Z.ty+=e.touches[0].clientY-_tc[0].clientY;applyZ();
  }}else if(e.touches.length===2&&_tc.length===2){{
    const d0=Math.hypot(_tc[0].clientX-_tc[1].clientX,_tc[0].clientY-_tc[1].clientY);
    const d1=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);
    if(d0>0)zoomAt(d1/d0,vpW()/2,vpH()/2);
  }}
  _tc=[...e.touches];
}},{{passive:true}});

function ns(t,a={{}}){{
  const el=document.createElementNS('http://www.w3.org/2000/svg',t);
  Object.entries(a).forEach(([k,v])=>el.setAttribute(k,v));return el;
}}
function esc(s){{
  return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}
function xOf(y){{return LEFT_PAD+(y-YEAR_MIN)*YEAR_STEP;}}
function bTop(t){{return TOP_PAD+{{pioneer:0,established:1,emerging:2}}[t]*BAND_H;}}
function bMid(t){{return bTop(t)+BAND_H/2;}}
function visSet(){{return new Set(D.nodes.filter(n=>n.year>=S.yMin&&n.year<=S.yMax).map(n=>n.id));}}

function doLayout(nodes){{
  const mpc=Math.max(1,Math.floor((BAND_H-30)/(CARD_H+GAP_V)));
  const pos={{}};
  ['pioneer','established','emerging'].forEach(tier=>{{
    const grp=nodes.filter(n=>n.tier===tier);
    if(!grp.length)return;
    grp.sort((a,b)=>a.year!==b.year?a.year-b.year:b.citations-a.citations);
    const by={{}};
    grp.forEach(n=>(by[n.year]=by[n.year]||[]).push(n));
    const years=Object.keys(by).map(Number).sort((a,b)=>a-b);
    let prevR=-Infinity;
    years.forEach(yr=>{{
      const g=by[yr];
      const nc=Math.ceil(g.length/mpc);
      const gW=nc*CARD_W+(nc-1)*GAP_H;
      const startX=Math.max(xOf(yr)-gW/2, prevR+GAP_H);
      const bm=bMid(tier);
      g.forEach((n,i)=>{{
        const col=Math.floor(i/mpc),row=i%mpc;
        const cs=Math.min(mpc,g.length-col*mpc);
        const ch=cs*CARD_H+(cs-1)*GAP_V;
        const cx=startX+col*(CARD_W+GAP_H)+CARD_W/2;
        const cy=bm-ch/2+row*(CARD_H+GAP_V)+CARD_H/2;
        pos[n.id]={{left:cx-CARD_W/2,top:cy-CARD_H/2,cx,cy}};
      }});
      prevR=startX+gW;
    }});
  }});
  return pos;
}}

function drawBands(){{
  const g=document.getElementById('g-bands');g.innerHTML='';
  const fa={{pioneer:'rgba(179,157,250,.028)',established:'rgba(30,232,214,.022)',emerging:'rgba(96,176,255,.018)'}};
  ['pioneer','established','emerging'].forEach((t,i)=>{{
    const ty=bTop(t);
    g.appendChild(ns('rect',{{x:0,y:ty,width:V_W,height:BAND_H,fill:fa[t]}}));
    if(i>0)g.appendChild(ns('line',{{x1:0,y1:ty,x2:V_W,y2:ty,stroke:'rgba(99,162,255,.06)','stroke-dasharray':'5 12'}}));
    const lb=ns('text',{{x:14,y:ty+14,class:'tier-lbl',fill:TIER_CLR[t],opacity:'.5'}});
    lb.textContent=TIER_NM[t];g.appendChild(lb);
  }});
  for(let y=YEAR_MIN+1;y<=YEAR_MAX-1;y++){{
    const x=xOf(y);
    g.appendChild(ns('line',{{x1:x,y1:TOP_PAD,x2:x,y2:V_H-AXIS_H,stroke:'rgba(99,162,255,.04)'}}));
  }}
}}

function drawAxis(){{
  const g=document.getElementById('g-axis');g.innerHTML='';
  const ay=V_H-AXIS_H;
  g.appendChild(ns('line',{{x1:LEFT_PAD/2,y1:ay,x2:V_W-RIGHT_PAD/2,y2:ay,stroke:'rgba(99,162,255,.16)'}}));
  for(let y=YEAR_MIN+1;y<=YEAR_MAX-1;y++){{
    const x=xOf(y);
    g.appendChild(ns('line',{{x1:x,y1:ay,x2:x,y2:ay+6,stroke:'rgba(99,162,255,.22)'}}));
    const t=ns('text',{{x,y:ay+20,class:'yr-tick'}});t.textContent=y;g.appendChild(t);
  }}
}}

function drawEdges(pos){{
  const g=document.getElementById('g-edges');g.innerHTML='';
  if(!S.edges)return;
  const vis=visSet();
  D.edges.forEach(e=>{{
    if(!vis.has(e.source)||!vis.has(e.target))return;
    const a=pos[e.source],b=pos[e.target];if(!a||!b)return;
    const mx=(a.cx+b.cx)/2;
    const p=ns('path',{{d:`M${{a.cx}},${{a.cy}} C${{mx}},${{a.cy}} ${{mx}},${{b.cy}} ${{b.cx}},${{b.cy}}`,class:'cedge','stroke-width':Math.max(.6,e.weight*2.2)}});
    if(S.focus&&e.source!==S.focus&&e.target!==S.focus)p.classList.add('dim');
    g.appendChild(p);
  }});
}}

function drawPath(pos){{
  const g=document.getElementById('g-path');g.innerHTML='';
  if(!S.path)return;
  const vis=visSet();
  const ids=D.reading_path.filter(id=>vis.has(id));
  const pts=ids.map(id=>pos[id]).filter(Boolean);
  if(pts.length<2)return;
  const bot=p=>p.cy+CARD_H/2+10;
  let d=`M${{pts[0].cx}},${{bot(pts[0])}}`;
  for(let i=1;i<pts.length;i++){{
    const a=pts[i-1],b=pts[i];const mx=(a.cx+b.cx)/2;
    d+=` C${{mx}},${{bot(a)}} ${{mx}},${{bot(b)}} ${{b.cx}},${{bot(b)}}`;
  }}
  g.appendChild(ns('path',{{d,class:'rpath'}}));
  ids.forEach((id,i)=>{{
    const p=pos[id];if(!p)return;
    const cy=bot(p);
    g.appendChild(ns('circle',{{cx:p.cx,cy,r:11,class:'pb-c'}}));
    const t=ns('text',{{x:p.cx,y:cy,class:'pb-t'}});t.textContent=i+1;g.appendChild(t);
  }});
}}

function drawCards(pos){{
  const layer=document.getElementById('cl');layer.innerHTML='';
  const vis=visSet();
  D.nodes.filter(n=>vis.has(n.id)).forEach(n=>{{
    const p=pos[n.id];if(!p)return;
    const tc=TIER_CLR[n.tier];
    const cc=S.venue?(VM[n.venue]||tc):tc;
    const iF=S.focus===n.id;
    const iD=S.focus&&!iF;
    const au=(n.authors||'').split(',').slice(0,2).join(', ')+((n.authors||'').split(',').length>2?' et al.':'');
    const div=document.createElement('div');
    div.className=`card ${{n.tier}}${{S.venue?' vc':''}}${{iF?' focused':''}}${{iD?' dim':''}}`;
    div.dataset.id=n.id;
    div.style.left=p.left+'px';div.style.top=p.top+'px';
    if(S.venue)div.style.setProperty('--vc',cc);
    div.innerHTML=`
      <div class="c-chip">${{n.year}}</div>
      <div class="c-title">${{esc(n.title)}}</div>
      <div class="c-authors">${{esc(au)}}</div>
      <div class="c-foot">
        <span class="c-cite">↑ ${{n.citations.toLocaleString()}}</span>
        <span class="c-src">${{esc(n.source)}}</span>
      </div>`;
    div.addEventListener('mouseenter',ev=>showTip(ev,n,cc));
    div.addEventListener('mouseleave',()=>hideTip());
    div.addEventListener('click',ev=>{{ev.stopPropagation();openPanel(n);}});
    layer.appendChild(div);
  }});
}}

function showTip(ev,n,color){{
  const pi=D.reading_path.indexOf(n.id);
  const tt=document.getElementById('tt');
  tt.innerHTML=`
    <div class="tt-t">${{esc(n.title)}}</div>
    <div class="tt-m">👤 ${{esc((n.authors||'').split(',').slice(0,2).join(', '))}}</div>
    <div class="tt-m">📅 ${{n.year}} · ↑ ${{n.citations.toLocaleString()}} sitasi</div>
    <div class="tt-m">🏛 ${{esc(n.venue)}}</div>
    <span class="tt-badge ${{n.tier}}">${{TIER_NM[n.tier]}}</span>
    <div class="tt-abs">${{esc(n.abstract)}}</div>
    ${{pi>=0?`<div class="tt-hint">📍 Urutan Baca #${{pi+1}} dari ${{D.reading_path.length}}</div>`:''}}
    <div class="tt-hint" style="color:var(--accent);margin-top:5px">🖱 Klik untuk detail lengkap</div>
  `;
  const W=window.innerWidth,H=window.innerHeight;
  const lx=ev.clientX+18,ly=ev.clientY-12;
  tt.style.cssText=`display:block;left:${{lx+330>W?ev.clientX-340:lx}}px;top:${{ly+340>H?ev.clientY-350:ly}}px`;
}}
function hideTip(){{document.getElementById('tt').style.display='none';}}

function openPanel(n){{
  S.focus=n.id;
  const pi=D.reading_path.indexOf(n.id);
  document.getElementById('dp-ttl').textContent=n.title;
  document.getElementById('dp-abs').textContent=n.abstract;
  document.getElementById('dp-link').href=n.link||'#';
  document.getElementById('dp-rows').innerHTML=`
    <div class="dp-row"><span class="dp-k">TAHUN</span><span class="dp-v">${{n.year}}</span></div>
    <div class="dp-row"><span class="dp-k">SITASI</span><span class="dp-v">${{n.citations.toLocaleString()}}</span></div>
    <div class="dp-row"><span class="dp-k">TIER</span><span class="dp-v" style="color:${{TIER_CLR[n.tier]}}">${{TIER_NM[n.tier]}}</span></div>
    <div class="dp-row"><span class="dp-k">PENULIS</span><span class="dp-v" style="font-size:9px;max-width:160px;text-align:right;line-height:1.3">${{esc((n.authors||'').substring(0,60))}}</span></div>
    <div class="dp-row"><span class="dp-k">VENUE</span><span class="dp-v" style="font-size:9px;max-width:160px;text-align:right;line-height:1.3">${{esc(n.venue.substring(0,40))}}</span></div>
  `;
  document.getElementById('dp-path').innerHTML=pi>=0
    ?`<div class="dp-path">📍 Urutan Baca #${{pi+1}} dari ${{D.reading_path.length}}</div>`:'';
  document.getElementById('dp').classList.add('vis');
  renderAll();
}}
function closePanel(){{
  S.focus=null;
  document.getElementById('dp').classList.remove('vis');
  renderAll();
}}

function togglePath(){{S.path=!S.path;document.getElementById('btn-path').className='c-btn'+(S.path?' on':'');renderAll();}}
function toggleVenue(){{S.venue=!S.venue;document.getElementById('btn-venue').className='c-btn'+(S.venue?' on-t':'');renderAll();}}
function toggleEdge(){{S.edges=!S.edges;document.getElementById('btn-edge').className='c-btn'+(S.edges?' on-b':'');renderAll();}}
function onYear(){{
  let a=+document.getElementById('sl-min').value;
  let b=+document.getElementById('sl-max').value;
  if(a>b){{a=b;document.getElementById('sl-min').value=a;}}
  S.yMin=a;S.yMax=b;
  document.getElementById('yr-a').textContent=a;
  document.getElementById('yr-b').textContent=b;
  renderAll();
}}

function renderAll(){{
  const vis=visSet();
  const nodes=D.nodes.filter(n=>vis.has(n.id));
  const pos=doLayout(nodes);
  drawBands();drawAxis();drawEdges(pos);drawPath(pos);drawCards(pos);
}}

function init(){{
  const world=document.getElementById('world');
  world.style.width=V_W+'px';world.style.height=V_H+'px';
  const svg=document.getElementById('bg-svg');
  svg.style.width=V_W+'px';svg.style.height=V_H+'px';
  svg.setAttribute('viewBox',`0 0 ${{V_W}} ${{V_H}}`);
  document.getElementById('cl').style.width=V_W+'px';
  document.getElementById('cl').style.height=V_H+'px';
  ['sl-min','sl-max'].forEach(id=>{{
    const sl=document.getElementById(id);
    sl.min=YEAR_MIN;sl.max=YEAR_MAX;
    sl.value=id==='sl-min'?YEAR_MIN:YEAR_MAX;
  }});
  document.getElementById('yr-a').textContent=YEAR_MIN;
  document.getElementById('yr-b').textContent=YEAR_MAX;
  renderAll();
  initZoom();
  document.getElementById('vp').addEventListener('click',e=>{{
    if(!e.target.closest('.card')&&!e.target.closest('#dp'))closePanel();
  }});
  let rt;
  window.addEventListener('resize',()=>{{clearTimeout(rt);rt=setTimeout(()=>{{renderAll();applyZ();}},120);}});
}}

document.readyState==='loading'
  ?document.addEventListener('DOMContentLoaded',init)
  :setTimeout(init,60);
</script>
</body>
</html>"""
