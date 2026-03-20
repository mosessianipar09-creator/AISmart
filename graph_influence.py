"""
graph_influence.py
==================
Influence Map — Visualisasi hubungan antar paper berbasis sitasi.

Tampilkan jaringan 50-100 paper sebagai force-directed graph:
  - Node besar  = banyak dikutip
  - Warna node  = ring (pusat / leluhur / penerus / tetangga)
  - Garis tebal = koneksi kuat
  - Klik node   → panel detail + highlight koneksi
  - Search box  → filter/highlight paper by judul
  - Drag node   → reposition manual
  - Zoom/pan    → scroll atau tombol ± 

Fungsi publik:
    render_influence(papers, height)   → str  HTML siap embed di Streamlit
    influence_stats(papers, center_id) → dict statistik untuk metric cards
    build_influence_data(papers)       → dict data mentah (nodes + edges)
"""

from __future__ import annotations

import math
import json
import sys
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from data_layer import _raw_get

_R3_MIN_CITATIONS: int = 20
_FETCH_WORKERS: int = 8


# ─────────────────────────────────────────────────────────────────
# FETCH
# ─────────────────────────────────────────────────────────────────

def _do_fetch(paper_id: str) -> dict:
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
        print(f"[graph_influence] fetch failed {paper_id!r}: {exc}", file=sys.stderr)
        return {"references": [], "citations": []}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_refs(paper_id: str) -> dict:
    if not paper_id or paper_id.startswith("local_"):
        return {"references": [], "citations": []}
    return _do_fetch(paper_id)


def _fetch_all(pids: list[str]) -> dict[str, dict]:
    """Fetch semua refs secara parallel — jauh lebih cepat dari sequential."""
    result = {}
    real   = [p for p in pids if p and not p.startswith("local_")]
    for p in pids:
        if p not in real:
            result[p] = {"references": [], "citations": []}
    if not real:
        return result
    with ThreadPoolExecutor(max_workers=min(_FETCH_WORKERS, len(real))) as ex:
        futures = {ex.submit(fetch_refs, p): p for p in real}
        for f in as_completed(futures):
            pid = futures[f]
            try:
                result[pid] = f.result()
            except Exception as exc:
                print(f"[graph_influence] parallel fetch error {pid!r}: {exc}", file=sys.stderr)
                result[pid] = {"references": [], "citations": []}
    return result


# ─────────────────────────────────────────────────────────────────
# NORMALIZE
# ─────────────────────────────────────────────────────────────────

def _pid(paper: dict, idx: int) -> str:
    link = paper.get("link", "")
    if "semanticscholar.org/paper/" in link:
        return link.split("/paper/")[-1].strip("/")
    slug = (paper.get("title", "") or f"paper_{idx}")[:30].replace(" ", "_")
    return f"local_{idx}_{slug}"


def _int(val, default=0) -> int:
    try:
        return max(0, int(str(val).replace(",", "").strip()))
    except Exception:
        return default


def _year(val) -> int:
    try:
        y = int(str(val).strip())
        return y if 1900 < y <= 2030 else 2020
    except Exception:
        return 2020


def _authors(val) -> str:
    if isinstance(val, (list, tuple)):
        val = ", ".join(str(v).strip() for v in val if v)
    return str(val or "").strip() or "N/A"


def _norm(p: dict, idx: int) -> dict:
    pid   = _pid(p, idx)
    title = (p.get("title", "") or "Untitled").strip()
    abstr = (p.get("abstract", "") or "").strip()
    return {
        "id":        pid,
        "title":     title,
        "short":     (title[:60] + "…") if len(title) > 60 else title,
        "authors":   _authors(p.get("authors")),
        "year":      _year(p.get("year")),
        "citations": _int(p.get("citations", 0)),
        "venue":     (p.get("venue", "") or "").strip() or "—",
        "abstract":  (abstr[:300] + "…") if len(abstr) > 300 else abstr,
        "link":      p.get("link", ""),
    }


