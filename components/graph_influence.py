"""
graph_influence.py
==================
Influence Map — Fitur 2 dari Research Intelligence Center

Mengubah jaringan sitasi menjadi peta tata surya interaktif:
  Paper pilihan  = matahari (pusat, berwarna emas berpendar)
  Ring 1 (biru)  = paper yang DIKUTIP oleh pusat  → "leluhur intelektual"
  Ring 2 (hijau) = paper yang MENGUTIP pusat      → "keturunan/penerus"
  Ring 3 (abu)   = paper 2 derajat pemisahan      → "jaringan tidak langsung"

Interaksi canggih:
  · Klik node non-pusat  → re-center dengan smooth orbit transition animation
  · Hover node           → tooltip kaya: abstrak, tahun, sitasi, venue, ring position
  · Toggle PARTICLES     → animasi partikel aliran pengaruh (canvas overlay)
  · Toggle ORBITS        → tampilkan/sembunyikan cincin orbit beranimasi
  · Toggle HEATMAP       → warna node berdasarkan jarak & pengaruh dari pusat
  · Mode COMPARE         → split-view dua influence map dengan overlay deteksi node bersama
  · Dropdown selector    → pilih paper pusat dari daftar
  · Panel stats kanan    → statistik jaringan yang update otomatis saat re-center
  · Klik di luar         → tutup detail panel

Arsitektur rendering:
  SVG    = struktur statis (orbit rings, edges, node shapes, labels)
  Canvas = animasi dinamis (particle system — partikel mengalir sepanjang edges)

Fungsi publik:
  render_influence(papers, height)         → str   HTML siap embed di Streamlit
  influence_stats(papers, center_id)       → dict  statistik untuk metric cards Streamlit
  build_influence_data(papers)             → dict  data mentah (berguna untuk testing)

Kontrak interface untuk graph_layer.py:
  from graph_influence import render_influence, influence_stats, build_influence_data
"""

from __future__ import annotations  # PEP 563 — lazy annotations; safe on Python ≥3.7

import math
import json
import streamlit as st
from data_layer import _raw_get

# Threshold sitasi minimum untuk node Ring-3 (tetangga API)
# Naikkan nilainya jika ring-3 terlalu ramai; turunkan untuk lebih inklusif
_R3_MIN_CITATIONS: int = 30


# ─────────────────────────────────────────────────────────────────
# 1. FETCH CITATION NETWORK
# ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_influence_refs(paper_id: str) -> dict:
    """
    Ambil daftar referensi (paper yang dikutip) dan sitasi (paper yang mengutip)
    dari Semantic Scholar untuk satu paper_id.

    Menggunakan cache Streamlit 1 jam — aman dipanggil berulang kali.
    Mengembalikan dict kosong jika paper_id tidak valid atau API gagal.

    Returns:
        {
          "references": [{"paperId": ..., "title": ..., "year": ..., "citationCount": ...}],
          "citations":  [{"paperId": ..., "title": ..., "year": ..., "citationCount": ...}]
        }
    """
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
    except Exception as _exc:                          # FIXED: log error, don't swallow silently
        import sys
        print(f"[graph_influence] fetch_influence_refs({paper_id!r}) failed: {_exc}", file=sys.stderr)
        return {"references": [], "citations": []}


def _extract_pid(paper: dict) -> str:
    """Ekstrak Semantic Scholar paper ID dari URL paper."""
    link = paper.get("link", "")
    if "semanticscholar.org/paper/" in link:
        return link.split("/paper/")[-1].strip("/")
    return ""


# ─────────────────────────────────────────────────────────────────
# 2. DATA PROCESSING
# ─────────────────────────────────────────────────────────────────

