"""
graph_influence.py  —  v3 UPGRADED
====================================
Influence Map — Research Intelligence Center

PERUBAHAN v3 vs v2:
  ✅ Zoom + Pan native (SVG viewBox transform — scroll wheel + drag)
  ✅ Staggered Orbit  — ring otomatis dipecah jadi 2 jalur jika node > 12
  ✅ Smart Label      — label muncul progresif berdasarkan zoom level
  ✅ Click-to-Focus   — klik node → semua lain fade, tetangga tetap terang
  ✅ Label backdrop   — background gelap di belakang teks agar selalu terbaca
  ✅ Konsep orbital TIDAK berubah — pusat, ring 1/2/3, warna, partikel, panel tetap sama

Fungsi publik (interface tidak berubah):
  render_influence(papers, height)   → str  HTML siap embed di Streamlit
  influence_stats(papers, center_id) → dict statistik untuk metric cards
  build_influence_data(papers)       → dict data mentah
"""

from __future__ import annotations

import math
import json
import streamlit as st
from data_layer import _raw_get

_R3_MIN_CITATIONS: int = 30
_STAGGER_THRESHOLD: int = 12   # node per ring sebelum dipecah jadi 2 orbit


# ─────────────────────────────────────────────────────────────────
# 1. FETCH CITATION NETWORK
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_influence_refs(paper_id: str) -> dict:
    if not paper_id or paper_id.startswith("p"):
        return {"references": [], "citations": []}
    url    = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    params = {
        "fields": (
            "references.paperId,references.title,references.year,"
            "references.citationCount,"
            "citations.paperId,citations.title,citations.year,"
            "citations.citationCount"
        )
    }
    try:
        data = _raw_get(url, params)
        return {
            "references": data.get("references", []),
            "citations":  data.get("citations",  [])
        }
    except Exception as exc:
        import sys
        print(f"[graph_influence] fetch error {paper_id}: {exc}", file=sys.stderr)
        return {"references": [], "citations": []}


def _extract_pid(paper: dict) -> str:
    link = paper.get("link", "")
    if "semanticscholar.org/paper/" in link:
        return link.split("/paper/")[-1].strip("/")
    return ""


# ─────────────────────────────────────────────────────────────────
# 2. DATA PROCESSING  (sama persis dengan v2)
# ─────────────────────────────────────────────────────────────────

def _safe_int(val, default: int = 0) -> int:
    if val is None or val == "":
        return default
    try:
        return max(0, int(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return default


def _safe_authors(val) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, (list, tuple)):
        val = ", ".join(str(v).strip() for v in val if v)
    return str(val).strip() or "N/A"


def _normalize_paper(p: dict, idx: int) -> dict:
    pid = _extract_pid(p) or f"p{idx}_{p.get('title','x')[:20].replace(' ','_')}"
    title    = (p.get("title",    "") or "Untitled").strip()
    abstract = (p.get("abstract", "") or "Abstrak tidak tersedia.").strip()
    try:
        year = int(str(p.get("year","")).strip())
        if not (1900 < year <= 2030): year = 2020
    except (ValueError, TypeError):
        year = 2020
    citations = _safe_int(p.get("citations", 0))
    return {
        "id":          pid,
        "title":       title,
        "title_short": (title[:55] + "…") if len(title) > 55 else title,
        "authors":     _safe_authors(p.get("authors")),
        "year":        year,
        "citations":   citations,
        "venue":       (p.get("venue", "") or "Unknown Venue").strip() or "Unknown Venue",
        "abstract":    (abstract[:240] + "…") if len(abstract) > 240 else abstract,
        "link":        p.get("link", ""),
        "source":      p.get("source", "unknown"),
        "is_main":     True,
    }


def _build_one_config(center_id, papers_map, refs_cache):
    center    = papers_map[center_id]
    refs_data = refs_cache.get(center_id, {"references": [], "citations": []})
    ref_ids   = {r.get("paperId") for r in refs_data.get("references", []) if r.get("paperId")}
    cite_ids  = {c.get("paperId") for c in refs_data.get("citations",  []) if c.get("paperId")}

    ring1, ring2, ring3_extra = [], [], []
    for pid, p in papers_map.items():
        if pid == center_id: continue
        if pid in ref_ids:        ring1.append(pid)
        elif pid in cite_ids:     ring2.append(pid)
        elif p["year"] < center["year"]: ring1.append(pid)
        elif p["year"] > center["year"]: ring2.append(pid)
        elif p["citations"] >= center["citations"]: ring1.append(pid)
        else: ring2.append(pid)

    seen_pids = set(papers_map.keys()) | {center_id}
    api_nodes = refs_data.get("references", []) + refs_data.get("citations", [])
    added_r3  = set()
    for node in sorted(api_nodes, key=lambda x: x.get("citationCount", 0), reverse=True)[:8]:
        nid  = node.get("paperId", "")
        ntit = (node.get("title", "") or "").strip()
        if nid and nid not in seen_pids and nid not in added_r3 and ntit:
            nc = node.get("citationCount", 0) or 0
            if nc > _R3_MIN_CITATIONS:
                ring3_extra.append({
                    "id": nid, "title": ntit,
                    "title_short": (ntit[:45]+"…") if len(ntit)>45 else ntit,
                    "authors": "—", "year": node.get("year","?") or "?",
                    "citations": nc, "venue": "External",
                    "abstract": "Paper tetangga dari jaringan sitasi.",
                    "link": f"https://www.semanticscholar.org/paper/{nid}",
                    "source": "neighbor", "is_main": False,
                })
                added_r3.add(nid)
                if len(added_r3) >= 6: break

    edges = []
    for pid in ring1:
        w = math.log(papers_map[pid]["citations"] + 1) / 3
        edges.append({"src": pid, "dst": center_id, "type": "r1", "weight": round(max(0.5, w), 3)})
    for pid in ring2:
        w = math.log(papers_map[pid]["citations"] + 1) / 3
        edges.append({"src": center_id, "dst": pid, "type": "r2", "weight": round(max(0.5, w), 3)})
    for nd in ring3_extra:
        nid = nd["id"]
        w   = math.log(nd["citations"] + 1) / 5
        yr  = nd["year"] if isinstance(nd["year"], int) else 0
        if yr and yr < center["year"]:
            edges.append({"src": nid, "dst": center_id, "type": "r3", "weight": round(max(0.3, w), 3)})
        else:
            edges.append({"src": center_id, "dst": nid, "type": "r3", "weight": round(max(0.3, w), 3)})

    avg_r1_cite = sum(papers_map[i]["citations"] for i in ring1) / len(ring1) if ring1 else 0
    return {
        "ring1": ring1, "ring2": ring2, "ring3_extra": ring3_extra, "edges": edges,
        "stats": {
            "ancestors": len(ring1), "descendants": len(ring2),
            "extra_neighbors": len(ring3_extra),
            "avg_r1_citations": round(avg_r1_cite),
            "center_citations": center["citations"],
            "center_year": center["year"],
        }
    }


@st.cache_data(ttl=3600, show_spinner=False)
def build_influence_data(papers: list[dict]) -> dict:
    if not papers:
        return {"papers": [], "configs": {}, "default_center": "", "year_range": [2015, 2025]}

    norm_papers = [_normalize_paper(p, i) for i, p in enumerate(papers)]
    papers_map: dict = {}
    for p in norm_papers:
        pid = p["id"]
        if pid in papers_map:
            p = dict(p)
            p["id"] = f"{pid}_dup{sum(1 for k in papers_map if k.startswith(pid))}"
        papers_map[p["id"]] = p

    refs_cache = {p["id"]: fetch_influence_refs(p["id"]) for p in norm_papers}
    configs    = {pid: _build_one_config(pid, papers_map, refs_cache) for pid in papers_map}
    default_center = max(papers_map, key=lambda k: papers_map[k]["citations"])
    years = [p["year"] for p in norm_papers]
    return {
        "papers": norm_papers, "configs": configs,
        "default_center": default_center,
        "year_range": [min(years, default=2015), max(years, default=2025)],
    }


# ─────────────────────────────────────────────────────────────────
# 3. STATISTIK
# ─────────────────────────────────────────────────────────────────

def influence_stats(papers: list[dict], center_id: str = None) -> dict:
    if not papers: return {}
    data = build_influence_data(papers)
    if not data["papers"]: return {}
    cid  = center_id or data["default_center"]
    pmap = {p["id"]: p for p in data["papers"]}
    cfg  = data["configs"].get(cid, {})
    center = pmap.get(cid, {})
    r3_ex  = cfg.get("ring3_extra", [])
    return {
        "total_papers":     len(data["papers"]),
        "total_nodes":      len(data["papers"]) + len(r3_ex),
        "center_title":     center.get("title_short", "-"),
        "center_citations": center.get("citations", 0),
        "ancestor_count":   cfg.get("stats", {}).get("ancestors",   0),
        "descendant_count": cfg.get("stats", {}).get("descendants", 0),
        "neighbor_count":   cfg.get("stats", {}).get("extra_neighbors", 0),
        "influence_reach":  (
            cfg.get("stats", {}).get("ancestors",       0) +
            cfg.get("stats", {}).get("descendants",     0) +
            cfg.get("stats", {}).get("extra_neighbors", 0)
        ),
    }


# ─────────────────────────────────────────────────────────────────
# 4. RENDER HTML  —  v3 UPGRADED
# ─────────────────────────────────────────────────────────────────

def render_influence(papers: list[dict], height: int = 700) -> str:
    data      = build_influence_data(papers)
    _raw_json = json.dumps(data, ensure_ascii=False).replace('\x3c/', r'\<\/')
    data_json = json.dumps(_raw_json)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Influence Map v3</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syncopate:wght@400;700&family=JetBrains+Mono:wght@300;400;500;600&family=Sora:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;overflow:hidden;
  background:#030a14;color:#c8d8f0;
  font-family:'Sora',sans-serif;user-select:none;
}}
:root{{
  --bg:         #030a14;
  --panel-bg:   rgba(4,12,28,0.97);
  --border:     rgba(56,189,248,0.13);
  --border-hi:  rgba(56,189,248,0.40);
  --center-c:   #fbbf24;
  --r1-c:       #38bdf8;
  --r2-c:       #34d399;
  --r3-c:       #94a3b8;
  --text-hi:    #e8f4ff;
  --text-mid:   #7aa8cc;
  --text-lo:    #2d4a6a;
  --font-disp:  'Syncopate',sans-serif;
  --font-mono:  'JetBrains Mono',monospace;
  --font-body:  'Sora',sans-serif;
}}

