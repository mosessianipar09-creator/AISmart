"""
graph_influence.py  —  v4 CANVAS
==================================
Full Canvas 2D — zero SVG DOM overhead.

Perubahan v4:
  ✅ Canvas 2D murni — 100 node tetap smooth
  ✅ Zoom + Pan ringan (matrix transform, bukan DOM reflow)
  ✅ Node tidak pernah overlap — angular spacing + auto split ring
  ✅ Label HANYA muncul saat hover / focus (tidak render semua sekaligus)
  ✅ Klik node → focus mode (dimmed yang tidak berkaitan)
  ✅ Partikel ringan max 40
  ✅ Font JetBrains Mono + Sora

Interface publik tidak berubah:
  render_influence(papers, height)   -> str HTML
  influence_stats(papers, center_id) -> dict
  build_influence_data(papers)       -> dict
"""

from __future__ import annotations
import math, json
import streamlit as st
from data_layer import _raw_get

_R3_MIN_CITATIONS = 30


# ─────────────────────────────────────────────────────
# 1. FETCH
# ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_influence_refs(paper_id: str) -> dict:
    if not paper_id or paper_id.startswith("p"):
        return {"references": [], "citations": []}
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    params = {"fields": (
        "references.paperId,references.title,references.year,references.citationCount,"
        "citations.paperId,citations.title,citations.year,citations.citationCount"
    )}
    try:
        data = _raw_get(url, params)
        return {"references": data.get("references", []), "citations": data.get("citations", [])}
    except Exception as e:
        import sys; print(f"[graph_influence] {paper_id}: {e}", file=sys.stderr)
        return {"references": [], "citations": []}


def _extract_pid(p):
    link = p.get("link", "")
    if "semanticscholar.org/paper/" in link:
        return link.split("/paper/")[-1].strip("/")
    return ""


# ─────────────────────────────────────────────────────
# 2. DATA
# ─────────────────────────────────────────────────────

def _safe_int(v, d=0):
    try: return max(0, int(str(v).replace(",", "").strip()))
    except: return d

def _safe_authors(v):
    if v is None: return "N/A"
    if isinstance(v, (list, tuple)): v = ", ".join(str(x).strip() for x in v if x)
    return str(v).strip() or "N/A"

def _norm(p, i):
    pid = _extract_pid(p) or f"p{i}_{p.get('title','x')[:18].replace(' ','_')}"
    title = (p.get("title","") or "Untitled").strip()
    abstract = (p.get("abstract","") or "Abstrak tidak tersedia.").strip()
    try:
        year = int(str(p.get("year","")).strip())
        if not (1900 < year <= 2030): year = 2020
    except: year = 2020
    return {
        "id": pid,
        "title": title,
        "title_short": (title[:52]+"...") if len(title) > 52 else title,
        "authors": _safe_authors(p.get("authors")),
        "year": year,
        "citations": _safe_int(p.get("citations", 0)),
        "venue": (p.get("venue","") or "Unknown").strip() or "Unknown",
        "abstract": (abstract[:220]+"...") if len(abstract) > 220 else abstract,
        "link": p.get("link",""),
        "source": p.get("source","unknown"),
        "is_main": True,
    }

def _build_config(center_id, pmap, refs_cache):
    center = pmap[center_id]
    rd = refs_cache.get(center_id, {"references":[],"citations":[]})
    ref_ids  = {r.get("paperId") for r in rd.get("references",[]) if r.get("paperId")}
    cite_ids = {c.get("paperId") for c in rd.get("citations",[])  if c.get("paperId")}

    ring1, ring2 = [], []
    for pid, p in pmap.items():
        if pid == center_id: continue
        if   pid in ref_ids:                         ring1.append(pid)
        elif pid in cite_ids:                        ring2.append(pid)
        elif p["year"] < center["year"]:             ring1.append(pid)
        elif p["year"] > center["year"]:             ring2.append(pid)
        elif p["citations"] >= center["citations"]:  ring1.append(pid)
        else:                                        ring2.append(pid)

    ring3_extra = []
    seen = set(pmap) | {center_id}
    api_nodes = rd.get("references",[]) + rd.get("citations",[])
    added = set()
    for nd in sorted(api_nodes, key=lambda x: x.get("citationCount",0), reverse=True)[:8]:
        nid = nd.get("paperId",""); ntit = (nd.get("title","") or "").strip()
        if nid and nid not in seen and nid not in added and ntit:
            nc = nd.get("citationCount",0) or 0
            if nc > _R3_MIN_CITATIONS:
                ring3_extra.append({
                    "id": nid, "title": ntit,
                    "title_short": (ntit[:42]+"...") if len(ntit) > 42 else ntit,
                    "authors": "-", "year": nd.get("year","?") or "?",
                    "citations": nc, "venue": "External",
                    "abstract": "Paper tetangga dari jaringan sitasi.",
                    "link": f"https://www.semanticscholar.org/paper/{nid}",
                    "source": "neighbor", "is_main": False,
                })
                added.add(nid)
                if len(added) >= 6: break

    edges = []
    for pid in ring1:
        w = math.log(pmap[pid]["citations"]+1)/3
        edges.append({"src":pid,"dst":center_id,"type":"r1","weight":round(max(0.5,w),3)})
    for pid in ring2:
        w = math.log(pmap[pid]["citations"]+1)/3
        edges.append({"src":center_id,"dst":pid,"type":"r2","weight":round(max(0.5,w),3)})
    for nd in ring3_extra:
        nid = nd["id"]; w = math.log(nd["citations"]+1)/5
        yr = nd["year"] if isinstance(nd["year"],int) else 0
        if yr and yr < center["year"]:
            edges.append({"src":nid,"dst":center_id,"type":"r3","weight":round(max(0.3,w),3)})
        else:
            edges.append({"src":center_id,"dst":nid,"type":"r3","weight":round(max(0.3,w),3)})

    return {
        "ring1": ring1, "ring2": ring2, "ring3_extra": ring3_extra, "edges": edges,
        "stats": {
            "ancestors": len(ring1), "descendants": len(ring2),
            "extra_neighbors": len(ring3_extra),
            "center_citations": center["citations"], "center_year": center["year"],
        }
    }