def _safe_int(val, default: int = 0) -> int:
    """Konversi nilai citations ke int aman — handle 'N/A', '1,234', None, dsb."""
    if val is None or val == "":
        return default
    try:
        # Hapus koma ribuan sebelum konversi (e.g. "1,234" → 1234)
        return max(0, int(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return default


def _safe_authors(val) -> str:
    """Konversi field 'authors' ke string aman — handle str, list, None."""
    if val is None:
        return "N/A"
    if isinstance(val, (list, tuple)):
        val = ", ".join(str(v).strip() for v in val if v)
    result = str(val).strip()
    return result or "N/A"


def _normalize_paper(p: dict, idx: int) -> dict:
    """
    Normalisasi satu paper dict dari search_papers() menjadi format
    yang konsisten untuk seluruh modul ini.
    """
    link = p.get("link", "")
    pid  = _extract_pid(p)
    if not pid:
        pid = f"p{idx}_{p.get('title','x')[:20].replace(' ','_')}"

    title    = (p.get("title",    "") or "Untitled").strip()
    abstract = (p.get("abstract", "") or "Abstrak tidak tersedia.").strip()
    year_raw = p.get("year", "")
    try:
        year = int(str(year_raw).strip())
        if not (1900 < year <= 2030):
            year = 2020
    except (ValueError, TypeError):
        year = 2020

    citations = _safe_int(p.get("citations", 0))  # FIXED: safe int, handles "N/A"/"1,234"/None

    return {
        "id":          pid,
        "title":       title,
        "title_short": (title[:55] + "…") if len(title) > 55 else title,
        "authors":     _safe_authors(p.get("authors")),
        "year":        year,
        "citations":   citations,
        "venue":       (p.get("venue",    "") or "Unknown Venue").strip() or "Unknown Venue",
        "abstract":    (abstract[:240] + "…") if len(abstract) > 240 else abstract,
        "link":        link,
        "source":      p.get("source", "unknown"),
        "is_main":     True,   # paper dari hasil pencarian utama
    }


def _build_one_config(
    center_id: str,
    papers_map: dict,
    refs_cache: dict
) -> dict:
    """
    Bangun konfigurasi influence map untuk SATU paper sebagai pusat.

    Algoritma penetapan ring:
      Ring 1 — paper dari papers_map yang ada dalam references center
               ATAU (fallback) paper lebih lama dari center
      Ring 2 — paper dari papers_map yang ada dalam citations center
               ATAU (fallback) paper lebih baru dari center
      Ring 3 — paper tetangga luar dari refs API yang tidak ada di papers_map
               (hanya jika citationCount > 30)

    Returns dict:
      {
        "ring1": [id, ...],
        "ring2": [id, ...],
        "ring3_extra": [{node dict}, ...],  # node baru dari API
        "edges": [{src, dst, type, weight}, ...],
        "stats": {ancestors, descendants, extra_neighbors, ...}
      }
    """
    center = papers_map[center_id]
    refs_data = refs_cache.get(center_id, {"references": [], "citations": []})

    # Set paper IDs yang diketahui dari referensi & sitasi API
    # FIXED: filter out None/empty paperId to avoid "" polluting the sets
    ref_ids  = {r.get("paperId") for r in refs_data.get("references", [])
                if r.get("paperId")}
    cite_ids = {c.get("paperId") for c in refs_data.get("citations",  [])
                if c.get("paperId")}

    # ── Ring assignment ──
    ring1, ring2, ring3_extra = [], [], []
    for pid, p in papers_map.items():
        if pid == center_id:
            continue
        in_refs  = pid in ref_ids
        in_cites = pid in cite_ids
        if in_refs:
            ring1.append(pid)
        elif in_cites:
            ring2.append(pid)
        else:
            # Fallback temporal: lebih lama = leluhur (ring1), lebih baru = keturunan (ring2)
            if p["year"] < center["year"]:
                ring1.append(pid)
            elif p["year"] > center["year"]:
                ring2.append(pid)
            else:
                # Tahun sama → masuk ring dengan sitasi lebih tinggi
                if p["citations"] >= center["citations"]:
                    ring1.append(pid)
                else:
                    ring2.append(pid)

    # ── Ring 3: tetangga dari API (bukan di papers_map) ──
    seen_pids = set(papers_map.keys()) | {center_id}
    api_nodes = refs_data.get("references", []) + refs_data.get("citations", [])
    added_r3  = set()
    for node in sorted(api_nodes,
                       key=lambda x: x.get("citationCount", 0),
                       reverse=True)[:8]:
        nid  = node.get("paperId", "")
        ntit = (node.get("title", "") or "").strip()
        if nid and nid not in seen_pids and nid not in added_r3 and ntit:
            nc = node.get("citationCount", 0) or 0
            if nc > _R3_MIN_CITATIONS:  # FIXED: use named constant
                ring3_extra.append({
                    "id":          nid,
                    "title":       ntit,
                    "title_short": (ntit[:45] + "…") if len(ntit) > 45 else ntit,
                    "authors":     "—",
                    "year":        node.get("year", "?") or "?",
                    "citations":   nc,
                    "venue":       "External",
                    "abstract":    "Paper tetangga dari jaringan sitasi (bukan dari hasil pencarian).",
                    "link":        f"https://www.semanticscholar.org/paper/{nid}",
                    "source":      "neighbor",
                    "is_main":     False,
                })
                added_r3.add(nid)
                if len(added_r3) >= 6:
                    break

    # ── Build edge list ──
    edges = []
    for pid in ring1:
        w = math.log(papers_map[pid]["citations"] + 1) / 3
        edges.append({"src": pid,       "dst": center_id, "type": "r1",
                      "weight": round(max(0.5, w), 3)})

    for pid in ring2:
        w = math.log(papers_map[pid]["citations"] + 1) / 3
        edges.append({"src": center_id, "dst": pid,       "type": "r2",
                      "weight": round(max(0.5, w), 3)})

    for nd in ring3_extra:
        nid = nd["id"]
        w   = math.log(nd["citations"] + 1) / 5
        # Determine direction by year
        yr  = nd["year"] if isinstance(nd["year"], int) else 0
        if yr and yr < center["year"]:
            edges.append({"src": nid,       "dst": center_id, "type": "r3",
                          "weight": round(max(0.3, w), 3)})
        else:
            edges.append({"src": center_id, "dst": nid,       "type": "r3",
                          "weight": round(max(0.3, w), 3)})

    # ── Config stats ──
    avg_r1_cite = (
        sum(papers_map[i]["citations"] for i in ring1) / len(ring1)
        if ring1 else 0
    )

    return {
        "ring1":       ring1,
        "ring2":       ring2,
        "ring3_extra": ring3_extra,
        "edges":       edges,
        "stats": {
            "ancestors":         len(ring1),
            "descendants":       len(ring2),
            "extra_neighbors":   len(ring3_extra),
            "avg_r1_citations":  round(avg_r1_cite),
            "center_citations":  center["citations"],
            "center_year":       center["year"],
        }
    }


@st.cache_data(ttl=3600, show_spinner=False)  # FIXED: cache — prevents double computation
def build_influence_data(papers: list[dict]) -> dict:
    """
    Bangun SELURUH data influence map: satu konfigurasi per paper sebagai pusat.
    Semua konfigurasi di-precompute dan di-embed ke HTML sebagai JSON —
    sehingga re-center di browser adalah instan (zero latency).

    Input:
        papers — list of dict dari search_papers() / data_layer.py

    Output:
    {
      "papers":         [NormalizedPaperDict, ...],
      "configs":        {paper_id: ConfigDict, ...},
      "default_center": paper_id,   # paper dengan sitasi terbanyak
      "year_range":     [min, max],
    }
    """
    if not papers:
        return {"papers": [], "configs": {}, "default_center": "", "year_range": [2015, 2025]}

    # ── Normalisasi semua paper ──
    norm_papers = [_normalize_paper(p, i) for i, p in enumerate(papers)]

    # FIXED: detect & resolve duplicate IDs — dict-comprehension silently overwrites duplicates
    papers_map: dict = {}
    for p in norm_papers:
        pid = p["id"]
        if pid in papers_map:
            import sys
            print(f"[graph_influence] WARNING: duplicate paper ID '{pid}' — appending suffix",
                  file=sys.stderr)
            p = dict(p)
            p["id"] = f"{pid}_dup{sum(1 for k in papers_map if k.startswith(pid))}"
        papers_map[p["id"]] = p

    # ── Fetch refs untuk semua paper (cached) ──
    refs_cache = {}
    for p in norm_papers:
        refs_cache[p["id"]] = fetch_influence_refs(p["id"])

    # ── Precompute konfigurasi tiap center ──
    configs = {}
    for pid in papers_map:
        configs[pid] = _build_one_config(pid, papers_map, refs_cache)

    # ── Default center = paper paling banyak dikutip ──
    default_center = max(papers_map, key=lambda k: papers_map[k]["citations"])

    years     = [p["year"] for p in norm_papers]
    year_min  = min(years, default=2015)
    year_max  = max(years, default=2025)

    return {
        "papers":         norm_papers,
        "configs":        configs,
        "default_center": default_center,
        "year_range":     [year_min, year_max],
    }


# ─────────────────────────────────────────────────────────────────
# 3. STATISTIK
# ─────────────────────────────────────────────────────────────────

def influence_stats(papers: list[dict], center_id: str = None) -> dict:
    """
    Hitung statistik influence map untuk ditampilkan sebagai metric cards
    di Streamlit — di atas atau di bawah komponen HTML.

    Returns dict:
        total_papers, total_nodes (incl. neighbors), center_title,
        center_citations, ancestor_count, descendant_count,
        neighbor_count, influence_reach (total nodes reachable from center)
    """
    if not papers:
        return {}

    data = build_influence_data(papers)
    if not data["papers"]:
        return {}

    cid  = center_id or data["default_center"]
    pmap = {p["id"]: p for p in data["papers"]}
    cfg  = data["configs"].get(cid, {})

    center = pmap.get(cid, {})
    r3_ex  = cfg.get("ring3_extra", [])
    total  = len(data["papers"]) + len(r3_ex)

    return {
        "total_papers":      len(data["papers"]),
        "total_nodes":       total,
        "center_title":      center.get("title_short", "-"),
        "center_citations":  center.get("citations",   0),
        "ancestor_count":    cfg.get("stats", {}).get("ancestors",    0),
        "descendant_count":  cfg.get("stats", {}).get("descendants",  0),
        "neighbor_count":    cfg.get("stats", {}).get("extra_neighbors", 0),
        "influence_reach":   (
            cfg.get("stats", {}).get("ancestors",  0) +
            cfg.get("stats", {}).get("descendants", 0) +
            cfg.get("stats", {}).get("extra_neighbors", 0)
        ),
    }


# ─────────────────────────────────────────────────────────────────
# 4. RENDER HTML
# ─────────────────────────────────────────────────────────────────

def render_influence(papers: list[dict], height: int = 700) -> str:
    """
    Render Influence Map sebagai HTML interaktif penuh.

    Arsitektur visual:
      · SVG layer    — struktur statis: orbit rings, edges, node shapes, labels
      · Canvas layer — animasi: particle system mengalir sepanjang edges
      · CSS layer    — background nebula, glow effects, panel UI

    Gunakan di Streamlit:
        import streamlit.components.v1 as components
        components.html(render_influence(papers), height=720, scrolling=False)

    Returns:
        str — HTML lengkap (~40KB) siap embed
    """
    data      = build_influence_data(papers)
    # FIXED: two-layer XSS defense
    #   1) replace </ with \<\/ so </script> can never prematurely close the tag
    #   2) double-encode as JS string literal → browser parses as data, not code
    _raw_json  = json.dumps(data, ensure_ascii=False).replace('\x3c/', r'\<\/')
    data_json  = json.dumps(_raw_json)          # outer quotes → safe JS string

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Influence Map</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syncopate:wght@400;700&family=Fira+Code:wght@300;400;500&family=Nunito:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;overflow:hidden;
  background:#030a14;color:#c8d8f0;
  font-family:'Nunito',sans-serif;user-select:none;
}}