/* ── Root ── */
#iw{{
  width:100%;height:{height}px;
  position:relative;overflow:hidden;
  background:radial-gradient(ellipse 90% 80% at 50% 50%,
    rgba(12,25,60,0.55) 0%, rgba(3,10,20,1) 70%);
}}
#nebula{{
  position:absolute;pointer-events:none;border-radius:50%;
  transition:left .7s cubic-bezier(.4,0,.2,1),top .7s cubic-bezier(.4,0,.2,1);
  z-index:0;
}}
/* scanline */
#iw::after{{
  content:'';position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(0deg,transparent,transparent 2px,
    rgba(0,10,35,.05) 2px,rgba(0,10,35,.05) 3px);
}}

/* ── Control bar ── */
#ctrl{{
  position:absolute;top:0;left:0;right:0;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding:7px 12px;z-index:30;
  background:linear-gradient(180deg,rgba(3,10,20,.97) 60%,transparent);
  border-bottom:1px solid rgba(56,189,248,.06);
}}
.c-logo{{
  font-family:var(--font-disp);font-size:7px;letter-spacing:3.5px;
  color:rgba(56,189,248,.35);text-transform:uppercase;white-space:nowrap;
}}
.c-sep{{width:1px;height:18px;background:var(--border);flex-shrink:0;}}
.c-btn{{
  display:flex;align-items:center;gap:4px;cursor:pointer;
  padding:3px 9px;border-radius:3px;
  border:1px solid var(--border);background:transparent;
  font-family:var(--font-mono);font-size:8.5px;letter-spacing:.6px;
  color:var(--text-mid);transition:all .15s;
}}
.c-btn:hover{{border-color:var(--border-hi);color:var(--text-hi);}}
.c-btn.on-amber{{border-color:rgba(251,191,36,.5);color:#fbbf24;background:rgba(251,191,36,.06);}}
.c-btn.on-sky  {{border-color:rgba(56,189,248,.5);color:#38bdf8;background:rgba(56,189,248,.06);}}
.c-btn.on-green{{border-color:rgba(52,211,153,.5);color:#34d399;background:rgba(52,211,153,.06);}}
.c-dot{{width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0;}}

/* zoom indicator */
#zoom-ind{{
  font-family:var(--font-mono);font-size:8px;
  color:rgba(56,189,248,.4);letter-spacing:.5px;
  padding:3px 8px;border:1px solid rgba(56,189,248,.1);border-radius:3px;
}}

/* paper selector */
#sel-wrap{{margin-left:auto;display:flex;align-items:center;gap:6px;}}
.c-lbl{{font-family:var(--font-mono);font-size:7.5px;color:var(--text-lo);white-space:nowrap;}}
#paper-sel{{
  background:rgba(4,12,28,.95);border:1px solid var(--border);
  border-radius:4px;color:#38bdf8;padding:3px 22px 3px 8px;
  font-family:var(--font-mono);font-size:8.5px;cursor:pointer;
  appearance:none;outline:none;max-width:200px;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='9' height='5'%3E%3Cpath d='M0 0l4.5 5 4.5-5z' fill='%2338bdf8'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 7px center;
  transition:border-color .15s;
}}
#paper-sel:hover{{border-color:var(--border-hi);}}
#paper-sel option{{background:#040c1c;}}

/* ── Zoom hint (shown only at start) ── */
#zoom-hint{{
  position:absolute;bottom:52px;left:50%;transform:translateX(-50%);
  font-family:var(--font-mono);font-size:9px;letter-spacing:.8px;
  color:rgba(56,189,248,.35);pointer-events:none;z-index:20;
  animation:hint-fade 4s ease forwards;
}}
@keyframes hint-fade{{0%{{opacity:1}}70%{{opacity:.6}}100%{{opacity:0}}}}

/* ── SVG + Canvas container ── */
#sc{{position:absolute;inset:0;z-index:2;cursor:grab;}}
#sc.dragging{{cursor:grabbing;}}
#svg{{position:absolute;inset:0;width:100%;height:100%;}}
#cv {{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;}}

/* SVG element classes */
.orbit-ring{{
  fill:none;stroke-dasharray:5 11;
  animation:orbit-spin var(--spd,24s) linear infinite;
  transform-box:fill-box;transform-origin:center;
}}
@keyframes orbit-spin{{to{{stroke-dashoffset:-160}}}}

.edge-line{{
  fill:none;
  transition:opacity .25s,stroke-width .25s;
}}