# ─────────────────────────────────────────────────────────────────
# BUILD GRAPH DATA
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def build_influence_data(papers: list[dict]) -> dict:
    """
    Build nodes + edges untuk seluruh paper.

    Node fields: id, title, short, authors, year, citations, venue, abstract, link, ring
    Edge fields: source, target, weight

    Ring assignment (relatif terhadap paper paling banyak dikutip):
      'center' → paper dengan sitasi terbanyak
      'r1'     → dikutip oleh center (leluhur intelektual)
      'r2'     → mengutip center (penerus)
      'r3'     → koneksi tidak langsung / tetangga API

    Returns:
        {
          "nodes":     [NodeDict, ...],
          "edges":     [EdgeDict, ...],
          "center_id": str
        }
    """
    if not papers:
        return {"nodes": [], "edges": [], "center_id": ""}

    # Normalize & deduplicate
    nodes_raw = []
    seen_ids: dict = {}
    for i, p in enumerate(papers):
        n = _norm(p, i)
        if n["id"] in seen_ids:
            n["id"] = n["id"] + f"_d{i}"
        seen_ids[n["id"]] = True
        nodes_raw.append(n)

    pmap = {n["id"]: n for n in nodes_raw}

    # Default center = paper paling banyak dikutip
    center_id = max(pmap, key=lambda k: pmap[k]["citations"])

    # Fetch semua refs secara parallel
    refs_cache = _fetch_all(list(pmap.keys()))

    # Assign ring untuk setiap node relatif terhadap center
    center    = pmap[center_id]
    refs_data = refs_cache.get(center_id, {})
    ref_ids   = {r.get("paperId") for r in refs_data.get("references", []) if r.get("paperId")}
    cite_ids  = {c.get("paperId") for c in refs_data.get("citations",  []) if c.get("paperId")}

    for pid, node in pmap.items():
        if pid == center_id:
            node["ring"] = "center"
        elif pid in ref_ids:
            node["ring"] = "r1"
        elif pid in cite_ids:
            node["ring"] = "r2"
        else:
            # Fallback temporal
            if node["year"] < center["year"]:
                node["ring"] = "r1"
            elif node["year"] > center["year"]:
                node["ring"] = "r2"
            else:
                node["ring"] = "r1" if node["citations"] >= center["citations"] else "r2"

    # Tambah tetangga luar (ring 3) dari API — max 30 node tambahan
    r3_nodes  = []
    seen_all  = set(pmap.keys())
    api_pool  = refs_data.get("references", []) + refs_data.get("citations", [])
    api_pool  = sorted(api_pool, key=lambda x: x.get("citationCount", 0), reverse=True)

    for nd in api_pool:
        nid  = nd.get("paperId", "")
        ntit = (nd.get("title", "") or "").strip()
        nc   = nd.get("citationCount", 0) or 0
        if nid and nid not in seen_all and ntit and nc > _R3_MIN_CITATIONS:
            r3_nodes.append({
                "id":        nid,
                "title":     ntit,
                "short":     (ntit[:60] + "…") if len(ntit) > 60 else ntit,
                "authors":   "—",
                "year":      nd.get("year", "?") or "?",
                "citations": nc,
                "venue":     "—",
                "abstract":  "Paper dari jaringan sitasi eksternal.",
                "link":      f"https://www.semanticscholar.org/paper/{nid}",
                "ring":      "r3",
            })
            seen_all.add(nid)
            if len(r3_nodes) >= 30:
                break

    all_nodes = list(pmap.values()) + r3_nodes
    all_pmap  = {n["id"]: n for n in all_nodes}

    # Build edges
    edges      = []
    seen_edges: set = set()

    def add_edge(src, dst, w):
        key = (min(src, dst), max(src, dst))
        if key not in seen_edges and src in all_pmap and dst in all_pmap:
            seen_edges.add(key)
            edges.append({"source": src, "target": dst, "weight": round(w, 3)})

    # Center → ring1 (references) dan center ← ring2 (citations)
    for ref in refs_data.get("references", []):
        nid = ref.get("paperId", "")
        if nid and nid in all_pmap:
            w = math.log(ref.get("citationCount", 1) + 1) / 4
            add_edge(center_id, nid, max(0.4, w))

    for cit in refs_data.get("citations", []):
        nid = cit.get("paperId", "")
        if nid and nid in all_pmap:
            w = math.log(cit.get("citationCount", 1) + 1) / 4
            add_edge(center_id, nid, max(0.3, w))

    # Cross-edges antar non-center nodes (cap 20 per node agar tidak meledak)
    for pid in list(pmap.keys()):
        if pid == center_id:
            continue
        rc = refs_cache.get(pid, {})
        for ref in rc.get("references", [])[:20]:
            nid = ref.get("paperId", "")
            if nid and nid in all_pmap and nid != pid:
                w = math.log(ref.get("citationCount", 1) + 1) / 6
                add_edge(pid, nid, max(0.2, w))

    return {
        "nodes":     all_nodes,
        "edges":     edges,
        "center_id": center_id,
    }