/* ── Design Tokens ── */
:root{{
  --bg:          #030a14;
  --bg2:         #060f22;
  --panel-bg:    rgba(6,15,35,0.96);
  --border:      rgba(56,189,248,0.14);
  --border-hi:   rgba(56,189,248,0.42);

  --center-c:    #fbbf24;
  --center-g:    rgba(251,191,36,0.55);
  --r1-c:        #38bdf8;
  --r1-g:        rgba(56,189,248,0.45);
  --r2-c:        #34d399;
  --r2-g:        rgba(52,211,153,0.40);
  --r3-c:        #94a3b8;
  --r3-g:        rgba(148,163,184,0.30);

  --text-hi:     #e8f2ff;
  --text-mid:    #8ab0d0;
  --text-lo:     #3d5a78;

  --font-disp:   'Syncopate',sans-serif;
  --font-mono:   'Fira Code',monospace;
  --font-body:   'Nunito',sans-serif;
}}

/* ── Root container ── */
#iw{{
  width:100%;height:{height}px;
  position:relative;overflow:hidden;
  background:radial-gradient(ellipse 80% 70% at 50% 50%,
    rgba(15,30,70,0.6) 0%,
    rgba(3,10,20,1) 65%);
}}

/* Nebula glow behind center (dynamic via JS) */
#nebula{{
  position:absolute;pointer-events:none;border-radius:50%;
  transition:left .6s ease,top .6s ease,opacity .4s;
  z-index:0;opacity:.55;
}}

/* Scanline overlay */
#iw::after{{
  content:'';position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(
    0deg,transparent,transparent 2px,rgba(0,15,45,.06) 2px,rgba(0,15,45,.06) 3px
  );
}}

/* ── Control bar ── */
#ctrl{{
  position:absolute;top:0;left:0;right:0;
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:8px 14px;z-index:30;
  background:linear-gradient(180deg,rgba(3,10,20,.98),transparent);
}}
.c-lbl{{
  font-family:var(--font-disp);font-size:9.5px;letter-spacing:3px;
  color:var(--text-lo);text-transform:uppercase;white-space:nowrap;
}}
.c-sep{{width:1px;height:20px;background:var(--border);flex-shrink:0;}}
.c-btn{{
  display:flex;align-items:center;gap:5px;cursor:pointer;
  padding:4px 10px;border-radius:4px;
  border:1px solid var(--border);background:transparent;
  font-family:var(--font-mono);font-size:11px;letter-spacing:.8px;
  color:var(--text-mid);transition:all .18s;
}}
.c-btn:hover{{border-color:var(--border-hi);color:var(--text-hi);}}
.c-btn.on-amber{{border-color:var(--center-c);color:var(--center-c);background:rgba(251,191,36,.07);box-shadow:0 0 7px rgba(251,191,36,.18);}}
.c-btn.on-sky{{border-color:var(--r1-c);color:var(--r1-c);background:rgba(56,189,248,.07);}}
.c-btn.on-green{{border-color:var(--r2-c);color:var(--r2-c);background:rgba(52,211,153,.07);}}
.c-dot{{width:6px;height:6px;border-radius:50%;background:currentColor;flex-shrink:0;}}
/* Paper selector */
#sel-wrap{{margin-left:auto;display:flex;align-items:center;gap:7px;}}
.c-lbl-inline{{font-family:var(--font-mono);font-size:10.5px;color:var(--text-lo);white-space:nowrap;}}
#paper-sel{{
  background:rgba(6,15,35,.9);border:1px solid var(--border);
  border-radius:5px;color:var(--r1-c);padding:4px 26px 4px 10px;
  font-family:var(--font-mono);font-size:11px;cursor:pointer;
  appearance:none;outline:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2338bdf8'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;
  max-width:200px;
}}
#paper-sel option{{background:#060f22;color:#c8d8f0;}}

/* ── SVG + Canvas ── */
#sc{{position:absolute;inset:0;z-index:2;}}
#svg{{position:absolute;inset:0;width:100%;height:100%;}}
#cv {{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;}}

/* SVG classes */
.orbit-ring{{
  fill:none;stroke-dasharray:6 12;
  animation:orbit-spin var(--spd,24s) linear infinite;
  transform-origin:var(--ox,50%) var(--oy,50%);
}}
@keyframes orbit-spin{{to{{stroke-dashoffset:-180}}}}

.edge-line{{fill:none;transition:opacity .3s;}}
.edge-line.dim{{opacity:.04;}}

.inode{{cursor:pointer;transition:opacity .3s;}}
.inode:hover .n-glow{{opacity:.7;}}
.inode.dim{{opacity:.1;}}

.n-glow{{transition:opacity .3s;}}
.n-ring-anim{{animation:pulse-ring 2.2s ease-out infinite;}}
@keyframes pulse-ring{{
  0%{{transform:scale(1);opacity:.7;}}
  60%{{transform:scale(1.5);opacity:0;}}
  100%{{transform:scale(1.5);opacity:0;}}
}}

.n-lbl{{
  font-family:var(--font-body);font-size:12px;fill:#d0e4f8;
  pointer-events:none;text-anchor:middle;dominant-baseline:hanging;
}}
.n-cite{{
  font-family:var(--font-mono);font-size:10px;
  pointer-events:none;text-anchor:middle;
}}
.n-yr{{
  font-family:var(--font-mono);font-size:11px;font-weight:500;
  text-anchor:middle;dominant-baseline:central;pointer-events:none;
}}
.ring-label{{
  font-family:var(--font-disp);font-size:9px;letter-spacing:2px;
  text-transform:uppercase;text-anchor:middle;dominant-baseline:central;
  pointer-events:none;
}}

/* ── Tooltip ── */
#tt{{
  position:absolute;display:none;pointer-events:none;z-index:100;
  background:rgba(3,10,20,.97);border:1px solid rgba(56,189,248,.25);
  border-radius:9px;padding:13px 15px;max-width:280px;min-width:200px;
  box-shadow:0 12px 40px rgba(0,0,0,.8),0 0 20px rgba(56,189,248,.06);
  backdrop-filter:blur(16px);font-size:13px;line-height:1.5;
}}
.tt-title{{font-family:var(--font-body);font-size:13px;font-weight:700;color:var(--text-hi);margin-bottom:4px;line-height:1.35;}}
.tt-meta{{font-family:var(--font-mono);font-size:10px;color:var(--text-mid);letter-spacing:.3px;margin-bottom:2px;}}
.tt-ring{{
  display:inline-flex;align-items:center;gap:5px;
  padding:2px 8px;border-radius:3px;
  font-family:var(--font-mono);font-size:9.5px;letter-spacing:1px;
  text-transform:uppercase;font-weight:500;margin:5px 0 6px;
  border:1px solid currentColor;background:rgba(0,0,0,.2);
}}
.tt-abs{{font-family:var(--font-body);font-size:11px;color:var(--text-mid);line-height:1.5;border-top:1px solid var(--border);padding-top:5px;margin-top:4px;}}
.tt-hint{{font-family:var(--font-mono);font-size:9.5px;color:var(--center-c);margin-top:6px;}}