/* Node groups */
.inode{{cursor:pointer;}}
.inode .n-body{{transition:opacity .25s;}}
.inode .n-label-grp{{transition:opacity .2s;}}

/* Focus/dim states */
.inode.dimmed .n-body{{opacity:.07;}}
.inode.dimmed .n-label-grp{{opacity:0;}}
.edge-line.dimmed{{opacity:.03!important;}}

.n-pulse{{animation:pulse-ring 2.4s ease-out infinite;}}
@keyframes pulse-ring{{
  0%{{transform:scale(1);opacity:.65;}}
  60%{{transform:scale(1.6);opacity:0;}}
  100%{{transform:scale(1.6);opacity:0;}}
}}

/* ── Tooltip ── */
#tt{{
  position:absolute;display:none;pointer-events:none;z-index:100;
  background:rgba(3,9,22,.97);
  border:1px solid rgba(56,189,248,.22);
  border-radius:8px;padding:12px 14px;max-width:270px;min-width:190px;
  box-shadow:0 16px 48px rgba(0,0,0,.85),0 0 24px rgba(56,189,248,.05);
  backdrop-filter:blur(18px);
}}
.tt-title{{font-family:var(--font-body);font-size:10.5px;font-weight:700;
  color:var(--text-hi);margin-bottom:5px;line-height:1.4;}}
.tt-meta{{font-family:var(--font-mono);font-size:7.5px;color:var(--text-mid);
  letter-spacing:.2px;margin-bottom:2px;}}
.tt-ring{{
  display:inline-flex;align-items:center;gap:4px;
  padding:2px 7px;border-radius:2px;margin:5px 0 6px;
  font-family:var(--font-mono);font-size:7px;letter-spacing:1px;
  text-transform:uppercase;border:1px solid currentColor;
}}
.tt-abs{{font-family:var(--font-body);font-size:8.5px;color:var(--text-mid);
  line-height:1.55;border-top:1px solid var(--border);padding-top:5px;margin-top:4px;}}
.tt-hint{{font-family:var(--font-mono);font-size:7px;color:#fbbf24;margin-top:5px;}}

/* ── Detail Panel ── */
#dp{{
  position:absolute;right:12px;top:46px;width:230px;
  background:var(--panel-bg);
  border:1px solid rgba(56,189,248,.18);border-radius:9px;
  padding:14px;z-index:50;display:none;
  box-shadow:0 16px 48px rgba(0,0,0,.7),0 0 0 1px rgba(56,189,248,.05);
  backdrop-filter:blur(20px);
  animation:dp-in .2s ease;
}}
@keyframes dp-in{{from{{opacity:0;transform:translateX(12px)}}to{{opacity:1;transform:none}}}}
#dp.vis{{display:block;}}
.dp-x{{
  position:absolute;top:10px;right:11px;cursor:pointer;
  color:var(--text-lo);font-size:14px;line-height:1;transition:color .15s;
}}
.dp-x:hover{{color:var(--text-hi);}}
.dp-title{{
  font-family:var(--font-body);font-size:10.5px;font-weight:700;
  color:var(--text-hi);line-height:1.4;margin-bottom:10px;padding-right:14px;
}}
.dp-row{{
  display:flex;justify-content:space-between;align-items:center;
  padding:3.5px 0;border-bottom:1px solid rgba(56,189,248,.06);
}}
.dp-k{{font-family:var(--font-mono);font-size:7px;color:var(--text-lo);letter-spacing:.8px;text-transform:uppercase;}}
.dp-v{{font-family:var(--font-mono);font-size:9px;color:#38bdf8;font-weight:500;}}
.dp-abs{{
  font-family:var(--font-body);font-size:8.5px;color:var(--text-mid);
  line-height:1.55;margin:8px 0;
}}
.dp-btn{{
  display:block;width:100%;padding:6px;text-align:center;
  background:rgba(56,189,248,.06);border:1px solid rgba(56,189,248,.2);
  border-radius:4px;color:#38bdf8;cursor:pointer;
  font-family:var(--font-mono);font-size:7.5px;letter-spacing:1.2px;
  text-transform:uppercase;text-decoration:none;transition:all .15s;margin-bottom:5px;
}}
.dp-btn:hover{{background:rgba(56,189,248,.15);}}
.dp-recenter{{
  display:block;width:100%;padding:6px;text-align:center;
  background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.2);
  border-radius:4px;color:#fbbf24;cursor:pointer;
  font-family:var(--font-mono);font-size:7.5px;letter-spacing:1.2px;
  text-transform:uppercase;transition:all .15s;
}}
.dp-recenter:hover{{background:rgba(251,191,36,.15);}}

/* ── Stats panel ── */
#sp{{
  position:absolute;right:12px;bottom:36px;width:162px;
  background:var(--panel-bg);border:1px solid var(--border);
  border-radius:8px;padding:11px;z-index:20;
}}
.sp-hdr{{
  font-family:var(--font-disp);font-size:6.5px;letter-spacing:3px;
  color:var(--text-lo);text-transform:uppercase;margin-bottom:7px;
}}
.sp-row{{display:flex;justify-content:space-between;align-items:center;padding:2.5px 0;}}
.sp-k{{font-family:var(--font-mono);font-size:7px;color:var(--text-lo);}}
.sp-v{{font-family:var(--font-mono);font-size:9.5px;font-weight:500;}}
.sp-bar{{height:2px;background:rgba(56,189,248,.08);border-radius:1px;margin:4px 0;overflow:hidden;}}
.sp-fill{{height:100%;border-radius:1px;transition:width .6s cubic-bezier(.4,0,.2,1);}}

/* ── Mini-map ── */
#minimap{{
  position:absolute;left:12px;bottom:36px;
  width:120px;height:90px;
  background:rgba(4,12,28,.9);border:1px solid rgba(56,189,248,.1);
  border-radius:6px;z-index:20;overflow:hidden;
}}
#mm-svg{{width:100%;height:100%;}}
#mm-viewport{{
  fill:none;stroke:rgba(56,189,248,.35);stroke-width:1;
  pointer-events:none;
}}
.mm-title{{
  position:absolute;top:3px;left:5px;
  font-family:var(--font-mono);font-size:6px;letter-spacing:1.5px;
  color:rgba(56,189,248,.3);text-transform:uppercase;
}}

/* ── Legend ── */
#leg{{
  position:absolute;bottom:14px;left:140px;
  display:flex;align-items:center;gap:12px;z-index:20;
}}
.leg-i{{display:flex;align-items:center;gap:4px;
  font-family:var(--font-mono);font-size:7.5px;color:var(--text-lo);}}
.leg-d{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}