@st.cache_data(ttl=3600, show_spinner=False)
def build_influence_data(papers):
    if not papers:
        return {"papers":[],"configs":{},"default_center":"","year_range":[2015,2025]}
    norm = [_norm(p,i) for i,p in enumerate(papers)]
    pmap = {}
    for p in norm:
        pid = p["id"]
        if pid in pmap:
            p = dict(p); p["id"] = f"{pid}_dup{sum(1 for k in pmap if k.startswith(pid))}"
        pmap[p["id"]] = p
    refs_cache = {p["id"]: fetch_influence_refs(p["id"]) for p in norm}
    configs = {pid: _build_config(pid, pmap, refs_cache) for pid in pmap}
    default_center = max(pmap, key=lambda k: pmap[k]["citations"])
    years = [p["year"] for p in norm]
    return {
        "papers": norm, "configs": configs,
        "default_center": default_center,
        "year_range": [min(years, default=2015), max(years, default=2025)],
    }


# ─────────────────────────────────────────────────────
# 3. STATS
# ─────────────────────────────────────────────────────

def influence_stats(papers, center_id=None):
    if not papers: return {}
    data = build_influence_data(papers)
    if not data["papers"]: return {}
    cid  = center_id or data["default_center"]
    pmap = {p["id"]:p for p in data["papers"]}
    cfg  = data["configs"].get(cid, {})
    c    = pmap.get(cid, {})
    r3   = cfg.get("ring3_extra", [])
    return {
        "total_papers":     len(data["papers"]),
        "total_nodes":      len(data["papers"]) + len(r3),
        "center_title":     c.get("title_short", "-"),
        "center_citations": c.get("citations", 0),
        "ancestor_count":   cfg.get("stats",{}).get("ancestors", 0),
        "descendant_count": cfg.get("stats",{}).get("descendants", 0),
        "neighbor_count":   cfg.get("stats",{}).get("extra_neighbors", 0),
        "influence_reach":  (cfg.get("stats",{}).get("ancestors", 0) +
                             cfg.get("stats",{}).get("descendants", 0) +
                             cfg.get("stats",{}).get("extra_neighbors", 0)),
    }


# ─────────────────────────────────────────────────────
# 4. RENDER — CANVAS PURE v4
# ─────────────────────────────────────────────────────

def render_influence(papers, height=700):
    data      = build_influence_data(papers)
    _raw      = json.dumps(data, ensure_ascii=False).replace('\x3c/', r'\<\/')
    data_json = json.dumps(_raw)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title>Influence Map v4</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&family=Sora:wght@300;400;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:100%;height:{height}px;overflow:hidden;
  background:#030a14;font-family:'Sora',sans-serif;user-select:none;}}
:root{{
  --bg:#030a14;--panel:rgba(4,11,26,.97);
  --b0:rgba(56,189,248,.10);--b1:rgba(56,189,248,.35);
  --center:#fbbf24;--r1:#38bdf8;--r2:#34d399;--r3:#94a3b8;
  --hi:#e8f4ff;--mid:#7aa8cc;--lo:#2a4460;
  --mono:'JetBrains Mono',monospace;--body:'Sora',sans-serif;
}}
#wrap{{position:relative;width:100%;height:{height}px;overflow:hidden;}}
#cv{{position:absolute;inset:0;cursor:grab;display:block;width:100%;height:100%;}}
#cv.drag{{cursor:grabbing;}}

/* top bar */
#bar{{
  position:absolute;top:0;left:0;right:0;z-index:10;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding:6px 12px;
  background:linear-gradient(180deg,rgba(3,10,20,.97) 55%,transparent);
  border-bottom:1px solid rgba(56,189,248,.05);
}}
.b-tag{{font-family:var(--mono);font-size:7px;letter-spacing:3px;
  color:rgba(56,189,248,.3);text-transform:uppercase;white-space:nowrap;}}
.b-sep{{width:1px;height:16px;background:var(--b0);}}
.b-btn{{font-family:var(--mono);font-size:8px;letter-spacing:.5px;
  color:var(--mid);border:1px solid var(--b0);background:transparent;
  border-radius:3px;padding:3px 9px;cursor:pointer;transition:all .14s;}}