/* ── Detail Panel ── */
#dp{{
  position:absolute;right:14px;top:52px;width:240px;
  background:var(--panel-bg);border:1px solid var(--border);
  border-radius:10px;padding:14px;z-index:50;
  display:none;animation:dp-in .22s ease;
  box-shadow:0 12px 40px rgba(0,0,0,.6);backdrop-filter:blur(16px);
}}
@keyframes dp-in{{from{{opacity:0;transform:translateX(16px)}}to{{opacity:1;transform:none}}}}
#dp.vis{{display:block;}}
.dp-x{{
  position:absolute;top:10px;right:12px;cursor:pointer;
  color:var(--text-lo);font-size:15px;line-height:1;transition:color .15s;
}}
.dp-x:hover{{color:var(--text-hi);}}
.dp-title{{font-family:var(--font-body);font-size:13px;font-weight:700;color:var(--text-hi);line-height:1.4;margin-bottom:10px;padding-right:16px;}}
.dp-row{{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);}}
.dp-k{{font-family:var(--font-mono);font-size:9.5px;color:var(--text-lo);letter-spacing:.7px;text-transform:uppercase;}}
.dp-v{{font-family:var(--font-mono);font-size:11.5px;color:var(--r1-c);font-weight:500;}}
.dp-abs{{font-family:var(--font-body);font-size:11px;color:var(--text-mid);line-height:1.5;margin:8px 0;}}
.dp-btn{{
  display:block;width:100%;padding:7px;text-align:center;
  background:rgba(56,189,248,.07);border:1px solid rgba(56,189,248,.22);
  border-radius:5px;color:var(--r1-c);cursor:pointer;
  font-family:var(--font-mono);font-size:10px;letter-spacing:1.5px;
  text-transform:uppercase;text-decoration:none;transition:all .18s;margin-bottom:6px;
}}
.dp-btn:hover{{background:rgba(56,189,248,.18);}}
.dp-recenter{{
  display:block;width:100%;padding:7px;text-align:center;
  background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.22);
  border-radius:5px;color:var(--center-c);cursor:pointer;
  font-family:var(--font-mono);font-size:10px;letter-spacing:1.5px;
  text-transform:uppercase;transition:all .18s;
}}
.dp-recenter:hover{{background:rgba(251,191,36,.18);}}

/* ── Stats Panel (right) ── */
#sp{{
  position:absolute;right:14px;bottom:40px;width:170px;
  background:var(--panel-bg);border:1px solid var(--border);
  border-radius:9px;padding:12px;z-index:20;
}}
.sp-hdr{{
  font-family:var(--font-disp);font-size:9px;letter-spacing:3px;
  color:var(--text-lo);text-transform:uppercase;margin-bottom:8px;
}}
.sp-row{{display:flex;justify-content:space-between;align-items:center;padding:3px 0;}}
.sp-k{{font-family:var(--font-mono);font-size:9.5px;color:var(--text-lo);}}
.sp-v{{font-family:var(--font-mono);font-size:12px;font-weight:500;}}
.sp-bar{{
  height:3px;background:rgba(56,189,248,.1);border-radius:2px;
  margin:5px 0;overflow:hidden;
}}
.sp-fill{{height:100%;border-radius:2px;transition:width .6s ease;}}

/* ── Compare Mode ── */
#compare-wrap{{
  position:absolute;inset:36px 0 0 0;display:none;z-index:25;
}}
#compare-wrap.vis{{display:flex;}}
.cmp-half{{flex:1;position:relative;border:1px solid var(--border);margin:4px;border-radius:8px;overflow:hidden;}}
.cmp-sel-wrap{{position:absolute;top:8px;left:0;right:0;display:flex;justify-content:center;z-index:5;}}
.cmp-sel{{
  background:rgba(6,15,35,.95);border:1px solid var(--border);
  border-radius:4px;color:var(--r1-c);padding:4px 22px 4px 8px;
  font-family:var(--font-mono);font-size:10.5px;cursor:pointer;appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2338bdf8'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 6px center;max-width:180px;
}}
.cmp-sel option{{background:#060f22;}}
.cmp-svg{{width:100%;height:100%;}}
.shared-badge{{
  position:absolute;bottom:8px;left:0;right:0;text-align:center;
  font-family:var(--font-mono);font-size:9.5px;color:var(--r2-c);
  letter-spacing:.5px;pointer-events:none;
}}

/* ── Legend ── */
#leg{{
  position:absolute;bottom:14px;left:14px;
  display:flex;align-items:center;gap:14px;z-index:20;
}}
.leg-i{{display:flex;align-items:center;gap:5px;font-family:var(--font-mono);font-size:10px;color:var(--text-lo);}}
.leg-d{{width:9px;height:9px;border-radius:50%;flex-shrink:0;}}
</style>
</head>
<body>
<div id="iw">
  <!-- Nebula background glow -->
  <div id="nebula"></div>

  <!-- Control bar -->
  <div id="ctrl">
    <span class="c-lbl">Influence Map ◈</span>
    <div class="c-sep"></div>
    <button class="c-btn on-amber" id="btn-part" onclick="toggleParticles()"><span class="c-dot"></span>PARTICLES</button>
    <button class="c-btn on-sky"   id="btn-orb"  onclick="toggleOrbits()">  <span class="c-dot"></span>ORBITS</button>
    <button class="c-btn"          id="btn-heat" onclick="toggleHeatmap()"> <span class="c-dot"></span>HEATMAP</button>
    <button class="c-btn"          id="btn-cmp"  onclick="toggleCompare()"> <span class="c-dot"></span>COMPARE</button>
    <div class="c-sep"></div>
    <div id="sel-wrap">
      <span class="c-lbl-inline">PUSAT :</span>
      <select id="paper-sel" onchange="onSelectCenter(this.value)"></select>
    </div>
  </div>

  <!-- Main SVG + Canvas -->
  <div id="sc">
    <svg id="svg" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="grad-center" cx="50%" cy="50%" r="50%">
          <stop offset="0%"   stop-color="#fde68a" stop-opacity="1"/>
          <stop offset="60%"  stop-color="#f59e0b" stop-opacity=".8"/>
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
        <filter id="f-center" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="7" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="f-node" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="4" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="f-glow-hi" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6"/>
        </filter>
        <marker id="arr-r1" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L0,8 L8,4 z" fill="rgba(56,189,248,0.55)"/>
        </marker>
        <marker id="arr-r2" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L0,8 L8,4 z" fill="rgba(52,211,153,0.55)"/>
        </marker>
        <marker id="arr-r3" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
          <path d="M0,0 L0,7 L7,3.5 z" fill="rgba(148,163,184,0.35)"/>
        </marker>
      </defs>
      <rect width="100%" height="100%" fill="transparent"/>
      <g id="g-orbits"></g>
      <g id="g-edges"></g>
      <g id="g-nodes"></g>
    </svg>
    <!-- Particle canvas overlay -->
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
    <a  class="dp-btn"      id="dp-link"     href="#" target="_blank">↗ BUKA PAPER</a>
    <div class="dp-recenter" id="dp-recenter" onclick="reCenterFromPanel()">⊙ JADIKAN PUSAT</div>
  </div>

  <!-- Stats Panel -->
  <div id="sp">
    <div class="sp-hdr">Network Stats</div>
    <div id="sp-content"></div>
  </div>

  <!-- Compare Mode overlay -->
  <div id="compare-wrap">
    <div class="cmp-half" id="cmp-left">
      <div class="cmp-sel-wrap">
        <select class="cmp-sel" id="cmp-sel-a" onchange="renderCompare()"></select>
      </div>
      <svg class="cmp-svg" id="cmp-svg-a" xmlns="http://www.w3.org/2000/svg"></svg>
      <div class="shared-badge" id="cmp-badge-a"></div>
    </div>
    <div class="cmp-half" id="cmp-right">
      <div class="cmp-sel-wrap">
        <select class="cmp-sel" id="cmp-sel-b" onchange="renderCompare()"></select>
      </div>
      <svg class="cmp-svg" id="cmp-svg-b" xmlns="http://www.w3.org/2000/svg"></svg>
      <div class="shared-badge" id="cmp-badge-b"></div>
    </div>
  </div>

  <!-- Legend -->
  <div id="leg">
    <span class="leg-i"><span class="leg-d" style="background:#fbbf24;box-shadow:0 0 6px #fbbf24"></span>PUSAT</span>
    <span class="leg-i"><span class="leg-d" style="background:#38bdf8"></span>LELUHUR (ring 1)</span>
    <span class="leg-i"><span class="leg-d" style="background:#34d399"></span>PENERUS (ring 2)</span>
    <span class="leg-i"><span class="leg-d" style="background:#94a3b8"></span>TETANGGA (ring 3)</span>
  </div>