/* ── Reset Focus btn (shown when in focus mode) ── */
#btn-reset-focus{{
  position:absolute;top:46px;left:12px;
  display:none;z-index:30;
  background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.35);
  border-radius:4px;padding:5px 10px;
  font-family:var(--font-mono);font-size:8px;letter-spacing:.8px;
  color:#fbbf24;cursor:pointer;transition:all .15s;
}}
#btn-reset-focus.vis{{display:block;}}
#btn-reset-focus:hover{{background:rgba(251,191,36,.2);}}
</style>
</head>
<body>
<div id="iw">
  <div id="nebula"></div>

  <!-- Control bar -->
  <div id="ctrl">
    <span class="c-logo">Influence Map ◈ v3</span>
    <div class="c-sep"></div>
    <button class="c-btn on-amber" id="btn-part"  onclick="toggleParticles()"><span class="c-dot"></span>PARTICLES</button>
    <button class="c-btn on-sky"   id="btn-orb"   onclick="toggleOrbits()">  <span class="c-dot"></span>ORBITS</button>
    <button class="c-btn"          id="btn-heat"  onclick="toggleHeatmap()"> <span class="c-dot"></span>HEATMAP</button>
    <div class="c-sep"></div>
    <span id="zoom-ind">ZOOM 100%</span>
    <button class="c-btn" onclick="resetZoom()" title="Reset zoom">⌂ RESET</button>
    <div id="sel-wrap">
      <span class="c-lbl">PUSAT:</span>
      <select id="paper-sel" onchange="onSelectCenter(this.value)"></select>
    </div>
  </div>

  <!-- Reset Focus button -->
  <button id="btn-reset-focus" onclick="clearFocusMode()">✕ CLEAR FOCUS</button>

  <!-- Main SVG + Canvas -->
  <div id="sc">
    <svg id="svg" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="grad-center" cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stop-color="#fde68a" stop-opacity="1"/>
          <stop offset="55%"  stop-color="#f59e0b" stop-opacity=".75"/>
          <stop offset="100%" stop-color="#d97706" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="grad-r1" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stop-color="#7dd3fc" stop-opacity=".9"/>
          <stop offset="100%" stop-color="#0284c7" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="grad-r2" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stop-color="#6ee7b7" stop-opacity=".9"/>
          <stop offset="100%" stop-color="#059669" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="grad-r3" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stop-color="#cbd5e1" stop-opacity=".7"/>
          <stop offset="100%" stop-color="#64748b" stop-opacity="0"/>
        </radialGradient>
        <filter id="f-center" x="-70%" y="-70%" width="240%" height="240%">
          <feGaussianBlur stdDeviation="8" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="f-node" x="-45%" y="-45%" width="190%" height="190%">
          <feGaussianBlur stdDeviation="4" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="f-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="7"/>
        </filter>
        <filter id="f-txt" x="-5%" y="-20%" width="110%" height="140%">
          <feFlood flood-color="rgba(3,9,22,.82)" result="bg"/>
          <feComposite in="bg" in2="SourceGraphic" operator="in" result="bgclip"/>
          <feMerge><feMergeNode in="bgclip"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <marker id="arr-r1" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
          <path d="M0,0 L0,7 L7,3.5 z" fill="rgba(56,189,248,0.5)"/>
        </marker>
        <marker id="arr-r2" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
          <path d="M0,0 L0,7 L7,3.5 z" fill="rgba(52,211,153,0.5)"/>
        </marker>
        <marker id="arr-r3" markerWidth="6" markerHeight="6" refX="4" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="rgba(148,163,184,0.32)"/>
        </marker>
      </defs>
      <rect id="svg-bg" width="100%" height="100%" fill="transparent"/>
      <!-- Zoomable group -->
      <g id="g-zoom">
        <g id="g-orbits"></g>
        <g id="g-edges"></g>
        <g id="g-nodes"></g>
      </g>
    </svg>
    <canvas id="cv"></canvas>
  </div>

  <!-- Tooltip -->
  <div id="tt"></div>

  <!-- Detail Panel -->
  <div id="dp">
    <span class="dp-x" onclick="closePanel()">✕</span>
    <div class="dp-title" id="dp-title">—</div>
    <div id="dp-rows"></div>
    <div class="dp-abs" id="dp-abs">—</div>
    <a class="dp-btn"       id="dp-link"     href="#" target="_blank">↗ BUKA PAPER</a>
    <div class="dp-recenter" id="dp-recenter" onclick="reCenterFromPanel()">⊙ JADIKAN PUSAT</div>
  </div>

  <!-- Stats Panel -->
  <div id="sp">
    <div class="sp-hdr">Network Stats</div>
    <div id="sp-content"></div>
  </div>

  <!-- Mini-map -->
  <div id="minimap">
    <span class="mm-title">OVERVIEW</span>
    <svg id="mm-svg" xmlns="http://www.w3.org/2000/svg">
      <g id="mm-nodes"></g>
      <rect id="mm-viewport" x="5%" y="5%" width="90%" height="90%"/>
    </svg>
  </div>

  <!-- Legend -->
  <div id="leg">
    <span class="leg-i"><span class="leg-d" style="background:#fbbf24;box-shadow:0 0 5px #fbbf24"></span>PUSAT</span>
    <span class="leg-i"><span class="leg-d" style="background:#38bdf8"></span>LELUHUR R1</span>
    <span class="leg-i"><span class="leg-d" style="background:#34d399"></span>PENERUS R2</span>
    <span class="leg-i"><span class="leg-d" style="background:#94a3b8"></span>TETANGGA R3</span>
  </div>

  <!-- Zoom hint -->
  <div id="zoom-hint">🖱 Scroll = Zoom &nbsp;·&nbsp; Drag = Pan &nbsp;·&nbsp; Klik Node = Fokus</div>
</div>

<script>
/* ══════════════════════════════════════
   DATA
══════════════════════════════════════ */
const D = JSON.parse({data_json});

/* ══════════════════════════════════════
   XSS SAFETY
══════════════════════════════════════ */
function esc(s){{
  return String(s==null?'':s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

/* ══════════════════════════════════════
   STATE
══════════════════════════════════════ */
const S = {{
  center:       D.default_center,
  showPart:     true,
  showOrbits:   true,
  heatmap:      false,
  focusNodeId:  null,      // node yang sedang difokuskan
  transitioning:false,

  // Zoom + Pan state
  zoom:  1.0,
  panX:  0,
  panY:  0,
  isDragging: false,
  dragStartX: 0,
  dragStartY: 0,
  dragPanX:   0,
  dragPanY:   0,
}};

const ZOOM_MIN  = 0.3;
const ZOOM_MAX  = 4.0;
const ZOOM_STEP = 0.12;

/* ══════════════════════════════════════
   CONSTANTS
══════════════════════════════════════ */
const RING_CLR   = {{center:'#fbbf24',r1:'#38bdf8',r2:'#34d399',r3:'#94a3b8'}};
const RING_NAMES = {{center:'PUSAT',r1:'LELUHUR',r2:'PENERUS',r3:'TETANGGA'}};
const NODE_BASE  = 14;
const NODE_MAX   = 46;
const STAGGER_TH = {_STAGGER_THRESHOLD};  // node per ring sebelum dipecah

/* ══════════════════════════════════════
   DIMENSIONS
══════════════════════════════════════ */
function W(){{ return document.getElementById('sc').clientWidth  || 800; }}
function H(){{ return document.getElementById('sc').clientHeight || 600; }}

/* ══════════════════════════════════════
   SVG NAMESPACE
══════════════════════════════════════ */
function ns(tag, attrs={{}}){{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k,v));
  return el;
}}

/* ══════════════════════════════════════
   NODE SIZE
══════════════════════════════════════ */
function nodeSize(citations){{
  if(!citations) return NODE_BASE;
  return Math.max(NODE_BASE, Math.min(NODE_MAX, Math.log(citations+1)*5.2));
}}

function heatColor(ring){{
  if(!S.heatmap) return null;
  return {{center:'#ffffff',r1:'#ef4444',r2:'#f97316',r3:'#3b82f6'}}[ring] || '#94a3b8';
}}
function ringColor(ring){{ return heatColor(ring) || RING_CLR[ring] || RING_CLR.r3; }}

/* ══════════════════════════════════════
   ZOOM + PAN
══════════════════════════════════════ */
function applyTransform(){{
  const g = document.getElementById('g-zoom');
  g.setAttribute('transform',`translate(${{S.panX}},${{S.panY}}) scale(${{S.zoom}})`);
  document.getElementById('zoom-ind').textContent = `ZOOM ${{Math.round(S.zoom*100)}}%`;
  // Progressive labels: show/hide based on zoom
  updateLabelVisibility();
  updateMinimap();
}}

function zoomAt(cx, cy, delta){{
  const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, S.zoom + delta));
  if(newZoom === S.zoom) return;
  // Zoom toward cursor point
  const scale = newZoom / S.zoom;
  S.panX = cx - scale * (cx - S.panX);
  S.panY = cy - scale * (cy - S.panY);
  S.zoom = newZoom;
  applyTransform();
}}