.b-btn:hover{{color:var(--hi);border-color:var(--b1);}}
.b-btn.on{{border-color:rgba(251,191,36,.45);color:#fbbf24;background:rgba(251,191,36,.06);}}
.b-btn.on-b{{border-color:rgba(56,189,248,.45);color:#38bdf8;background:rgba(56,189,248,.06);}}
#zoom-txt{{font-family:var(--mono);font-size:7.5px;color:rgba(56,189,248,.35);
  border:1px solid rgba(56,189,248,.08);border-radius:2px;padding:2px 7px;}}
#sel-wrap{{margin-left:auto;display:flex;align-items:center;gap:6px;}}
.b-lbl{{font-family:var(--mono);font-size:7px;color:var(--lo);}}
#psel{{
  background:rgba(4,11,26,.96);border:1px solid var(--b0);border-radius:3px;
  color:#38bdf8;padding:3px 20px 3px 8px;font-family:var(--mono);font-size:8px;
  cursor:pointer;appearance:none;outline:none;max-width:190px;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='4'%3E%3Cpath d='M0 0l4 4 4-4z' fill='%2338bdf8'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 6px center;
}}
#psel option{{background:#040b1a;}}

/* focus reset */
#btn-cf{{
  position:absolute;top:38px;left:12px;z-index:10;display:none;
  font-family:var(--mono);font-size:7.5px;letter-spacing:.8px;color:#fbbf24;
  border:1px solid rgba(251,191,36,.3);background:rgba(251,191,36,.07);
  border-radius:3px;padding:4px 10px;cursor:pointer;transition:all .14s;
}}
#btn-cf.show{{display:block;}}
#btn-cf:hover{{background:rgba(251,191,36,.16);}}

/* tooltip */
#tt{{
  position:absolute;display:none;pointer-events:none;z-index:50;
  background:rgba(3,9,22,.97);border:1px solid rgba(56,189,248,.2);
  border-radius:7px;padding:11px 13px;max-width:255px;min-width:175px;
  box-shadow:0 12px 40px rgba(0,0,0,.8);backdrop-filter:blur(16px);
}}
.tt-h{{font-family:var(--body);font-size:10.5px;font-weight:700;
  color:var(--hi);margin-bottom:4px;line-height:1.4;}}
.tt-m{{font-family:var(--mono);font-size:7px;color:var(--mid);margin-bottom:1px;}}
.tt-ring{{display:inline-flex;align-items:center;gap:4px;
  margin:4px 0 5px;padding:2px 7px;border-radius:2px;
  font-family:var(--mono);font-size:7px;letter-spacing:1px;
  text-transform:uppercase;border:1px solid currentColor;}}
.tt-ab{{font-family:var(--body);font-size:8.5px;color:var(--mid);
  line-height:1.5;border-top:1px solid var(--b0);padding-top:4px;margin-top:3px;}}
.tt-hint{{font-family:var(--mono);font-size:7px;color:#fbbf24;margin-top:4px;}}

/* detail panel */
#dp{{
  position:absolute;right:12px;top:42px;width:222px;
  background:var(--panel);border:1px solid rgba(56,189,248,.16);
  border-radius:8px;padding:13px;z-index:20;display:none;
  box-shadow:0 14px 42px rgba(0,0,0,.7);backdrop-filter:blur(18px);
  animation:dpin .18s ease;
}}
@keyframes dpin{{from{{opacity:0;transform:translateX(10px)}}to{{opacity:1;transform:none}}}}
#dp.show{{display:block;}}
.dp-x{{position:absolute;top:9px;right:10px;cursor:pointer;
  color:var(--lo);font-size:13px;transition:color .14s;}}
.dp-x:hover{{color:var(--hi);}}
.dp-ttl{{font-family:var(--body);font-size:10px;font-weight:700;
  color:var(--hi);line-height:1.4;margin-bottom:9px;padding-right:12px;}}
.dp-row{{display:flex;justify-content:space-between;align-items:center;
  padding:3px 0;border-bottom:1px solid rgba(56,189,248,.05);}}
.dp-k{{font-family:var(--mono);font-size:6.5px;color:var(--lo);
  letter-spacing:.8px;text-transform:uppercase;}}
.dp-v{{font-family:var(--mono);font-size:8.5px;color:#38bdf8;font-weight:500;}}
.dp-ab{{font-family:var(--body);font-size:8px;color:var(--mid);
  line-height:1.55;margin:7px 0;}}
.dp-a{{display:block;width:100%;padding:5px;text-align:center;
  background:rgba(56,189,248,.05);border:1px solid rgba(56,189,248,.18);
  border-radius:3px;color:#38bdf8;text-decoration:none;
  font-family:var(--mono);font-size:7px;letter-spacing:1.2px;
  text-transform:uppercase;transition:all .14s;margin-bottom:4px;}}
.dp-a:hover{{background:rgba(56,189,248,.14);}}
.dp-rc{{display:block;width:100%;padding:5px;text-align:center;
  background:rgba(251,191,36,.05);border:1px solid rgba(251,191,36,.18);
  border-radius:3px;color:#fbbf24;cursor:pointer;
  font-family:var(--mono);font-size:7px;letter-spacing:1.2px;
  text-transform:uppercase;transition:all .14s;}}
.dp-rc:hover{{background:rgba(251,191,36,.14);}}

/* stats */
#sp{{
  position:absolute;right:12px;bottom:32px;width:155px;
  background:var(--panel);border:1px solid var(--b0);
  border-radius:7px;padding:10px;z-index:10;
}}
.sp-h{{font-family:var(--mono);font-size:6px;letter-spacing:3px;
  color:var(--lo);text-transform:uppercase;margin-bottom:6px;}}