</div><!-- #iw -->

<script>
/* ════════════════════════════════════════
   DATA
════════════════════════════════════════ */
const D = JSON.parse({data_json}); /* FIXED: safe JSON.parse, no raw injection */

/* ════════════════════════════════════════
   SAFETY — HTML escape for DOM injection
════════════════════════════════════════ */
function safeText(s) {{
  /* FIXED: prevent DOM XSS — escape HTML entities before inserting into innerHTML */
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}}

/* ════════════════════════════════════════
   STATE
════════════════════════════════════════ */
const S = {{
  center:      D.default_center,
  showPart:    true,
  showOrbits:  true,
  heatmap:     false,
  compare:     false,
  focusNode:   null,
  transitioning: false,
  compareA:    D.default_center,
  compareB:    D.papers[1] ? D.papers[1].id : D.default_center,
}};

/* ════════════════════════════════════════
   CONSTANTS
════════════════════════════════════════ */
const RING_CLR = {{
  center: '#fbbf24',
  r1:     '#38bdf8',
  r2:     '#34d399',
  r3:     '#94a3b8',
}};
const RING_NAMES = {{center:'PUSAT', r1:'LELUHUR', r2:'PENERUS', r3:'TETANGGA'}};
const NODE_BASE  = 16;
const NODE_MAX   = 48;

/* ════════════════════════════════════════
   HELPERS
════════════════════════════════════════ */
function W() {{ return document.getElementById('sc').clientWidth  || 800; }}
function H() {{ return document.getElementById('sc').clientHeight || 600; }}

function ns(tag, attrs={{}}) {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([k,v]) => el.setAttribute(k, v));
  return el;
}}

function nodeSize(citations) {{
  if (!citations) return NODE_BASE;
  return Math.max(NODE_BASE, Math.min(NODE_MAX, Math.log(citations+1)*5.5));
}}

function heatColor(ring) {{
  if (!S.heatmap) return null;
  switch(ring) {{
    case 'center': return '#ffffff';
    case 'r1':     return '#ef4444';
    case 'r2':     return '#f97316';
    case 'r3':     return '#3b82f6';
    default:       return '#94a3b8';
  }}
}}

function ringColor(ring) {{
  const hc = heatColor(ring);
  if (hc) return hc;
  return RING_CLR[ring] || RING_CLR.r3;
}}

/* ════════════════════════════════════════
   LAYOUT — positions for all nodes
════════════════════════════════════════ */
function computeLayout(centerId, w, h, forCompare=false) {{
  const cfg   = D.configs[centerId];
  if (!cfg) return {{}};

  const cx = w / 2;
  const cy = h / 2 + (forCompare ? 15 : 0);

  const minDim = Math.min(w, h);
  const R1 = minDim * 0.22;
  const R2 = minDim * 0.40;
  const R3 = minDim * 0.58;

  const pos = {{}};
  pos[centerId] = {{x:cx, y:cy, ring:'center', r:0}};

  function placeRing(ids, R, ringName) {{
    const n = ids.length;
    if (!n) return;
    const angleOffset = -Math.PI / 2; // start at top
    ids.forEach((id, i) => {{
      const a = angleOffset + (2 * Math.PI * i) / n;
      pos[id] = {{
        x: cx + R * Math.cos(a),
        y: cy + R * Math.sin(a),
        ring: ringName,
        r: R,
        angle: a
      }};
    }});
  }}

  placeRing(cfg.ring1,       R1, 'r1');
  placeRing(cfg.ring2,       R2, 'r2');

  // Ring 3 extra nodes
  const r3ids = cfg.ring3_extra.map(n => n.id);
  placeRing(r3ids, R3, 'r3');

  return {{pos, R1, R2, R3, cx, cy}};
}}

/* ════════════════════════════════════════
   ALL NODES (main + r3 extras) for current center
════════════════════════════════════════ */
function allNodesForCenter(centerId) {{
  const pmap = {{}};
  D.papers.forEach(p => {{ pmap[p.id] = p; }});
  const cfg  = D.configs[centerId] || {{}};
  const r3ex = cfg.ring3_extra || [];
  r3ex.forEach(n => {{ pmap[n.id] = n; }});
  return pmap;
}}

/* ════════════════════════════════════════
   DRAW: ORBIT RINGS
════════════════════════════════════════ */
function drawOrbits(g, layout) {{
  g.innerHTML = '';
  if (!S.showOrbits) return;
  const {{R1,R2,R3,cx,cy}} = layout;

  const rings = [
    {{r:R1, c:'rgba(56,189,248,.18)',  spd:'28s',  lbl:'RING 1 · LELUHUR'}},
    {{r:R2, c:'rgba(52,211,153,.14)',  spd:'38s',  lbl:'RING 2 · PENERUS'}},
    {{r:R3, c:'rgba(148,163,184,.10)', spd:'50s',  lbl:'RING 3 · TETANGGA'}},
  ];

  rings.forEach((ri, i) => {{
    if (ri.r <= 0) return;
    const circ = ns('circle', {{
      cx, cy, r:ri.r,
      class:'orbit-ring',
      stroke:ri.c,
      'stroke-width': i===0?1.4:i===1?1.1:.8,
      style:`--spd:${{ri.spd}};--ox:${{cx}}px;--oy:${{cy}}px`
    }});
    g.appendChild(circ);

    // Ring label at top of each orbit
    const lx = cx;
    const ly = cy - ri.r - 8;
    const lt = ns('text', {{
      x:lx, y:ly, class:'ring-label',
      fill:ri.c.replace('.18)','.5)').replace('.14)','.4)').replace('.10)','.3)')
    }});
    lt.textContent = ri.lbl;
    g.appendChild(lt);
  }});
}}