# ─────────────────────────────────────────────────────────────────
# STATS
# ─────────────────────────────────────────────────────────────────

def influence_stats(papers: list[dict], center_id: str = None) -> dict:
    """Statistik singkat untuk metric cards Streamlit."""
    if not papers:
        return {}
    data  = build_influence_data(papers)
    nodes = {n["id"]: n for n in data["nodes"]}
    cid   = center_id or data["center_id"]
    cn    = nodes.get(cid, {})
    rings: dict = {}
    for n in data["nodes"]:
        rings[n["ring"]] = rings.get(n["ring"], 0) + 1
    return {
        "total_nodes":      len(data["nodes"]),
        "total_edges":      len(data["edges"]),
        "center_title":     cn.get("short", "—"),
        "center_citations": cn.get("citations", 0),
        "ring1_count":      rings.get("r1", 0),
        "ring2_count":      rings.get("r2", 0),
        "ring3_count":      rings.get("r3", 0),
    }


# ─────────────────────────────────────────────────────────────────
# RENDER HTML
# ─────────────────────────────────────────────────────────────────

def render_influence(papers: list[dict], height: int = 680) -> str:
    """
    Render Influence Map sebagai HTML interaktif.
    Gunakan D3.js force-directed graph — optimal untuk 50-100 node.

    Cara pakai di Streamlit:
        import streamlit.components.v1 as components
        components.html(render_influence(papers), height=700, scrolling=False)

    Returns:
        str — HTML lengkap siap embed
    """
    data      = build_influence_data(papers)
    _raw      = json.dumps(data, ensure_ascii=False).replace("</", r"<\/")
    data_json = json.dumps(_raw)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  background:#0d1117;color:#c9d1d9;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  width:100%;height:{height}px;overflow:hidden;
}}

/* ── Layout ── */
#root{{display:flex;height:{height}px;}}
#graph-wrap{{flex:1;position:relative;min-width:0;}}
#panel{{
  width:260px;flex-shrink:0;
  background:#161b22;border-left:1px solid #30363d;
  display:flex;flex-direction:column;overflow:hidden;
}}