function resetZoom(){{
  S.zoom = 1; S.panX = 0; S.panY = 0;
  document.getElementById('g-zoom').style.transition = 'transform .35s cubic-bezier(.4,0,.2,1)';
  applyTransform();
  setTimeout(()=>document.getElementById('g-zoom').style.transition='', 380);
}}

/* ── Mouse / Touch handlers ── */
const sc = document.getElementById('sc');

sc.addEventListener('wheel', ev=>{{
  ev.preventDefault();
  const rect = sc.getBoundingClientRect();
  const cx   = ev.clientX - rect.left;
  const cy   = ev.clientY - rect.top;
  const dir  = ev.deltaY < 0 ? 1 : -1;
  zoomAt(cx, cy, dir * ZOOM_STEP * (ev.ctrlKey ? 2 : 1));
}}, {{passive:false}});

sc.addEventListener('mousedown', ev=>{{
  if(ev.button !== 0) return;
  S.isDragging  = true;
  S.dragStartX  = ev.clientX;
  S.dragStartY  = ev.clientY;
  S.dragPanX    = S.panX;
  S.dragPanY    = S.panY;
  sc.classList.add('dragging');
}});
window.addEventListener('mousemove', ev=>{{
  if(!S.isDragging) return;
  S.panX = S.dragPanX + (ev.clientX - S.dragStartX);
  S.panY = S.dragPanY + (ev.clientY - S.dragStartY);
  applyTransform();
}});
window.addEventListener('mouseup', ()=>{{
  S.isDragging = false;
  sc.classList.remove('dragging');
}});

/* ══════════════════════════════════════
   STAGGERED ORBIT LAYOUT
   Jika ring > STAGGER_TH node → pecah jadi 2 sub-orbit (r_inner, r_outer)
══════════════════════════════════════ */
function computeLayout(centerId, w, h){{
  const cfg = D.configs[centerId];
  if(!cfg) return {{}};
  const cx = w/2, cy = h/2;
  const minDim = Math.min(w,h);
  const R1 = minDim * 0.20;
  const R2 = minDim * 0.37;
  const R3 = minDim * 0.55;
  const pos = {{}};
  pos[centerId] = {{x:cx, y:cy, ring:'center', r:0, angle:0}};

  function placeRing(ids, baseR, ringName){{
    const n = ids.length;
    if(!n) return;

    if(n > STAGGER_TH){{
      // Staggered: split into 2 sub-orbits
      const half1 = ids.slice(0, Math.ceil(n/2));
      const half2 = ids.slice(Math.ceil(n/2));
      const rInner = baseR * 0.87;
      const rOuter = baseR * 1.13;
      const ao = -Math.PI/2;
      half1.forEach((id,i)=>{{
        const a = ao + (2*Math.PI*i)/half1.length;
        pos[id] = {{x:cx+rInner*Math.cos(a), y:cy+rInner*Math.sin(a),
                    ring:ringName, r:rInner, angle:a, staggered:true}};
      }});
      half2.forEach((id,i)=>{{
        const a = ao + Math.PI/half2.length + (2*Math.PI*i)/half2.length;
        pos[id] = {{x:cx+rOuter*Math.cos(a), y:cy+rOuter*Math.sin(a),
                    ring:ringName, r:rOuter, angle:a, staggered:true}};
      }});
    }} else {{
      // Normal single orbit
      const ao = -Math.PI/2;
      ids.forEach((id,i)=>{{
        const a = ao + (2*Math.PI*i)/n;
        pos[id] = {{x:cx+baseR*Math.cos(a), y:cy+baseR*Math.sin(a),
                    ring:ringName, r:baseR, angle:a, staggered:false}};
      }});
    }}
  }}

  placeRing(cfg.ring1,                             R1, 'r1');
  placeRing(cfg.ring2,                             R2, 'r2');
  placeRing(cfg.ring3_extra.map(n=>n.id),          R3, 'r3');

  return {{pos, R1, R2, R3, cx, cy}};
}}

/* ══════════════════════════════════════
   ALL NODES MAP
══════════════════════════════════════ */
function allNodesForCenter(centerId){{
  const pmap = {{}};
  D.papers.forEach(p=>pmap[p.id]=p);
  (D.configs[centerId]?.ring3_extra || []).forEach(n=>pmap[n.id]=n);
  return pmap;
}}

/* ══════════════════════════════════════
   DRAW ORBITS
══════════════════════════════════════ */
function drawOrbits(g, layout){{
  g.innerHTML='';
  if(!S.showOrbits) return;
  const {{R1,R2,R3,cx,cy}} = layout;
  const cfg = D.configs[S.center];

  // Helper: draw one orbit circle
  function orbit(r, clr, sw, spd, lbl){{
    if(r<=0) return;
    const c = ns('circle',{{cx,cy,r,class:'orbit-ring',stroke:clr,
      'stroke-width':sw,style:`--spd:${{spd}}`}});
    g.appendChild(c);
    // label at top
    const t = ns('text',{{x:cx,y:cy-r-7,
      'font-family':'JetBrains Mono,monospace','font-size':'6.5',
      'letter-spacing':'2','text-anchor':'middle','dominant-baseline':'central',
      fill:clr,'text-transform':'uppercase',opacity:'.5'}});
    t.textContent=lbl;
    g.appendChild(t);
  }}

  // If staggered, draw inner+outer sub-orbits
  const n1 = cfg?.ring1?.length || 0;
  const n2 = cfg?.ring2?.length || 0;
  const n3 = (cfg?.ring3_extra||[]).length;

  if(n1>STAGGER_TH){{
    orbit(R1*.87,'rgba(56,189,248,.18)',1.2,'28s','R1a · LELUHUR');
    orbit(R1*1.13,'rgba(56,189,248,.13)',1.0,'32s','R1b');
  }} else {{
    orbit(R1,'rgba(56,189,248,.18)',1.3,'28s','R1 · LELUHUR');
  }}
  if(n2>STAGGER_TH){{
    orbit(R2*.87,'rgba(52,211,153,.15)',1.1,'38s','R2a · PENERUS');
    orbit(R2*1.13,'rgba(52,211,153,.10)',.9,'44s','R2b');
  }} else {{
    orbit(R2,'rgba(52,211,153,.15)',1.1,'38s','R2 · PENERUS');
  }}
  orbit(R3,'rgba(148,163,184,.09)',.8,'52s','R3 · TETANGGA');
}}