/* ════════════════════════════════════════
   DRAW: EDGES
════════════════════════════════════════ */
function drawEdges(g, layout, pmap) {{
  g.innerHTML = '';
  const cfg = D.configs[S.center];
  if (!cfg) return;
  const {{pos}} = layout;

  cfg.edges.forEach(e => {{
    const a = pos[e.src], b = pos[e.dst];
    if (!a || !b) return;

    const t = e.type; // r1, r2, r3
    const clr = t==='r1' ? 'rgba(56,189,248,0.35)'
               :t==='r2' ? 'rgba(52,211,153,0.30)'
               :           'rgba(148,163,184,0.18)';
    const arr = t==='r1' ? 'url(#arr-r1)'
               :t==='r2' ? 'url(#arr-r2)'
               :           'url(#arr-r3)';

    // Curved bezier
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.sqrt(dx*dx + dy*dy);
    const curve = dist * 0.15;
    const mx = (a.x+b.x)/2 - dy*curve/dist;
    const my = (a.y+b.y)/2 + dx*curve/dist;

    const path = ns('path', {{
      d:`M${{a.x}},${{a.y}} Q${{mx}},${{my}} ${{b.x}},${{b.y}}`,
      class:'edge-line',
      stroke:clr,
      'stroke-width': Math.max(.8, e.weight * 1.8),
      'marker-end': arr,
    }});
    path.dataset.src = e.src;
    path.dataset.dst = e.dst;
    g.appendChild(path);
  }});
}}

/* ════════════════════════════════════════
   DRAW: NODES
════════════════════════════════════════ */
function drawNodes(g, layout, pmap) {{
  g.innerHTML = '';
  const cfg = D.configs[S.center];
  if (!cfg) return;
  const {{pos}} = layout;

  Object.entries(pos).forEach(([id, p]) => {{
    const node = pmap[id];
    if (!node) return;

    const isCenter = (id === S.center);
    const ring     = p.ring;
    const sz       = isCenter ? nodeSize(node.citations) * 1.35 : nodeSize(node.citations);
    const clr      = ringColor(ring);
    const fil      = isCenter ? 'f-center' : 'f-node';

    const grp = ns('g', {{
      class: 'inode',
      transform: `translate(${{p.x}},${{p.y}})`
    }});
    grp.dataset.id = id;

    // Outer glow halo
    grp.appendChild(ns('circle', {{
      r: sz + 8, fill: clr, opacity: '.10',
      class: 'n-glow', filter: `url(#f-glow-hi)`
    }}));

    if (isCenter) {{
      // Pulse ring animation for center
      const pr = ns('circle', {{
        r: sz + 4, fill:'none', stroke:clr,
        'stroke-width':'1.5', opacity:'.6',
        class:'n-ring-anim'
      }});
      grp.appendChild(pr);
    }}

    // Main circle
    grp.appendChild(ns('circle', {{
      r: sz,
      fill: `url(#grad-${{ring==='center'?'center':ring}})`,
      stroke: clr, 'stroke-width': isCenter ? 2 : 1.4,
      filter: `url(#${{fil}})`,
    }}));

    // Inner highlight dot (top-left)
    grp.appendChild(ns('circle', {{
      r: sz*.28, cx: -sz*.25, cy: -sz*.28,
      fill: 'rgba(255,255,255,0.22)'
    }}));

    // Year badge
    const yrTxt = ns('text', {{
      x:0, y:0, class:'n-yr', fill:clr
    }});
    yrTxt.textContent = node.year;
    grp.appendChild(yrTxt);

    // Label below
    const lblY = sz + 12;
    const lbl  = ns('text', {{ x:0, y:lblY, class:'n-lbl' }});
    lbl.textContent = node.title_short
      ? node.title_short.substring(0, isCenter?50:32) + (node.title_short.length > (isCenter?50:32) ? '…':'')
      : id.substring(0,20);
    grp.appendChild(lbl);

    // Citation count below label
    const cTxt = ns('text', {{
      x:0, y:lblY+13, class:'n-cite', fill:clr, opacity:'.65'
    }});
    cTxt.textContent = `↑ ${{(node.citations||0).toLocaleString()}}`;
    grp.appendChild(cTxt);

    // Events
    grp.addEventListener('mouseenter', ev => showTooltip(ev, node, ring));
    grp.addEventListener('mouseleave', hideTooltip);
    grp.addEventListener('click',      ()  => onNodeClick(id, node, ring));

    g.appendChild(grp);
  }});

  // Move nebula glow to center
  const cp = pos[S.center];
  if (cp) moveNebula(cp.x, cp.y);
}}

/* ════════════════════════════════════════
   NEBULA
════════════════════════════════════════ */
function moveNebula(x, y) {{
  const neb = document.getElementById('nebula');
  const sz  = Math.min(W(), H()) * 0.55;
  neb.style.cssText = `
    width:${{sz}}px;height:${{sz}}px;
    left:${{x - sz/2}}px;top:${{y - sz/2}}px;
    background:radial-gradient(circle,rgba(251,191,36,.12) 0%,rgba(56,189,248,.05) 40%,transparent 70%);
    display:block;
  `;
}}

/* ════════════════════════════════════════
   STATS PANEL
════════════════════════════════════════ */
function updateStats() {{
  const cfg  = D.configs[S.center] || {{}};
  const st   = cfg.stats  || {{}};
  const pmap = allNodesForCenter(S.center);
  const cn   = pmap[S.center] || {{}};

  const maxCite = Math.max(...D.papers.map(p=>p.citations), 1);
  const pct     = Math.min(100, Math.round((cn.citations||0)/maxCite*100));

  document.getElementById('sp-content').innerHTML = `
    <div class="sp-row"><span class="sp-k">Judul</span></div>
    <div style="font-family:var(--font-body);font-size:11px;color:var(--r1-c);padding:3px 0 6px;line-height:1.35">
      ${{safeText((cn.title_short||'—').substring(0,55))}}
    </div>
    <div class="sp-row">
      <span class="sp-k">Sitasi</span>
      <span class="sp-v" style="color:var(--center-c)">${{(cn.citations||0).toLocaleString()}}</span>
    </div>
    <div class="sp-bar"><div class="sp-fill" style="width:${{pct}}%;background:var(--center-c)"></div></div>
    <div class="sp-row">
      <span class="sp-k">Leluhur</span>
      <span class="sp-v" style="color:var(--r1-c)">${{st.ancestors||0}}</span>
    </div>
    <div class="sp-row">
      <span class="sp-k">Penerus</span>
      <span class="sp-v" style="color:var(--r2-c)">${{st.descendants||0}}</span>
    </div>
    <div class="sp-row">
      <span class="sp-k">Tetangga</span>
      <span class="sp-v" style="color:var(--r3-c)">${{st.extra_neighbors||0}}</span>
    </div>
    <div class="sp-row">
      <span class="sp-k">Tahun</span>
      <span class="sp-v">${{cn.year||'?'}}</span>
    </div>
  `;
}}

/* ════════════════════════════════════════
   TOOLTIP
════════════════════════════════════════ */
function showTooltip(ev, node, ring) {{
  const tt  = document.getElementById('tt');
  const rc  = RING_CLR[ring] || RING_CLR.r3;
  const rn  = RING_NAMES[ring] || ring;
  tt.innerHTML = `
    <div class="tt-title">${{safeText(node.title)}}</div>
    <div class="tt-meta">👤 ${{safeText((node.authors||'N/A').split(',').slice(0,2).join(', '))}}</div>
    <div class="tt-meta">📅 ${{node.year}} &nbsp;·&nbsp; ↑ ${{(node.citations||0).toLocaleString()}} sitasi</div>
    <div class="tt-meta">🏛️ ${{safeText(node.venue||'—')}}</div>
    <span class="tt-ring" style="color:${{rc}};border-color:${{rc}}">${{rn}}</span>
    <div class="tt-abs">${{safeText(node.abstract)}}</div>
    ${{ring!=='center' ? `<div class="tt-hint">🖱️ Klik sekali → detail &nbsp;|&nbsp; Klik lagi → jadikan pusat</div>` : '<div class="tt-hint">⊙ Ini adalah paper pusat saat ini</div>'}}
  `;
  const sc = document.getElementById('sc').getBoundingClientRect();
  let tx = ev.clientX - sc.left + 14;
  let ty = ev.clientY - sc.top  - 10;
  if (tx + 295 > sc.width)  tx = ev.clientX - sc.left - 295;
  if (ty + 260 > sc.height) ty = ev.clientY - sc.top  - 260;
  tt.style.cssText = `display:block;left:${{tx}}px;top:${{ty}}px`;
}}
function hideTooltip() {{ document.getElementById('tt').style.display = 'none'; }}