.sp-r{{display:flex;justify-content:space-between;align-items:center;padding:2px 0;}}
.sp-k{{font-family:var(--mono);font-size:6.5px;color:var(--lo);}}
.sp-v{{font-family:var(--mono);font-size:9px;font-weight:500;}}
.sp-bar{{height:2px;background:rgba(56,189,248,.07);border-radius:1px;margin:3px 0;overflow:hidden;}}
.sp-fill{{height:100%;border-radius:1px;transition:width .5s ease;}}

/* legend */
#leg{{
  position:absolute;bottom:12px;left:12px;
  display:flex;align-items:center;gap:10px;z-index:10;
}}
.lg{{display:flex;align-items:center;gap:4px;
  font-family:var(--mono);font-size:7px;color:var(--lo);}}
.ld{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}

/* hint */
#hint{{
  position:absolute;bottom:48px;left:50%;transform:translateX(-50%);
  font-family:var(--mono);font-size:8px;letter-spacing:.8px;
  color:rgba(56,189,248,.3);pointer-events:none;z-index:5;
  animation:hfade 5s ease forwards;white-space:nowrap;
}}
@keyframes hfade{{0%{{opacity:1}}70%{{opacity:.5}}100%{{opacity:0}}}}
</style>
</head>
<body>
<div id="wrap">
  <canvas id="cv"></canvas>

  <div id="bar">
    <span class="b-tag">Influence Map v4</span>
    <div class="b-sep"></div>
    <button class="b-btn on"   id="btn-pt" onclick="tog('part')">PARTICLES</button>
    <button class="b-btn on-b" id="btn-ob" onclick="tog('orbit')">ORBITS</button>
    <button class="b-btn"      id="btn-ht" onclick="tog('heat')">HEATMAP</button>
    <div class="b-sep"></div>
    <span id="zoom-txt">100%</span>
    <button class="b-btn" onclick="resetView()" title="Reset tampilan">HOME</button>
    <div id="sel-wrap">
      <span class="b-lbl">PUSAT:</span>
      <select id="psel" onchange="reCenter(this.value)"></select>
    </div>
  </div>

  <button id="btn-cf" onclick="clearFocus()">x CLEAR FOCUS</button>
  <div id="tt"></div>

  <div id="dp">
    <span class="dp-x" onclick="closePanel()">x</span>
    <div class="dp-ttl" id="dp-ttl"></div>
    <div id="dp-rows"></div>
    <div class="dp-ab" id="dp-ab"></div>
    <a class="dp-a" id="dp-lnk" href="#" target="_blank">BUKA PAPER</a>
    <div class="dp-rc" onclick="reCenterPanel()">JADIKAN PUSAT</div>
  </div>

  <div id="sp">
    <div class="sp-h">Network Stats</div>
    <div id="sp-body"></div>
  </div>

  <div id="leg">
    <span class="lg"><span class="ld" style="background:#fbbf24"></span>PUSAT</span>
    <span class="lg"><span class="ld" style="background:#38bdf8"></span>LELUHUR</span>
    <span class="lg"><span class="ld" style="background:#34d399"></span>PENERUS</span>
    <span class="lg"><span class="ld" style="background:#94a3b8"></span>TETANGGA</span>
  </div>

  <div id="hint">Scroll=Zoom  Drag=Pan  Klik Node=Fokus</div>
</div>

<script>
const D = JSON.parse({data_json});