/* ══════════════════════════════════════
   DRAW EDGES
══════════════════════════════════════ */
function drawEdges(g, layout){{
  g.innerHTML='';
  const cfg = D.configs[S.center];
  if(!cfg) return;
  const {{pos}} = layout;

  cfg.edges.forEach(e=>{{
    const a=pos[e.src], b=pos[e.dst];
    if(!a||!b) return;
    const t=e.type;
    const clr = t==='r1'?'rgba(56,189,248,.3)':t==='r2'?'rgba(52,211,153,.26)':'rgba(148,163,184,.15)';
    const arr = t==='r1'?'url(#arr-r1)':t==='r2'?'url(#arr-r2)':'url(#arr-r3)';
    const dx=b.x-a.x, dy=b.y-a.y, dist=Math.sqrt(dx*dx+dy*dy)||1;
    const curve=dist*.12;
    const mx=(a.x+b.x)/2 - dy*curve/dist;
    const my=(a.y+b.y)/2 + dx*curve/dist;
    const path = ns('path',{{
      d:`M${{a.x}},${{a.y}} Q${{mx}},${{my}} ${{b.x}},${{b.y}}`,
      class:'edge-line',stroke:clr,
      'stroke-width':Math.max(.6,e.weight*1.6),
      'marker-end':arr,
    }});
    path.dataset.src=e.src; path.dataset.dst=e.dst;
    g.appendChild(path);
  }});
}}

/* ══════════════════════════════════════
   DRAW NODES
══════════════════════════════════════ */
function drawNodes(g, layout, pmap){{
  g.innerHTML='';
  const cfg = D.configs[S.center];
  if(!cfg) return;
  const {{pos}} = layout;

  Object.entries(pos).forEach(([id,p])=>{{
    const node = pmap[id];
    if(!node) return;
    const isCenter = (id===S.center);
    const ring = p.ring;
    const sz   = isCenter ? nodeSize(node.citations)*1.3 : nodeSize(node.citations);
    const clr  = ringColor(ring);
    const fil  = isCenter?'f-center':'f-node';

    const grp = ns('g',{{class:'inode',transform:`translate(${{p.x}},${{p.y}})`}});
    grp.dataset.id   = id;
    grp.dataset.ring = ring;

    // Body group (dimmed when focus mode)
    const body = ns('g',{{class:'n-body'}});

    // Outer glow
    body.appendChild(ns('circle',{{r:sz+9,fill:clr,opacity:'.08',filter:'url(#f-glow)'}}));

    // Pulse ring (center only)
    if(isCenter){{
      const pr=ns('circle',{{r:sz+5,fill:'none',stroke:clr,
        'stroke-width':'1.4',opacity:'.55',class:'n-pulse'}});
      body.appendChild(pr);
    }}

    // Main node circle
    body.appendChild(ns('circle',{{
      r:sz,
      fill:`url(#grad-${{ring==='center'?'center':ring}})`,
      stroke:clr,'stroke-width':isCenter?2:1.3,
      filter:`url(#${{fil}})`
    }}));

    // Inner highlight
    body.appendChild(ns('circle',{{
      r:sz*.26,cx:-sz*.22,cy:-sz*.26,
      fill:'rgba(255,255,255,0.20)'
    }}));

    // Year text (inside node)
    const yrT = ns('text',{{
      x:0,y:0,
      'font-family':'JetBrains Mono,monospace',
      'font-size': Math.max(7,sz*.38),
      'font-weight':'500',
      fill:clr,'text-anchor':'middle','dominant-baseline':'central',
      'pointer-events':'none'
    }});
    yrT.textContent=node.year;
    body.appendChild(yrT);
    grp.appendChild(body);

    // ── Label group (smart visibility) ──
    const lblGrp = ns('g',{{class:'n-label-grp'}});
    lblGrp.dataset.ring  = ring;
    lblGrp.dataset.cites = node.citations || 0;

    const lblY   = sz+14;
    const rawLbl = node.title_short || id.substring(0,22);
    const maxCh  = isCenter?48:28;
    const lblTxt = rawLbl.length>maxCh ? rawLbl.substring(0,maxCh)+'…' : rawLbl;

    // Background rect for readability
    const lblBg = ns('rect',{{
      x:-70,y:lblY-2,width:140,height:13,rx:2,
      fill:'rgba(3,9,22,.78)','pointer-events':'none'
    }});
    lblGrp.appendChild(lblBg);

    const lbl = ns('text',{{
      x:0,y:lblY+8,
      'font-family':'Sora,sans-serif',
      'font-size': isCenter?10:8.5,
      'font-weight': isCenter?'600':'400',
      fill:'#d0e4f8','text-anchor':'middle',
      'dominant-baseline':'central','pointer-events':'none',
    }});
    lbl.textContent=lblTxt;
    lblGrp.appendChild(lbl);

    // Citation badge
    const citeY = lblY+17;
    const citeBg = ns('rect',{{
      x:-34,y:citeY-2,width:68,height:11,rx:2,
      fill:'rgba(3,9,22,.65)','pointer-events':'none'
    }});
    lblGrp.appendChild(citeBg);
    const cT = ns('text',{{
      x:0,y:citeY+4,
      'font-family':'JetBrains Mono,monospace','font-size':7.5,
      fill:clr,opacity:'.7','text-anchor':'middle',
      'dominant-baseline':'central','pointer-events':'none'
    }});
    cT.textContent=`↑ ${{(node.citations||0).toLocaleString()}}`;
    lblGrp.appendChild(cT);

    grp.appendChild(lblGrp);

    // Events
    grp.addEventListener('mouseenter', ev=>showTooltip(ev,node,ring));
    grp.addEventListener('mouseleave', hideTooltip);
    grp.addEventListener('click',      ()=>onNodeClick(id,node,ring));

    g.appendChild(grp);
  }});

  moveNebula(pos[S.center]?.x||W()/2, pos[S.center]?.y||H()/2);
  updateLabelVisibility();
}}

/* ══════════════════════════════════════
   SMART LABEL VISIBILITY
   - Zoom < 0.6  → hanya center label
   - Zoom 0.6-1  → center + top-cited nodes
   - Zoom > 1    → semua label
   - Focus mode  → hanya focused node + neighbors
══════════════════════════════════════ */
function updateLabelVisibility(){{
  const z = S.zoom;
  document.querySelectorAll('.n-label-grp').forEach(el=>{{
    const ring  = el.dataset.ring;
    const cites = parseInt(el.dataset.cites)||0;
    const grp   = el.closest('.inode');
    const id    = grp?.dataset.id;
    const isCenter = (id===S.center);

    let show = false;
    if(z>=1.4)           show=true;              // all labels at high zoom
    else if(z>=0.85)     show=(cites>50||isCenter);
    else if(z>=0.55)     show=(cites>200||isCenter);
    else                 show=isCenter;

    // Focus override: if focus mode, show labels for focused+neighbors
    if(S.focusNodeId && !grp?.classList.contains('dimmed')){{
      show=true;
    }}

    el.style.opacity = show?'1':'0';
    el.style.pointerEvents = show?'auto':'none';
  }});
}}

/* ══════════════════════════════════════
   NEBULA GLOW
══════════════════════════════════════ */
function moveNebula(x,y){{
  const neb=document.getElementById('nebula');
  const sz=Math.min(W(),H())*.52;
  // Account for zoom+pan when positioning nebula
  const sx = S.panX + x*S.zoom;
  const sy = S.panY + y*S.zoom;
  neb.style.cssText=`
    width:${{sz}}px;height:${{sz}}px;
    left:${{sx-sz/2}}px;top:${{sy-sz/2}}px;
    background:radial-gradient(circle,rgba(251,191,36,.11) 0%,rgba(56,189,248,.05) 38%,transparent 68%);
    display:block;
  `;
}}