/* ════════════════════════════════════════
   NODE CLICK — focus then recenter
════════════════════════════════════════ */
let _lastClickId = null;
function onNodeClick(id, node, ring) {{
  hideTooltip();
  if (id === S.center) return;

  if (_lastClickId === id) {{
    // Second click → recenter
    _lastClickId = null;
    closePanel();
    reCenter(id);
  }} else {{
    // First click → show panel
    _lastClickId = id;
    openPanel(id, node, ring);
    applyFocus(id);
  }}
}}

function applyFocus(id) {{
  S.focusNode = id;
  const cfg = D.configs[S.center];
  if (!cfg) return;
  const connected = new Set([id, S.center]);
  cfg.edges.forEach(e => {{
    if (e.src===id||e.dst===id) {{ connected.add(e.src); connected.add(e.dst); }}
  }});
  document.querySelectorAll('.inode').forEach(el => {{
    el.classList.toggle('dim', !connected.has(el.dataset.id));
  }});
  document.querySelectorAll('.edge-line').forEach(el => {{
    const conn = connected.has(el.dataset.src) && connected.has(el.dataset.dst);
    el.classList.toggle('dim', !conn);
  }});
}}

function clearFocus() {{
  S.focusNode  = null;
  _lastClickId = null;
  document.querySelectorAll('.inode,.edge-line').forEach(el => el.classList.remove('dim'));
}}

/* ════════════════════════════════════════
   DETAIL PANEL
════════════════════════════════════════ */
let _panelNodeId = null;
function openPanel(id, node, ring) {{
  _panelNodeId = id;
  const rc = RING_CLR[ring] || RING_CLR.r3;
  document.getElementById('dp-title').textContent = node.title;
  document.getElementById('dp-abs').textContent   = node.abstract;
  document.getElementById('dp-link').href          = node.link || '#';
  document.getElementById('dp-rows').innerHTML = `
    <div class="dp-row"><span class="dp-k">TAHUN</span>  <span class="dp-v">${{node.year}}</span></div>
    <div class="dp-row"><span class="dp-k">SITASI</span> <span class="dp-v" style="color:var(--center-c)">${{(node.citations||0).toLocaleString()}}</span></div>
    <div class="dp-row"><span class="dp-k">RING</span>   <span class="dp-v" style="color:${{rc}}">${{RING_NAMES[ring]||ring}}</span></div>
    <div class="dp-row"><span class="dp-k">VENUE</span>  <span class="dp-v" style="font-size:10px">${{safeText((node.venue||'—').substring(0,25))}}</span></div>
  `;
  document.getElementById('dp').classList.add('vis');
}}
function closePanel() {{
  document.getElementById('dp').classList.remove('vis');
  clearFocus();
}}
function reCenterFromPanel() {{
  if (_panelNodeId) {{
    closePanel();
    reCenter(_panelNodeId);
  }}
}}

/* ════════════════════════════════════════
   RE-CENTER with transition animation
════════════════════════════════════════ */
function reCenter(newId) {{
  if (S.transitioning || newId === S.center) return;
  if (!D.configs[newId]) return;
  S.transitioning = true;

  // Fade out existing nodes
  const gn = document.getElementById('g-nodes');
  const ge = document.getElementById('g-edges');
  gn.style.transition = 'opacity .35s';
  ge.style.transition = 'opacity .35s';
  gn.style.opacity    = '0';
  ge.style.opacity    = '0';

  setTimeout(() => {{
    S.center = newId;
    // Update selector
    document.getElementById('paper-sel').value = newId;
    // Re-render
    renderMain();
    updateStats();
    // Fade back in
    gn.style.opacity = '1';
    ge.style.opacity = '1';
    setTimeout(() => {{ S.transitioning = false; }}, 350);
  }}, 320);
}}

/* ════════════════════════════════════════
   TOGGLES
════════════════════════════════════════ */
function toggleParticles() {{
  S.showPart = !S.showPart;
  const b = document.getElementById('btn-part');
  b.className = 'c-btn' + (S.showPart ? ' on-amber' : '');
}}
function toggleOrbits() {{
  S.showOrbits = !S.showOrbits;
  const b = document.getElementById('btn-orb');
  b.className = 'c-btn' + (S.showOrbits ? ' on-sky' : '');
  const layout = computeLayout(S.center, W(), H());
  drawOrbits(document.getElementById('g-orbits'), layout);
}}
function toggleHeatmap() {{
  S.heatmap = !S.heatmap;
  const b = document.getElementById('btn-heat');
  b.className = 'c-btn' + (S.heatmap ? ' on-green' : '');
  renderMain();
}}
function toggleCompare() {{
  S.compare = !S.compare;
  const b  = document.getElementById('btn-cmp');
  b.className = 'c-btn' + (S.compare ? ' on-sky' : '');
  document.getElementById('compare-wrap').classList.toggle('vis', S.compare);
  document.getElementById('sc').style.display = S.compare ? 'none' : 'block';
  document.getElementById('sp').style.display = S.compare ? 'none' : 'block';
  if (S.compare) renderCompare();
}}
function onSelectCenter(val) {{
  if (val && val !== S.center) reCenter(val);
}}

/* ════════════════════════════════════════
   COMPARE MODE RENDER
════════════════════════════════════════ */
function renderCompare() {{
  const selA = document.getElementById('cmp-sel-a').value || S.compareA;
  const selB = document.getElementById('cmp-sel-b').value || S.compareB;

  const svgA = document.getElementById('cmp-svg-a');
  const svgB = document.getElementById('cmp-svg-b');

  const wHalf = (document.getElementById('compare-wrap').clientWidth / 2) - 16;
  const hCmp  = document.getElementById('compare-wrap').clientHeight - 8;

  [svgA,svgB].forEach(s=>{{s.setAttribute('width',wHalf);s.setAttribute('height',hCmp);}});

  renderMiniMap(svgA, selA, wHalf, hCmp);
  renderMiniMap(svgB, selB, wHalf, hCmp);

  // Find shared nodes
  const cfgA = D.configs[selA] || {{}};
  const cfgB = D.configs[selB] || {{}};
  const setA = new Set([...(cfgA.ring1||[]),...(cfgA.ring2||[])]);
  const setB = new Set([...(cfgB.ring1||[]),...(cfgB.ring2||[])]);
  const shared = [...setA].filter(id => setB.has(id));
  const msg = shared.length
    ? `⇌ ${{shared.length}} paper bersama terdeteksi`
    : '— tidak ada paper yang sama —';
  document.getElementById('cmp-badge-a').textContent = msg;
  document.getElementById('cmp-badge-b').textContent = msg;
}}