function esc(s){{
  return String(s==null?'':s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

const S = {{
  center: D.default_center,
  zoom:1, panX:0, panY:0,
  drag:false, dsx:0, dsy:0, dpx:0, dpy:0,
  showPart:true, showOrbit:true, heat:false,
  focusId:null, hoverId:null,
  transitioning:false, fadeOut:0,
  positions:{{}}, pmap:{{}},
}};

const RC = {{center:'#fbbf24',r1:'#38bdf8',r2:'#34d399',r3:'#94a3b8'}};
const RN = {{center:'PUSAT',r1:'LELUHUR',r2:'PENERUS',r3:'TETANGGA'}};

function rClr(ring){{
  if(S.heat) return ({{center:'#fff',r1:'#ef4444',r2:'#f97316',r3:'#3b82f6'}})[ring]||'#94a3b8';
  return RC[ring]||RC.r3;
}}

function nSz(cites,isCenter){{
  const b=Math.max(12,Math.min(38,Math.log((cites||0)+1)*4.8));
  return isCenter?b*1.35:b;
}}

const cv=document.getElementById('cv');
const ctx=cv.getContext('2d');
function W(){{return cv.width;}} function H(){{return cv.height;}}
function resize(){{cv.width=cv.offsetWidth||800;cv.height=cv.offsetHeight||600;}}

function w2s(wx,wy){{return [wx*S.zoom+S.panX, wy*S.zoom+S.panY];}}
function s2w(sx,sy){{return [(sx-S.panX)/S.zoom, (sy-S.panY)/S.zoom];}}

function computePositions(){{
  const cfg=D.configs[S.center]; if(!cfg) return;
  const cx=W()/2, cy=H()/2;
  const m=Math.min(W(),H());
  const R1=m*.21, R2=m*.38, R3=m*.55;
  const pos={{}};
  pos[S.center]={{x:cx,y:cy,ring:'center',r:0}};

  function place(ids,baseR,ring){{
    const n=ids.length; if(!n) return;
    if(n>14){{
      const h1=ids.slice(0,Math.ceil(n/2)), h2=ids.slice(Math.ceil(n/2));
      const ri=baseR*.86, ro=baseR*1.14;
      h1.forEach((id,i)=>{{const a=-Math.PI/2+(2*Math.PI*i)/h1.length; pos[id]={{x:cx+ri*Math.cos(a),y:cy+ri*Math.sin(a),ring,r:ri}};}});
      h2.forEach((id,i)=>{{const a=-Math.PI/2+Math.PI/h2.length+(2*Math.PI*i)/h2.length; pos[id]={{x:cx+ro*Math.cos(a),y:cy+ro*Math.sin(a),ring,r:ro}};}});
    }} else {{
      ids.forEach((id,i)=>{{const a=-Math.PI/2+(2*Math.PI*i)/n; pos[id]={{x:cx+baseR*Math.cos(a),y:cy+baseR*Math.sin(a),ring,r:baseR}};}});
    }}
  }}
  place(cfg.ring1,R1,'r1');
  place(cfg.ring2,R2,'r2');
  place((cfg.ring3_extra||[]).map(n=>n.id),R3,'r3');
  S.positions=pos;
  S.pmap={{}};
  D.papers.forEach(p=>S.pmap[p.id]=p);
  (cfg.ring3_extra||[]).forEach(n=>S.pmap[n.id]=n);
}}

function hitTest(sx,sy){{
  const [wx,wy]=s2w(sx,sy);
  let best=null,bestD=9999;
  for(const [id,p] of Object.entries(S.positions)){{
    const nd=S.pmap[id]; if(!nd) continue;
    const sz=nSz(nd.citations,id===S.center);
    const dx=wx-p.x,dy=wy-p.y,d=Math.sqrt(dx*dx+dy*dy);
    if(d<=sz+5&&d<bestD){{bestD=d;best=id;}}
  }}
  return best;
}}

function isDimmed(id){{
  if(!S.focusId) return false;
  if(id===S.focusId||id===S.center) return false;
  const cfg=D.configs[S.center]; if(!cfg) return false;
  for(const e of cfg.edges){{
    if((e.src===S.focusId&&e.dst===id)||(e.dst===S.focusId&&e.src===id)) return false;
  }}
  return true;
}}

function applyFocus(id){{S.focusId=id;document.getElementById('btn-cf').classList.add('show');}}
function clearFocus(){{S.focusId=null;document.getElementById('btn-cf').classList.remove('show');closePanel();}}

let _panelId=null;
function openPanel(id){{
  _panelId=id;
  const nd=S.pmap[id]; if(!nd) return;
  const ring=S.positions[id]?.ring||'r3';
  const rc=RC[ring]||RC.r3;
  document.getElementById('dp-ttl').textContent=nd.title;
  document.getElementById('dp-ab').textContent=nd.abstract;
  document.getElementById('dp-lnk').href=nd.link||'#';
  document.getElementById('dp-rows').innerHTML=
    `<div class="dp-row"><span class="dp-k">TAHUN</span><span class="dp-v">${{nd.year}}</span></div>`+
    `<div class="dp-row"><span class="dp-k">SITASI</span><span class="dp-v" style="color:#fbbf24">${{(nd.citations||0).toLocaleString()}}</span></div>`+
    `<div class="dp-row"><span class="dp-k">RING</span><span class="dp-v" style="color:${{rc}}">${{RN[ring]||ring}}</span></div>`+
    `<div class="dp-row"><span class="dp-k">VENUE</span><span class="dp-v" style="font-size:7.5px">${{esc((nd.venue||'-').substring(0,24))}}</span></div>`;
  document.getElementById('dp').classList.add('show');
}}
function closePanel(){{document.getElementById('dp').classList.remove('show');}}
function reCenterPanel(){{if(_panelId){{closePanel();clearFocus();reCenter(_panelId);}}}}

function reCenter(newId){{
  if(S.transitioning||newId===S.center||!D.configs[newId]) return;
  S.transitioning=true; S.fadeOut=1.0;
  setTimeout(()=>{{
    S.center=newId; S.focusId=null;
    document.getElementById('psel').value=newId;
    document.getElementById('btn-cf').classList.remove('show');
    closePanel(); computePositions(); updateStats();
    S.fadeOut=0; setTimeout(()=>S.transitioning=false,300);
  }},220);
}}

function tog(k){{
  const km={{part:'showPart',orbit:'showOrbit',heat:'heat'}};
  const bm={{part:'btn-pt',orbit:'btn-ob',heat:'btn-ht'}};
  const cm={{part:'on',orbit:'on-b',heat:'on-b'}};
  S[km[k]]=!S[km[k]];
  const b=document.getElementById(bm[k]);
  b.className='b-btn'+(S[km[k]]?' '+cm[k]:'');
}}

function resetView(){{
  S.zoom=1;S.panX=0;S.panY=0;
  document.getElementById('zoom-txt').textContent='100%';
}}

function updateStats(){{
  const cfg=D.configs[S.center]||{{}};
  const st=cfg.stats||{{}};
  const c=S.pmap[S.center]||{{}};
  const maxC=Math.max(...D.papers.map(p=>p.citations),1);
  const pct=Math.min(100,Math.round((c.citations||0)/maxC*100));
  document.getElementById('sp-body').innerHTML=
    `<div style="font-family:'JetBrains Mono',monospace;font-size:8px;color:#38bdf8;padding:0 0 5px;line-height:1.4">${{esc((c.title_short||'').substring(0,44))}}</div>`+
    `<div class="sp-r"><span class="sp-k">Sitasi</span><span class="sp-v" style="color:#fbbf24">${{(c.citations||0).toLocaleString()}}</span></div>`+
    `<div class="sp-bar"><div class="sp-fill" style="width:${{pct}}%;background:#fbbf24"></div></div>`+
    `<div class="sp-r"><span class="sp-k">Leluhur</span><span class="sp-v" style="color:#38bdf8">${{st.ancestors||0}}</span></div>`+
    `<div class="sp-r"><span class="sp-k">Penerus</span><span class="sp-v" style="color:#34d399">${{st.descendants||0}}</span></div>`+
    `<div class="sp-r"><span class="sp-k">Tetangga</span><span class="sp-v" style="color:#94a3b8">${{st.extra_neighbors||0}}</span></div>`+
    `<div class="sp-r"><span class="sp-k">Tahun</span><span class="sp-v">${{c.year||'?'}}</span></div>`;
}}

function showTT(sx,sy,id){{
  const nd=S.pmap[id]; if(!nd) return;
  const ring=S.positions[id]?.ring||'r3';
  const rc=RC[ring]||RC.r3;
  const tt=document.getElementById('tt');
  tt.innerHTML=
    `<div class="tt-h">${{esc(nd.title)}}</div>`+
    `<div class="tt-m">👤 ${{esc((nd.authors||'').split(',').slice(0,2).join(', '))}}</div>`+
    `<div class="tt-m">📅 ${{nd.year}} · ${{(nd.citations||0).toLocaleString()}} sitasi</div>`+
    `<div class="tt-m">🏛 ${{esc(nd.venue||'-')}}</div>`+
    `<span class="tt-ring" style="color:${{rc}};border-color:${{rc}}">${{RN[ring]||ring}}</span>`+
    `<div class="tt-ab">${{esc(nd.abstract)}}</div>`+
    (id!==S.center?`<div class="tt-hint">Klik untuk detail</div>`:'<div class="tt-hint">Paper pusat aktif</div>');
  let tx=sx+14,ty=sy-10;
  if(tx+262>W()) tx=sx-262;
  if(ty+265>H()) ty=sy-265;
  tt.style.cssText=`display:block;left:${{tx}}px;top:${{ty}}px`;
}}
function hideTT(){{document.getElementById('tt').style.display='none';}}

/* particles */
const PT=[];
const PT_MAX=40;
let ptick=0;
function spawnPt(ax,ay,bx,by,ring){{
  if(PT.length>=PT_MAX) return;
  const clr=ring==='r1'?'#38bdf8':ring==='r2'?'#34d399':'#94a3b8';
  PT.push({{ax,ay,bx,by,t:Math.random(),spd:.009+Math.random()*.007,r:1.3+Math.random()*1.2,clr,trail:[]}});
}}
function lerp(a,b,t){{return a+(b-a)*t;}}
function updatePT(){{
  for(let i=PT.length-1;i>=0;i--){{
    const p=PT[i];
    p.trail.push({{x:lerp(p.ax,p.bx,p.t),y:lerp(p.ay,p.by,p.t)}});
    if(p.trail.length>5) p.trail.shift();
    p.t+=p.spd;
    if(p.t>1) PT.splice(i,1);
  }}
}}
function spawnFromEdges(){{
  ptick++;
  if(ptick%10!==0||!S.showPart) return;
  const cfg=D.configs[S.center]; if(!cfg) return;
  const edges=cfg.edges; if(!edges.length) return;
  const e=edges[Math.floor(Math.random()*edges.length)];
  const a=S.positions[e.src],b=S.positions[e.dst];
  if(a&&b) spawnPt(a.x,a.y,b.x,b.y,e.type);
}}

/* roundRect polyfill */
function rRect(c,x,y,w,h,r){{
  c.beginPath();c.moveTo(x+r,y);c.lineTo(x+w-r,y);
  c.quadraticCurveTo(x+w,y,x+w,y+r);c.lineTo(x+w,y+h-r);
  c.quadraticCurveTo(x+w,y+h,x+w-r,y+h);c.lineTo(x+r,y+h);
  c.quadraticCurveTo(x,y+h,x,y+h-r);c.lineTo(x,y+r);
  c.quadraticCurveTo(x,y,x+r,y);c.closePath();
}}

/* main draw */
function draw(){{
  ctx.clearRect(0,0,W(),H());

  /* nebula bg */
  const cp=S.positions[S.center];
  if(cp){{
    const [sx,sy]=w2s(cp.x,cp.y);
    const grd=ctx.createRadialGradient(sx,sy,0,sx,sy,Math.min(W(),H())*.38);
    grd.addColorStop(0,'rgba(251,191,36,.08)');
    grd.addColorStop(.4,'rgba(56,189,248,.04)');
    grd.addColorStop(1,'rgba(0,0,0,0)');
    ctx.fillStyle=grd; ctx.fillRect(0,0,W(),H());
  }}

  ctx.save();
  ctx.translate(S.panX,S.panY);
  ctx.scale(S.zoom,S.zoom);
  if(S.fadeOut>0) ctx.globalAlpha=Math.max(0,1-S.fadeOut);

  /* orbits */
  if(S.showOrbit&&cp){{
    const cfg=D.configs[S.center];
    const m=Math.min(W(),H());
    const Rs=[m*.21,m*.38,m*.55];
    const Cs=['rgba(56,189,248,.13)','rgba(52,211,153,.10)','rgba(148,163,184,.07)'];
    const Ns=[cfg?.ring1?.length||0, cfg?.ring2?.length||0, 99];
    Rs.forEach((R,ri)=>{{
      ctx.setLineDash([4,10]);
      if(Ns[ri]>14&&ri<2){{
        [R*.86,R*1.14].forEach(r=>{{
          ctx.beginPath();ctx.arc(cp.x,cp.y,r,0,Math.PI*2);
          ctx.strokeStyle=Cs[ri];ctx.lineWidth=.9;ctx.stroke();
        }});
      }} else {{
        ctx.beginPath();ctx.arc(cp.x,cp.y,R,0,Math.PI*2);
        ctx.strokeStyle=Cs[ri];ctx.lineWidth=ri===0?1.2:ri===1?1:.7;ctx.stroke();
      }}
      ctx.setLineDash([]);
    }});
  }}

  /* edges */
  const cfg=D.configs[S.center];
  if(cfg){{
    cfg.edges.forEach(e=>{{
      const a=S.positions[e.src],b=S.positions[e.dst]; if(!a||!b) return;
      const dim=isDimmed(e.src)||isDimmed(e.dst);
      const baseAlpha=dim?.018:.26;
      const clr=e.type==='r1'?`rgba(56,189,248,${{baseAlpha}})`:
                e.type==='r2'?`rgba(52,211,153,${{baseAlpha}})`:`rgba(148,163,184,${{baseAlpha}})`;
      const dx=b.x-a.x,dy=b.y-a.y,dist=Math.sqrt(dx*dx+dy*dy)||1;
      const cv2=dist*.10;
      const mx=(a.x+b.x)/2-dy*cv2/dist,my=(a.y+b.y)/2+dx*cv2/dist;
      ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.quadraticCurveTo(mx,my,b.x,b.y);
      ctx.strokeStyle=clr;ctx.lineWidth=Math.max(.5,e.weight*1.5);ctx.stroke();
    }});
  }}

  /* particles */
  if(S.showPart){{
    PT.forEach(p=>{{
      const x=lerp(p.ax,p.bx,p.t),y=lerp(p.ay,p.by,p.t);
      if(p.trail.length>1){{
        ctx.beginPath();ctx.moveTo(p.trail[0].x,p.trail[0].y);
        p.trail.forEach(pt=>ctx.lineTo(pt.x,pt.y));
        ctx.strokeStyle=p.clr+'33';ctx.lineWidth=p.r*.42;ctx.stroke();
      }}
      const g=ctx.createRadialGradient(x,y,0,x,y,p.r*2.2);
      g.addColorStop(0,p.clr+'dd');g.addColorStop(1,p.clr+'00');
      ctx.beginPath();ctx.arc(x,y,p.r*2.2,0,Math.PI*2);ctx.fillStyle=g;ctx.fill();
    }});
  }}

  /* nodes */
  for(const [id,p] of Object.entries(S.positions)){{
    const nd=S.pmap[id]; if(!nd) continue;
    const isCenter=(id===S.center);
    const isHover=(id===S.hoverId);
    const dim=isDimmed(id);
    const ring=p.ring;
    const sz=nSz(nd.citations,isCenter);
    const clr=rClr(ring);

    ctx.globalAlpha=dim?.07:1;

    /* glow halo */
    if(!dim){{
      const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,sz+(isCenter?18:11));
      g.addColorStop(0,clr+'20');g.addColorStop(1,clr+'00');
      ctx.beginPath();ctx.arc(p.x,p.y,sz+(isCenter?18:11),0,Math.PI*2);
      ctx.fillStyle=g;ctx.fill();
    }}

    /* pulse ring for center */
    if(isCenter&&!dim){{
      const pt=(Date.now()%2400)/2400;
      const pr=sz+4+pt*sz*.55;
      const pa=.6*(1-pt);
      ctx.beginPath();ctx.arc(p.x,p.y,pr,0,Math.PI*2);
      ctx.strokeStyle=clr+Math.round(pa*255).toString(16).padStart(2,'0');
      ctx.lineWidth=1.3;ctx.stroke();
    }}

    /* hover ring */
    if(isHover&&!dim){{
      ctx.beginPath();ctx.arc(p.x,p.y,sz+5,0,Math.PI*2);
      ctx.strokeStyle=clr+'77';ctx.lineWidth=1.4;ctx.stroke();
    }}

    /* main fill */
    const grad=ctx.createRadialGradient(p.x-sz*.2,p.y-sz*.2,0,p.x,p.y,sz);
    if(ring==='center'){{grad.addColorStop(0,'#fde68a');grad.addColorStop(.6,'#f59e0b');grad.addColorStop(1,'#d97706');}}
    else if(ring==='r1'){{grad.addColorStop(0,'#7dd3fc');grad.addColorStop(1,'#0284c7');}}
    else if(ring==='r2'){{grad.addColorStop(0,'#6ee7b7');grad.addColorStop(1,'#059669');}}
    else{{grad.addColorStop(0,'#cbd5e1');grad.addColorStop(1,'#64748b');}}
    ctx.beginPath();ctx.arc(p.x,p.y,sz,0,Math.PI*2);
    ctx.fillStyle=grad;ctx.fill();
    ctx.strokeStyle=clr;ctx.lineWidth=isCenter?1.8:1.1;ctx.stroke();

    /* inner highlight */
    ctx.beginPath();ctx.arc(p.x-sz*.22,p.y-sz*.24,sz*.23,0,Math.PI*2);
    ctx.fillStyle='rgba(255,255,255,.17)';ctx.fill();

    /* year inside node */
    ctx.globalAlpha=dim?.07:1;
    ctx.font=`500 ${{Math.max(7,Math.floor(sz*.36))}}px 'JetBrains Mono',monospace`;
    ctx.fillStyle=clr;ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText(String(nd.year),p.x,p.y);

    /* smart label — only on hover, focus, or center */
    const showLbl=isCenter||isHover||(S.focusId&&!dim&&id!==S.center);
    if(showLbl&&!dim){{
      const raw=nd.title_short||id.substring(0,22);
      const maxCh=isCenter?46:28;
      const lbl=raw.length>maxCh?raw.substring(0,maxCh)+'...':raw;
      const lblY=p.y+sz+13;

      ctx.font=`${{isCenter?'600 10px':'400 8.5px'}} 'Sora',sans-serif`;
      const tw=ctx.measureText(lbl).width;
      ctx.globalAlpha=.88;
      ctx.fillStyle='rgba(3,9,22,.82)';
      rRect(ctx,p.x-tw/2-6,lblY-2,tw+12,13,3);
      ctx.fill();
      ctx.globalAlpha=1;
      ctx.fillStyle=isCenter?'#e8f4ff':'#b8d4f0';
      ctx.textAlign='center';ctx.textBaseline='hanging';
      ctx.fillText(lbl,p.x,lblY);

      const cstr=`${{(nd.citations||0).toLocaleString()}} sitasi`;
      const cY=lblY+14;
      ctx.font=`300 7.5px 'JetBrains Mono',monospace`;
      const cw=ctx.measureText(cstr).width;
      ctx.globalAlpha=.65;
      ctx.fillStyle='rgba(3,9,22,.7)';
      rRect(ctx,p.x-cw/2-5,cY-1,cw+10,11,2);
      ctx.fill();
      ctx.globalAlpha=.7;
      ctx.fillStyle=clr;
      ctx.fillText(cstr,p.x,cY);
    }}
    ctx.globalAlpha=1;
  }}

  ctx.restore();
}}

function loop(){{
  spawnFromEdges();updatePT();
  if(S.fadeOut>0) S.fadeOut=Math.max(0,S.fadeOut-.06);
  draw();
  requestAnimationFrame(loop);
}}

/* input */
cv.addEventListener('wheel',ev=>{{
  ev.preventDefault();
  const rect=cv.getBoundingClientRect();
  const sx=ev.clientX-rect.left,sy=ev.clientY-rect.top;
  const dir=ev.deltaY<0?1:-1;
  const step=.09*(ev.ctrlKey?2:1);
  const nz=Math.max(.25,Math.min(4,S.zoom+dir*step));
  S.panX=sx-nz/S.zoom*(sx-S.panX);
  S.panY=sy-nz/S.zoom*(sy-S.panY);
  S.zoom=nz;
  document.getElementById('zoom-txt').textContent=Math.round(nz*100)+'%';
}},{{passive:false}});

cv.addEventListener('mousedown',ev=>{{
  if(ev.button!==0) return;
  S.drag=true;S.dsx=ev.clientX;S.dsy=ev.clientY;S.dpx=S.panX;S.dpy=S.panY;
  cv.classList.add('drag');
}});
window.addEventListener('mousemove',ev=>{{
  if(S.drag){{S.panX=S.dpx+(ev.clientX-S.dsx);S.panY=S.dpy+(ev.clientY-S.dsy);}}
  const rect=cv.getBoundingClientRect();
  const sx=ev.clientX-rect.left,sy=ev.clientY-rect.top;
  const hit=hitTest(sx,sy);
  if(hit!==S.hoverId){{
    S.hoverId=hit;
    if(hit)showTT(sx,sy,hit);else hideTT();
  }} else if(hit){{showTT(sx,sy,hit);}}
}});
window.addEventListener('mouseup',()=>{{S.drag=false;cv.classList.remove('drag');}});

cv.addEventListener('click',ev=>{{
  if(Math.abs(ev.clientX-S.dsx)>5||Math.abs(ev.clientY-S.dsy)>5) return;
  const rect=cv.getBoundingClientRect();
  const hit=hitTest(ev.clientX-rect.left,ev.clientY-rect.top);
  if(!hit){{clearFocus();return;}}
  if(hit===S.center){{clearFocus();return;}}
  applyFocus(hit);openPanel(hit);
}});

function populateSel(){{
  const s=document.getElementById('psel');
  s.innerHTML=D.papers.map(p=>`<option value="${{esc(p.id)}}">${{esc((p.title_short||p.id).substring(0,36))}}</option>`).join('');
  s.value=S.center;
}}

let _rt;
window.addEventListener('resize',()=>{{clearTimeout(_rt);_rt=setTimeout(()=>{{resize();computePositions();}},80);}});

function init(){{
  resize();populateSel();
  S.pmap={{}};D.papers.forEach(p=>S.pmap[p.id]=p);
  computePositions();updateStats();
  requestAnimationFrame(loop);
}}
document.readyState==='loading'
  ?document.addEventListener('DOMContentLoaded',init)
  :setTimeout(init,50);
</script>
</body>
</html>"""