/* ══════════════════════════════════════
   MINI-MAP
══════════════════════════════════════ */
function updateMinimap(){{
  const mmg = document.getElementById('mm-nodes');
  const mmv = document.getElementById('mm-viewport');
  mmg.innerHTML='';

  const layout = computeLayout(S.center, W(), H());
  if(!layout.pos) return;
  const pmap = allNodesForCenter(S.center);

  const mmW=120, mmH=90;
  const scaleX = mmW/(W()||1);
  const scaleY = mmH/(H()||1);

  Object.entries(layout.pos).forEach(([id,p])=>{{
    const node = pmap[id];
    if(!node) return;
    const isC=(id===S.center);
    const clr=RING_CLR[p.ring]||RING_CLR.r3;
    const sz=isC?5:Math.max(2,Math.min(5,Math.log((node.citations||0)+1)*.8));
    mmg.appendChild(ns('circle',{{
      cx:p.x*scaleX, cy:p.y*scaleY, r:sz,
      fill:clr, opacity:isC?.95:.5
    }}));
  }});

  // Viewport rect in minimap coords
  const vx = (-S.panX/S.zoom) * scaleX;
  const vy = (-S.panY/S.zoom) * scaleY;
  const vw = (W()/S.zoom) * scaleX;
  const vh = (H()/S.zoom) * scaleY;
  mmv.setAttribute('x',   Math.max(0,vx));
  mmv.setAttribute('y',   Math.max(0,vy));
  mmv.setAttribute('width',  Math.min(mmW,vw));
  mmv.setAttribute('height', Math.min(mmH,vh));
}}

/* ── Minimap click → pan to position ── */
document.getElementById('minimap').addEventListener('click', ev=>{{
  const rect = document.getElementById('minimap').getBoundingClientRect();
  const mx=(ev.clientX-rect.left)/120;
  const my=(ev.clientY-rect.top) /90;
  S.panX = W()/2 - mx*W()*S.zoom;
  S.panY = H()/2 - my*H()*S.zoom;
  applyTransform();
}});

/* ══════════════════════════════════════
   STATS PANEL
══════════════════════════════════════ */
function updateStats(){{
  const cfg  = D.configs[S.center]||{{}};
  const st   = cfg.stats||{{}};
  const pmap = allNodesForCenter(S.center);
  const cn   = pmap[S.center]||{{}};
  const maxC = Math.max(...D.papers.map(p=>p.citations),1);
  const pct  = Math.min(100,Math.round((cn.citations||0)/maxC*100));
  document.getElementById('sp-content').innerHTML=`
    <div style="font-family:var(--font-body);font-size:8.5px;color:var(--r1-c,#38bdf8);
      padding:0 0 6px;line-height:1.4">${{esc((cn.title_short||'—').substring(0,50))}}</div>
    <div class="sp-row">
      <span class="sp-k">Sitasi</span>
      <span class="sp-v" style="color:#fbbf24">${{(cn.citations||0).toLocaleString()}}</span>
    </div>
    <div class="sp-bar"><div class="sp-fill" style="width:${{pct}}%;background:#fbbf24"></div></div>
    <div class="sp-row"><span class="sp-k">Leluhur</span>  <span class="sp-v" style="color:#38bdf8">${{st.ancestors||0}}</span></div>
    <div class="sp-row"><span class="sp-k">Penerus</span>  <span class="sp-v" style="color:#34d399">${{st.descendants||0}}</span></div>
    <div class="sp-row"><span class="sp-k">Tetangga</span> <span class="sp-v" style="color:#94a3b8">${{st.extra_neighbors||0}}</span></div>
    <div class="sp-row"><span class="sp-k">Tahun</span>    <span class="sp-v">${{cn.year||'?'}}</span></div>
  `;
}}

/* ══════════════════════════════════════
   TOOLTIP
══════════════════════════════════════ */
function showTooltip(ev,node,ring){{
  const tt=document.getElementById('tt');
  const rc=RING_CLR[ring]||RING_CLR.r3;
  const rn=RING_NAMES[ring]||ring;
  tt.innerHTML=`
    <div class="tt-title">${{esc(node.title)}}</div>
    <div class="tt-meta">👤 ${{esc((node.authors||'N/A').split(',').slice(0,2).join(', '))}}</div>
    <div class="tt-meta">📅 ${{node.year}} &nbsp;·&nbsp; ↑ ${{(node.citations||0).toLocaleString()}} sitasi</div>
    <div class="tt-meta">🏛️ ${{esc(node.venue||'—')}}</div>
    <span class="tt-ring" style="color:${{rc}};border-color:${{rc}}">${{rn}}</span>
    <div class="tt-abs">${{esc(node.abstract)}}</div>
    ${{ring!=='center'
      ?`<div class="tt-hint">🖱 Klik 1× → detail panel &nbsp;·&nbsp; Klik ⊙ → jadikan pusat</div>`
      :`<div class="tt-hint">⊙ Paper pusat — scroll untuk zoom</div>`
    }}
  `;
  const sc=document.getElementById('sc').getBoundingClientRect();
  let tx=ev.clientX-sc.left+14, ty=ev.clientY-sc.top-10;
  if(tx+278>sc.width)  tx=ev.clientX-sc.left-278;
  if(ty+270>sc.height) ty=ev.clientY-sc.top-270;
  tt.style.cssText=`display:block;left:${{tx}}px;top:${{ty}}px`;
}}
function hideTooltip(){{ document.getElementById('tt').style.display='none'; }}

/* ══════════════════════════════════════
   FOCUS MODE  (Click-to-Focus)
══════════════════════════════════════ */
function applyFocusMode(id){{
  S.focusNodeId=id;
  const cfg=D.configs[S.center];
  if(!cfg) return;

  // Build connected set
  const connected=new Set([id,S.center]);
  cfg.edges.forEach(e=>{{
    if(e.src===id||e.dst===id){{connected.add(e.src);connected.add(e.dst);}}
  }});

  document.querySelectorAll('.inode').forEach(el=>{{
    el.classList.toggle('dimmed', !connected.has(el.dataset.id));
  }});
  document.querySelectorAll('.edge-line').forEach(el=>{{
    const conn=connected.has(el.dataset.src)&&connected.has(el.dataset.dst);
    el.classList.toggle('dimmed',!conn);
  }});

  document.getElementById('btn-reset-focus').classList.add('vis');
  updateLabelVisibility();
}}

function clearFocusMode(){{
  S.focusNodeId=null;
  document.querySelectorAll('.inode,.edge-line').forEach(el=>el.classList.remove('dimmed'));
  document.getElementById('btn-reset-focus').classList.remove('vis');
  updateLabelVisibility();
}}

/* ══════════════════════════════════════
   NODE CLICK
══════════════════════════════════════ */
let _lastClick=null;
function onNodeClick(id,node,ring){{
  hideTooltip();
  if(id===S.center){{ clearFocusMode(); return; }}
  _lastClick=id;
  openPanel(id,node,ring);
  applyFocusMode(id);
}}