function renderMiniMap(svgEl, centerId, w, h) {{
  svgEl.innerHTML = '';

  const cfg = D.configs[centerId];
  if (!cfg) return;

  const pmap   = allNodesForCenter(centerId);
  const layout = computeLayout(centerId, w, h, true);
  const {{pos}} = layout;

  // Defs
  const defs = ns('defs');
  svgEl.appendChild(defs);
  svgEl.appendChild(ns('rect',{{width:w,height:h,fill:'rgba(3,10,20,.9)',rx:'7'}}));

  // Edges
  cfg.edges.forEach(e => {{
    const a = pos[e.src], b = pos[e.dst];
    if (!a||!b) return;
    const clr = e.type==='r1'?'rgba(56,189,248,.35)':e.type==='r2'?'rgba(52,211,153,.3)':'rgba(148,163,184,.18)';
    const dx=b.x-a.x,dy=b.y-a.y,dist=Math.sqrt(dx*dx+dy*dy)||1;
    const mx=(a.x+b.x)/2-dy*.12,my=(a.y+b.y)/2+dx*.12;
    svgEl.appendChild(ns('path',{{
      d:`M${{a.x}},${{a.y}} Q${{mx}},${{my}} ${{b.x}},${{b.y}}`,
      fill:'none',stroke:clr,'stroke-width': Math.max(.6,e.weight*1.4)
    }}));
  }});

  // Nodes
  Object.entries(pos).forEach(([id, p]) => {{
    const node = pmap[id];
    if (!node) return;
    const isC = id===centerId;
    const sz  = isC ? 14 : Math.max(7, Math.min(18, Math.log((node.citations||0)+1)*3.5));
    const clr = RING_CLR[p.ring]||RING_CLR.r3;
    const grp = ns('g',{{transform:`translate(${{p.x}},${{p.y}})`}});
    grp.appendChild(ns('circle',{{r:sz,fill:clr,opacity:isC?.9:.65}}));
    if (isC) {{
      const lt=ns('text',{{x:0,y:sz+11,fill:'#fbbf24',
        'font-family':'Fira Code,monospace','font-size':'8',
        'text-anchor':'middle','dominant-baseline':'hanging'}});
      lt.textContent=(node.title_short||id).substring(0,28);
      grp.appendChild(lt);
    }}
    svgEl.appendChild(grp);
  }});
}}

/* ════════════════════════════════════════
   PARTICLE SYSTEM
════════════════════════════════════════ */
const PARTICLES = [];
const P_MAX     = 60;
const P_SPEED   = 0.012;

function spawnParticle(srcPos, dstPos, ring) {{
  if (PARTICLES.length >= P_MAX) return;
  const clr = ring==='r1' ? '#38bdf8'
             :ring==='r2' ? '#34d399'
             :               '#94a3b8';
  PARTICLES.push({{
    sx:srcPos.x, sy:srcPos.y,
    dx:dstPos.x, dy:dstPos.y,
    t:Math.random(),    // start at random position along path
    spd: P_SPEED * (0.6 + Math.random()*.8),
    r: 1.5 + Math.random()*1.5,
    clr,
    alpha: .6 + Math.random()*.4,
    trail: [],
  }});
}}

function updateParticles() {{
  for (let i = PARTICLES.length-1; i>=0; i--) {{
    const p = PARTICLES[i];
    p.trail.push({{x:lerp(p.sx,p.dx,p.t), y:lerp(p.sy,p.dy,p.t)}});
    if (p.trail.length > 6) p.trail.shift();
    p.t += p.spd;
    if (p.t > 1) PARTICLES.splice(i,1);
  }}
}}

function lerp(a,b,t) {{ return a + (b-a)*t; }}

function drawParticles() {{
  const cv  = document.getElementById('cv');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  if (!S.showPart) return;

  PARTICLES.forEach(p => {{
    const x = lerp(p.sx,p.dx,p.t);
    const y = lerp(p.sy,p.dy,p.t);
    // Trail
    if (p.trail.length > 1) {{
      ctx.beginPath();
      ctx.moveTo(p.trail[0].x, p.trail[0].y);
      p.trail.forEach(pt => ctx.lineTo(pt.x,pt.y));
      ctx.strokeStyle = p.clr + '44';
      ctx.lineWidth   = p.r * .6;
      ctx.stroke();
    }}
    // Core
    const grd = ctx.createRadialGradient(x,y,0,x,y,p.r*2);
    grd.addColorStop(0, p.clr + 'ff');
    grd.addColorStop(1, p.clr + '00');
    ctx.beginPath();
    ctx.arc(x,y,p.r*2,0,Math.PI*2);
    ctx.fillStyle = grd;
    ctx.fill();
  }});
}}

let _partTick = 0;
function tickParticles() {{
  _partTick++;
  // Spawn particles from current edges every N frames
  if (_partTick % 8 === 0 && S.showPart) {{
    const cfg = D.configs[S.center];
    if (!cfg) return;
    const layout = computeLayout(S.center, W(), H());
    const {{pos}} = layout;
    // Pick a random edge and spawn a particle
    const edges = cfg.edges;
    if (!edges.length) return;
    const e = edges[Math.floor(Math.random()*edges.length)];
    const a = pos[e.src], b = pos[e.dst];
    if (a && b) spawnParticle(a, b, e.type);
  }}
}}

/* ════════════════════════════════════════
   MAIN RENDER
════════════════════════════════════════ */
function renderMain() {{
  const w = W(), h = H();
  const layout = computeLayout(S.center, w, h);
  const pmap   = allNodesForCenter(S.center);

  drawOrbits(document.getElementById('g-orbits'), layout);
  drawEdges (document.getElementById('g-edges'),  layout, pmap);
  drawNodes (document.getElementById('g-nodes'),  layout, pmap);
}}

/* ════════════════════════════════════════
   ANIMATION LOOP
════════════════════════════════════════ */
function animLoop() {{
  tickParticles();
  updateParticles();
  drawParticles();
  requestAnimationFrame(animLoop);
}}

/* ════════════════════════════════════════
   POPULATE SELECTORS
════════════════════════════════════════ */
function populateSelectors() {{
  const opts = D.papers.map(p =>
    `<option value="${{safeText(p.id)}}">${{safeText(p.title_short||p.id.substring(0,35))}}</option>`
  ).join('');

  document.getElementById('paper-sel').innerHTML = opts;
  document.getElementById('paper-sel').value     = S.center;

  document.getElementById('cmp-sel-a').innerHTML = opts;
  document.getElementById('cmp-sel-b').innerHTML = opts;
  const p2 = D.papers[1];
  document.getElementById('cmp-sel-a').value = S.compareA;
  document.getElementById('cmp-sel-b').value = p2 ? p2.id : S.compareB;
}}

/* ════════════════════════════════════════
   CANVAS RESIZE
════════════════════════════════════════ */
function resizeCanvas() {{
  const cv = document.getElementById('cv');
  cv.width  = W();
  cv.height = H();
}}

/* ════════════════════════════════════════
   CLICK OUTSIDE → clear focus
════════════════════════════════════════ */
document.getElementById('svg').addEventListener('click', ev => {{
  if (ev.target.tagName === 'svg' || ev.target.tagName === 'rect') closePanel();
}});

/* ════════════════════════════════════════
   RESIZE
════════════════════════════════════════ */
let _resizeT;
window.addEventListener('resize', () => {{
  clearTimeout(_resizeT);
  _resizeT = setTimeout(() => {{
    resizeCanvas();
    renderMain();
  }}, 90);
}});

/* ════════════════════════════════════════
   INIT
════════════════════════════════════════ */
function init() {{
  resizeCanvas();
  populateSelectors();
  renderMain();
  updateStats();
  requestAnimationFrame(animLoop);
}}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : setTimeout(init, 60);
</script>
</body>
</html>"""