/* ── Top bar ── */
#topbar{{
  position:absolute;top:0;left:0;right:0;height:40px;
  background:rgba(13,17,23,.94);border-bottom:1px solid #21262d;
  padding:0 12px;display:flex;align-items:center;gap:10px;
  z-index:10;backdrop-filter:blur(8px);
}}
#topbar h1{{
  font-size:11px;font-weight:700;color:#58a6ff;
  letter-spacing:.5px;white-space:nowrap;flex-shrink:0;
}}
#search{{
  flex:1;max-width:200px;
  background:#0d1117;border:1px solid #30363d;border-radius:6px;
  padding:4px 10px;color:#c9d1d9;font-size:11px;outline:none;
}}
#search:focus{{border-color:#58a6ff;box-shadow:0 0 0 2px rgba(88,166,255,.15);}}
#search::placeholder{{color:#484f58;}}
.tag{{
  font-size:9px;padding:2px 7px;border-radius:10px;font-weight:600;
  white-space:nowrap;flex-shrink:0;
}}
.tag-center{{background:rgba(255,215,0,.12);color:#ffd700;}}
.tag-r1{{background:rgba(88,166,255,.10);color:#58a6ff;}}
.tag-r2{{background:rgba(63,185,80,.10);color:#3fb950;}}
.tag-r3{{background:rgba(110,118,129,.12);color:#8b949e;}}

/* ── Zoom controls ── */
#zoom-ctrl{{
  position:absolute;bottom:14px;left:14px;
  display:flex;gap:4px;z-index:10;
}}
.z-btn{{
  width:28px;height:28px;
  background:#161b22;border:1px solid #30363d;
  border-radius:6px;color:#8b949e;font-size:15px;line-height:1;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:all .15s;user-select:none;
}}
.z-btn:hover{{background:#21262d;color:#c9d1d9;border-color:#58a6ff;}}

/* ── SVG ── */
svg{{width:100%;height:100%;display:block;}}
.link{{stroke-opacity:.5;transition:stroke-opacity .18s;}}
.link.faded{{stroke-opacity:.05;}}
.link.lit{{stroke-opacity:.9;}}
.node-circle{{
  cursor:pointer;stroke-width:1.5px;
  transition:opacity .18s,filter .18s;
}}
.node-circle.faded{{opacity:.1;}}
.node-circle.lit{{stroke-width:2.8px;filter:brightness(1.4) drop-shadow(0 0 4px currentColor);}}
.node-label{{
  font-size:9px;fill:#6e7681;pointer-events:none;
  dominant-baseline:central;
}}
.node-label.vis{{fill:#c9d1d9;}}

/* ── Tooltip ── */
#tooltip{{
  position:absolute;display:none;pointer-events:none;
  background:#1c2128;border:1px solid #30363d;border-radius:8px;
  padding:9px 12px;max-width:220px;z-index:50;
  box-shadow:0 8px 24px rgba(0,0,0,.55);
  font-size:10.5px;line-height:1.45;
}}
#tooltip .tt-title{{font-weight:600;color:#e6edf3;margin-bottom:4px;}}
#tooltip .tt-meta{{color:#8b949e;font-size:9.5px;}}

/* ── Side panel ── */
#stats-row{{
  display:flex;border-bottom:1px solid #21262d;flex-shrink:0;
}}
.stat-box{{
  flex:1;padding:8px;border-right:1px solid #21262d;text-align:center;
}}
.stat-box:last-child{{border-right:none;}}
.stat-num{{font-size:15px;font-weight:700;color:#e6edf3;}}
.stat-lbl{{font-size:8px;color:#484f58;margin-top:1px;text-transform:uppercase;letter-spacing:.5px;}}

#panel-header{{
  padding:12px 14px 10px;border-bottom:1px solid #21262d;flex-shrink:0;
}}
.ph-label{{font-size:8.5px;letter-spacing:.8px;color:#484f58;text-transform:uppercase;margin-bottom:5px;}}
#panel-title{{font-size:11px;font-weight:600;color:#e6edf3;line-height:1.4;}}

#panel-body{{padding:10px 14px 14px;overflow-y:auto;flex:1;}}
.info-row{{
  display:flex;justify-content:space-between;align-items:baseline;
  padding:5px 0;border-bottom:1px solid #21262d;font-size:10px;
}}
.info-label{{color:#484f58;flex-shrink:0;}}
.info-val{{color:#c9d1d9;font-weight:500;text-align:right;max-width:150px;
  word-break:break-word;}}
#panel-abstract{{
  font-size:9.5px;color:#8b949e;line-height:1.6;
  margin-top:10px;padding-top:10px;border-top:1px solid #21262d;
}}
#panel-open{{
  display:block;text-align:center;margin:12px 0 6px;
  background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.2);
  border-radius:6px;padding:7px;color:#58a6ff;font-size:10px;
  text-decoration:none;transition:background .15s;font-weight:600;
}}
#panel-open:hover{{background:rgba(88,166,255,.18);}}
#panel-recenter{{
  display:block;text-align:center;
  background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.18);
  border-radius:6px;padding:7px;color:#ffd700;font-size:10px;
  cursor:pointer;transition:background .15s;font-weight:600;
}}
#panel-recenter:hover{{background:rgba(255,215,0,.14);}}
.empty-hint{{
  color:#484f58;font-size:10px;text-align:center;
  padding:30px 0;
}}

/* ── Legend ── */
#legend{{
  padding:8px 14px;border-top:1px solid #21262d;
  display:flex;flex-wrap:wrap;gap:8px;flex-shrink:0;
}}
.leg{{display:flex;align-items:center;gap:5px;font-size:9px;color:#484f58;}}
.leg-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}
</style>
</head>
<body>
<div id="root">

  <!-- Graph -->
  <div id="graph-wrap">
    <div id="topbar">
      <h1>◈ INFLUENCE MAP</h1>
      <input id="search" type="text" placeholder="Cari judul…" oninput="onSearch(this.value)">
      <span class="tag tag-center">⊙ Pusat</span>
      <span class="tag tag-r1" id="tag-r1">— Leluhur</span>
      <span class="tag tag-r2" id="tag-r2">— Penerus</span>
      <span class="tag tag-r3" id="tag-r3">— Tetangga</span>
    </div>

    <svg id="svg">
      <g id="g-zoom">
        <g id="g-links"></g>
        <g id="g-nodes"></g>
      </g>
    </svg>

    <div id="tooltip">
      <div class="tt-title" id="tt-title"></div>
      <div class="tt-meta"  id="tt-info"></div>
    </div>

    <div id="zoom-ctrl">
      <button class="z-btn" onclick="zoomIn()"   title="Zoom In">+</button>
      <button class="z-btn" onclick="zoomReset()" title="Reset">⊙</button>
      <button class="z-btn" onclick="zoomOut()"  title="Zoom Out">−</button>
    </div>
  </div>

  <!-- Panel -->
  <div id="panel">
    <div id="stats-row">
      <div class="stat-box">
        <div class="stat-num" id="s-nodes">—</div>
        <div class="stat-lbl">Nodes</div>
      </div>
      <div class="stat-box">
        <div class="stat-num" id="s-edges">—</div>
        <div class="stat-lbl">Edges</div>
      </div>
      <div class="stat-box">
        <div class="stat-num" id="s-cites">—</div>
        <div class="stat-lbl">Sitasi</div>
      </div>
    </div>

    <div id="panel-header">
      <div class="ph-label">Paper terpilih</div>
      <div id="panel-title" style="color:#484f58;font-size:10px">Klik node pada graf</div>
    </div>

    <div id="panel-body">
      <div id="panel-empty" class="empty-hint">◎<br>Klik node untuk<br>melihat detail</div>
      <div id="panel-detail" style="display:none">
        <div id="panel-rows"></div>
        <div id="panel-abstract"></div>
        <a id="panel-open" href="#" target="_blank" style="display:none">↗ Buka di Semantic Scholar</a>
        <div id="panel-recenter" onclick="recenterNode()">⊙ Jadikan Pusat</div>
      </div>
    </div>

    <div id="legend">
      <div class="leg"><div class="leg-dot" style="background:#ffd700"></div>Pusat</div>
      <div class="leg"><div class="leg-dot" style="background:#58a6ff"></div>Leluhur (R1)</div>
      <div class="leg"><div class="leg-dot" style="background:#3fb950"></div>Penerus (R2)</div>
      <div class="leg"><div class="leg-dot" style="background:#6e7681"></div>Tetangga (R3)</div>
    </div>
  </div>

</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
/* ── DATA ── */
const RAW = JSON.parse({data_json});

/* ── ESCAPE ── */
const esc = s => String(s==null?'':s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');

/* ── COLORS ── */
const CLR   = {{center:'#ffd700',r1:'#58a6ff',r2:'#3fb950',r3:'#6e7681'}};
const RNAME = {{center:'PUSAT',r1:'LELUHUR',r2:'PENERUS',r3:'TETANGGA'}};

/* ── STATE ── */
let centerNodeId = RAW.center_id;
let selectedId   = null;
let G            = null;   // {{nodes, edges, nmap, link, nodeG}}

/* ── HELPERS ── */
const svgEl = document.getElementById('svg');
const W = () => svgEl.clientWidth  || 800;
const H = () => svgEl.clientHeight || 600;
const nsize = c => Math.max(5, Math.min(22, 5 + Math.sqrt(c||0)*.55));

/* ── ZOOM ── */
const svg   = d3.select('#svg');
const gZoom = d3.select('#g-zoom');
const zoom  = d3.zoom()
  .scaleExtent([0.15, 5])
  .on('zoom', ev => gZoom.attr('transform', ev.transform));
svg.call(zoom);

function zoomIn()    {{ svg.transition().duration(220).call(zoom.scaleBy, 1.35); }}
function zoomOut()   {{ svg.transition().duration(220).call(zoom.scaleBy, 0.74); }}
function zoomReset() {{
  svg.transition().duration(380)
    .call(zoom.transform, d3.zoomIdentity.translate(W()/2, H()/2).scale(0.82));
}}

/* ── BUILD GRAPH ── */
function buildGraph(data) {{
  const nodes = data.nodes.map(n => ({{...n}}));
  const nmap  = Object.fromEntries(nodes.map(n => [n.id, n]));

  const edges = data.edges
    .filter(e => nmap[e.source] && nmap[e.target])
    .map(e => ({{...e}}));

  // Degree per node
  nodes.forEach(n => n.degree = 0);
  edges.forEach(e => {{
    if (nmap[e.source]) nmap[e.source].degree = (nmap[e.source].degree||0) + 1;
    if (nmap[e.target]) nmap[e.target].degree = (nmap[e.target].degree||0) + 1;
  }});

  if (G && G.sim) G.sim.stop();

  /* ── Simulation ── */
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges)
      .id(d => d.id)
      .distance(d => 65 + (1 - Math.min(d.weight||.5, 1)) * 85)
      .strength(.45))
    .force('charge', d3.forceManyBody()
      .strength(d => -130 - (d.degree||0) * 10))
    .force('center', d3.forceCenter(W()/2, H()/2).strength(.05))
    .force('collide', d3.forceCollide().radius(d => nsize(d.citations) + 7))
    .alphaDecay(.022)
    .velocityDecay(.38);

  // Pin center briefly
  const cn = nmap[centerNodeId];
  if (cn) {{
    cn.fx = W()/2; cn.fy = H()/2;
    setTimeout(() => {{ if(cn){{cn.fx=null;cn.fy=null;}} }}, 1800);
  }}

  /* ── Render links ── */
  const gLinks = d3.select('#g-links');
  gLinks.selectAll('*').remove();
  const link = gLinks.selectAll('line')
    .data(edges).join('line')
    .attr('class','link')
    .attr('stroke', e => {{
      const sr = (nmap[typeof e.source==='object'?e.source.id:e.source]||{{}}).ring;
      const tr = (nmap[typeof e.target==='object'?e.target.id:e.target]||{{}}).ring;
      if (sr==='center'||tr==='center') {{
        if (sr==='r1'||tr==='r1') return '#58a6ff';
        if (sr==='r2'||tr==='r2') return '#3fb950';
        return '#6e7681';
      }}
      return '#30363d';
    }})
    .attr('stroke-width', e => Math.max(.5, e.weight * 2.2));

  /* ── Render nodes ── */
  const gNodes = d3.select('#g-nodes');
  gNodes.selectAll('*').remove();
  const nodeG = gNodes.selectAll('g')
    .data(nodes).join('g')
    .call(d3.drag()
      .on('start', (ev,d) => {{ if(!ev.active) sim.alphaTarget(.2).restart(); d.fx=d.x;d.fy=d.y; }})
      .on('drag',  (ev,d) => {{ d.fx=ev.x;d.fy=ev.y; }})
      .on('end',   (ev,d) => {{ if(!ev.active) sim.alphaTarget(0); d.fx=null;d.fy=null; }})
    )
    .on('mouseenter', showTooltip)
    .on('mouseleave', () => document.getElementById('tooltip').style.display='none')
    .on('click', (ev,d) => {{ ev.stopPropagation(); onNodeClick(d, link, nodeG); }});

  nodeG.append('circle')
    .attr('class','node-circle')
    .attr('r', d => nsize(d.citations))
    .attr('fill', d => CLR[d.ring]||CLR.r3)
    .attr('stroke', d => d3.color(CLR[d.ring]||CLR.r3).brighter(.7))
    .attr('fill-opacity', .88);

  // Label: tampil untuk center + node degree tinggi
  nodeG.append('text')
    .attr('class', d => 'node-label' + (d.ring==='center'||d.degree>3?' vis':''))
    .attr('x', d => nsize(d.citations)+3)
    .attr('y', 0)
    .text(d => (d.short||'').substring(0,26)+(d.short&&d.short.length>26?'…':''));

  sim.on('tick', () => {{
    link
      .attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
      .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
    nodeG.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  }});

  // Stats
  const rings = {{}};
  nodes.forEach(n => rings[n.ring]=(rings[n.ring]||0)+1);
  document.getElementById('s-nodes').textContent = nodes.length;
  document.getElementById('s-edges').textContent = edges.length;
  document.getElementById('s-cites').textContent = (nmap[centerNodeId]?.citations||0).toLocaleString();
  document.getElementById('tag-r1').textContent  = `${{rings.r1||0}} Leluhur`;
  document.getElementById('tag-r2').textContent  = `${{rings.r2||0}} Penerus`;
  document.getElementById('tag-r3').textContent  = `${{rings.r3||0}} Tetangga`;

  return {{nodes, edges, nmap, link, nodeG, sim}};
}}

/* ── TOOLTIP ── */
function showTooltip(ev, d) {{
  const tt = document.getElementById('tooltip');
  document.getElementById('tt-title').textContent = d.title;
  document.getElementById('tt-info').textContent  =
    `${{RNAME[d.ring]||d.ring}}  ·  ${{d.year}}  ·  ↑ ${{(d.citations||0).toLocaleString()}} sitasi`;
  const wrap = document.getElementById('graph-wrap').getBoundingClientRect();
  let x = ev.clientX - wrap.left + 14;
  let y = ev.clientY - wrap.top  - 10;
  if (x + 230 > wrap.width)  x = ev.clientX - wrap.left - 230;
  if (y + 75  > wrap.height) y = ev.clientY - wrap.top  - 75;
  tt.style.cssText = `display:block;left:${{Math.max(4,x)}}px;top:${{Math.max(4,y)}}px`;
}}

/* ── NODE CLICK ── */
function onNodeClick(d, link, nodeG) {{
  document.getElementById('tooltip').style.display = 'none';
  selectedId = d.id;

  // Koneksi langsung
  const connected = new Set([d.id]);
  (G?.edges||[]).forEach(e => {{
    const s = typeof e.source==='object'?e.source.id:e.source;
    const t = typeof e.target==='object'?e.target.id:e.target;
    if(s===d.id) connected.add(t);
    if(t===d.id) connected.add(s);
  }});

  nodeG.select('circle')
    .classed('faded', n => !connected.has(n.id))
    .classed('lit',   n => n.id===d.id);
  link.classed('faded', e => {{
    const s=typeof e.source==='object'?e.source.id:e.source;
    const t=typeof e.target==='object'?e.target.id:e.target;
    return !(s===d.id||t===d.id);
  }}).classed('lit', e => {{
    const s=typeof e.source==='object'?e.source.id:e.source;
    const t=typeof e.target==='object'?e.target.id:e.target;
    return s===d.id||t===d.id;
  }});

  // Panel
  document.getElementById('panel-title').textContent = d.title;
  document.getElementById('panel-empty').style.display  = 'none';
  document.getElementById('panel-detail').style.display = 'block';

  const rc = CLR[d.ring]||CLR.r3;
  document.getElementById('panel-rows').innerHTML = `
    <div class="info-row">
      <span class="info-label">Ring</span>
      <span class="info-val" style="color:${{rc}}">${{esc(RNAME[d.ring]||d.ring)}}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Tahun</span>
      <span class="info-val">${{esc(d.year)}}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Sitasi</span>
      <span class="info-val" style="color:#ffd700">${{(d.citations||0).toLocaleString()}}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Koneksi</span>
      <span class="info-val">${{connected.size-1}} paper</span>
    </div>
    <div class="info-row">
      <span class="info-label">Venue</span>
      <span class="info-val" style="font-size:9px">${{esc((d.venue||'—').substring(0,32))}}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Author</span>
      <span class="info-val" style="font-size:9px">${{esc((d.authors||'—').split(',').slice(0,2).join(', ').substring(0,35))}}</span>
    </div>
  `;
  document.getElementById('panel-abstract').textContent = d.abstract||'';
  const linkEl = document.getElementById('panel-open');
  linkEl.href = d.link||'#';
  linkEl.style.display = d.link ? 'block' : 'none';
}}

/* ── CLEAR ── */
function clearSelection() {{
  selectedId = null;
  if (!G) return;
  G.nodeG.select('circle').classed('faded',false).classed('lit',false);
  G.link.classed('faded',false).classed('lit',false);
  document.getElementById('panel-title').textContent    = 'Klik node untuk detail';
  document.getElementById('panel-title').style.color    = '#484f58';
  document.getElementById('panel-empty').style.display  = 'block';
  document.getElementById('panel-detail').style.display = 'none';
}}
svg.on('click', clearSelection);

/* ── RECENTER ── */
function recenterNode() {{
  if (!selectedId || selectedId===centerNodeId) return;
  centerNodeId = selectedId;
  clearSelection();

  // Reassign rings dari sisi edge
  const nmap = Object.fromEntries(RAW.nodes.map(n=>[n.id,n]));
  const toC  = new Set(), fromC = new Set();
  RAW.edges.forEach(e => {{
    if(e.source===centerNodeId) fromC.add(e.target);
    if(e.target===centerNodeId) toC.add(e.source);
  }});
  RAW.nodes.forEach(n => {{
    if(n.id===centerNodeId)    n.ring='center';
    else if(toC.has(n.id))     n.ring='r1';
    else if(fromC.has(n.id))   n.ring='r2';
    else                       n.ring='r3';
  }});

  G = buildGraph(RAW);
  setTimeout(zoomReset, 120);
}}

/* ── SEARCH ── */
function onSearch(q) {{
  if (!G) return;
  const term = q.trim().toLowerCase();
  if (!term) {{
    G.nodeG.select('circle').classed('faded',false).classed('lit',false);
    G.link.classed('faded',false);
    return;
  }}
  const hit = new Set(G.nodes.filter(n=>(n.title||'').toLowerCase().includes(term)).map(n=>n.id));
  G.nodeG.select('circle')
    .classed('faded', n => hit.size>0 && !hit.has(n.id))
    .classed('lit',   n => hit.has(n.id));
  G.link.classed('faded', e=>{{
    const s=typeof e.source==='object'?e.source.id:e.source;
    const t=typeof e.target==='object'?e.target.id:e.target;
    return hit.size>0 && !hit.has(s) && !hit.has(t);
  }});
}}

/* ── RESIZE ── */
window.addEventListener('resize', () => {{
  if (G?.sim) {{
    G.sim.force('center', d3.forceCenter(W()/2, H()/2).strength(.05));
    G.sim.alpha(.12).restart();
  }}
}});

/* ── START ── */
G = buildGraph(RAW);
setTimeout(zoomReset, 80);
</script>
</body>
</html>"""