/* ══════════════════════════════════════
   DETAIL PANEL
══════════════════════════════════════ */
let _panelNodeId=null;
function openPanel(id,node,ring){{
  _panelNodeId=id;
  const rc=RING_CLR[ring]||RING_CLR.r3;
  document.getElementById('dp-title').textContent=node.title;
  document.getElementById('dp-abs').textContent=node.abstract;
  document.getElementById('dp-link').href=node.link||'#';
  document.getElementById('dp-rows').innerHTML=`
    <div class="dp-row"><span class="dp-k">TAHUN</span>  <span class="dp-v">${{node.year}}</span></div>
    <div class="dp-row"><span class="dp-k">SITASI</span> <span class="dp-v" style="color:#fbbf24">${{(node.citations||0).toLocaleString()}}</span></div>
    <div class="dp-row"><span class="dp-k">RING</span>   <span class="dp-v" style="color:${{rc}}">${{RING_NAMES[ring]||ring}}</span></div>
    <div class="dp-row"><span class="dp-k">VENUE</span>  <span class="dp-v" style="font-size:8px">${{esc((node.venue||'—').substring(0,26))}}</span></div>
  `;
  document.getElementById('dp').classList.add('vis');
}}
function closePanel(){{
  document.getElementById('dp').classList.remove('vis');
  clearFocusMode();
}}
function reCenterFromPanel(){{
  if(_panelNodeId){{ closePanel(); reCenter(_panelNodeId); }}
}}

/* ══════════════════════════════════════
   RE-CENTER  (smooth fade transition)
══════════════════════════════════════ */
function reCenter(newId){{
  if(S.transitioning||newId===S.center) return;
  if(!D.configs[newId]) return;
  S.transitioning=true;
  const gn=document.getElementById('g-nodes');
  const ge=document.getElementById('g-edges');
  gn.style.transition=ge.style.transition='opacity .3s';
  gn.style.opacity=ge.style.opacity='0';
  setTimeout(()=>{{
    S.center=newId;
    clearFocusMode();
    document.getElementById('paper-sel').value=newId;
    renderMain();
    updateStats();
    gn.style.opacity=ge.style.opacity='1';
    setTimeout(()=>{{S.transitioning=false;}},320);
  }},280);
}}

/* ══════════════════════════════════════
   TOGGLES
══════════════════════════════════════ */
function toggleParticles(){{
  S.showPart=!S.showPart;
  document.getElementById('btn-part').className='c-btn'+(S.showPart?' on-amber':'');
}}
function toggleOrbits(){{
  S.showOrbits=!S.showOrbits;
  document.getElementById('btn-orb').className='c-btn'+(S.showOrbits?' on-sky':'');
  const layout=computeLayout(S.center,W(),H());
  drawOrbits(document.getElementById('g-orbits'),layout);
}}
function toggleHeatmap(){{
  S.heatmap=!S.heatmap;
  document.getElementById('btn-heat').className='c-btn'+(S.heatmap?' on-green':'');
  renderMain();
}}
function onSelectCenter(val){{
  if(val&&val!==S.center) reCenter(val);
}}

/* ══════════════════════════════════════
   PARTICLE SYSTEM  (canvas overlay, unchanged from v2)
══════════════════════════════════════ */
const PARTICLES=[];
const P_MAX=55;
let _cachedLayout=null;

function spawnParticle(a,b,ring){{
  if(PARTICLES.length>=P_MAX) return;
  const clr=ring==='r1'?'#38bdf8':ring==='r2'?'#34d399':'#94a3b8';
  PARTICLES.push({{
    sx:a.x,sy:a.y,dx:b.x,dy:b.y,
    t:Math.random(),spd:.010+Math.random()*.008,
    r:1.4+Math.random()*1.4,clr,
    alpha:.55+Math.random()*.4,trail:[],
  }});
}}
function lerp(a,b,t){{return a+(b-a)*t;}}
function updateParticles(){{
  for(let i=PARTICLES.length-1;i>=0;i--){{
    const p=PARTICLES[i];
    p.trail.push({{x:lerp(p.sx,p.dx,p.t),y:lerp(p.sy,p.dy,p.t)}});
    if(p.trail.length>5) p.trail.shift();
    p.t+=p.spd;
    if(p.t>1) PARTICLES.splice(i,1);
  }}
}}
function drawParticles(){{
  const cv=document.getElementById('cv');
  const ctx=cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  if(!S.showPart) return;

  // Apply same transform as SVG zoom/pan
  ctx.save();
  ctx.translate(S.panX,S.panY);
  ctx.scale(S.zoom,S.zoom);

  PARTICLES.forEach(p=>{{
    const x=lerp(p.sx,p.dx,p.t), y=lerp(p.sy,p.dy,p.t);
    if(p.trail.length>1){{
      ctx.beginPath();
      ctx.moveTo(p.trail[0].x,p.trail[0].y);
      p.trail.forEach(pt=>ctx.lineTo(pt.x,pt.y));
      ctx.strokeStyle=p.clr+'44';ctx.lineWidth=p.r*.5;ctx.stroke();
    }}
    const g=ctx.createRadialGradient(x,y,0,x,y,p.r*2);
    g.addColorStop(0,p.clr+'ee');g.addColorStop(1,p.clr+'00');
    ctx.beginPath();ctx.arc(x,y,p.r*2,0,Math.PI*2);
    ctx.fillStyle=g;ctx.fill();
  }});
  ctx.restore();
}}

let _ptick=0;
function tickParticles(){{
  _ptick++;
  if(_ptick%9===0&&S.showPart){{
    const cfg=D.configs[S.center];
    if(!cfg||!_cachedLayout?.pos) return;
    const edges=cfg.edges;
    if(!edges.length) return;
    const e=edges[Math.floor(Math.random()*edges.length)];
    const a=_cachedLayout.pos[e.src],b=_cachedLayout.pos[e.dst];
    if(a&&b) spawnParticle(a,b,e.type);
  }}
}}

/* ══════════════════════════════════════
   MAIN RENDER
══════════════════════════════════════ */
function renderMain(){{
  const w=W(),h=H();
  const layout=computeLayout(S.center,w,h);
  _cachedLayout=layout;
  const pmap=allNodesForCenter(S.center);
  drawOrbits(document.getElementById('g-orbits'),layout);
  drawEdges (document.getElementById('g-edges'), layout);
  drawNodes (document.getElementById('g-nodes'), layout,pmap);
  updateMinimap();
}}

/* ══════════════════════════════════════
   ANIMATION LOOP
══════════════════════════════════════ */
function animLoop(){{
  tickParticles();updateParticles();drawParticles();
  requestAnimationFrame(animLoop);
}}

/* ══════════════════════════════════════
   POPULATE SELECTORS
══════════════════════════════════════ */
function populateSelectors(){{
  const opts=D.papers.map(p=>
    `<option value="${{esc(p.id)}}">${{esc((p.title_short||p.id.substring(0,38)))}}</option>`
  ).join('');
  document.getElementById('paper-sel').innerHTML=opts;
  document.getElementById('paper-sel').value=S.center;
}}

/* ══════════════════════════════════════
   CANVAS RESIZE
══════════════════════════════════════ */
function resizeCanvas(){{
  const cv=document.getElementById('cv');
  cv.width=W();cv.height=H();
}}

/* ── Click on empty SVG bg → clear focus ── */
document.getElementById('svg-bg').addEventListener('click',()=>closePanel());

/* ── Window resize ── */
let _rt;
window.addEventListener('resize',()=>{{
  clearTimeout(_rt);
  _rt=setTimeout(()=>{{resizeCanvas();renderMain();}},90);
}});

/* ══════════════════════════════════════
   INIT
══════════════════════════════════════ */
function init(){{
  resizeCanvas();
  populateSelectors();
  renderMain();
  updateStats();
  applyTransform();
  requestAnimationFrame(animLoop);
}}

document.readyState==='loading'
  ? document.addEventListener('DOMContentLoaded',init)
  : setTimeout(init,60);
</script>
</body>
</html>"""
