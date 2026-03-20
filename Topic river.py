"""
topic_river.py
==============
Research Topic River — 3-Panel Futuristic Dashboard

Panel Kiri  : Velocity Ranking (kecepatan pertumbuhan tiap keyword)
Panel Tengah: Streamgraph SVG (sejarah volume topik, smooth bezier)
Panel Kanan : 2-Year Forecast (proyeksi linear + confidence score)

Interaksi:
  · Klik keyword di panel kiri → highlight semua panel serentak
  · Hover streamgraph → crosshair + tooltip multi-keyword
  · Forecast update otomatis saat keyword dipilih

Fungsi publik:
  render_topic_river(papers, height=620) → str  (HTML siap embed Streamlit)
  river_stats(papers)                    → dict (untuk metric cards)
"""

import re
import math
import json
import collections
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# 1. STOPWORDS
# ─────────────────────────────────────────────────────────────────

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
    "significant","significantly","improve","improves","improved","performance",
    "achieve","evaluate","experiment","dataset","benchmark","clinical","patients",
})


# ─────────────────────────────────────────────────────────────────
# 2. DATA PROCESSING
# ─────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _top_keywords(papers: list[dict], n: int = 8) -> list[str]:
    freq: collections.Counter = collections.Counter()
    for p in papers:
        text = (p.get("title", "") or "") + " " + (p.get("abstract", "") or "")
        for t in _tokenize(text):
            freq[t] += 1
    return [kw for kw, _ in freq.most_common(n)]


def _linreg(xs: list, ys: list) -> tuple[float, float]:
    """Return (intercept, slope) of least-squares line."""
    n = len(xs)
    if n < 2:
        return (ys[-1] if ys else 0.0), 0.0
    sx  = sum(xs);  sy  = sum(ys)
    sxx = sum(x*x for x in xs)
    sxy = sum(x*y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return sy / n, 0.0
    slope     = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return intercept, slope


def _r_squared(xs: list, ys: list, intercept: float, slope: float) -> float:
    if len(ys) < 2:
        return 0.0
    mean_y   = sum(ys) / len(ys)
    ss_tot   = sum((y - mean_y) ** 2 for y in ys)
    ss_res   = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    if ss_tot == 0:
        return 1.0
    return max(0.0, min(1.0, 1 - ss_res / ss_tot))


def _interpolate(vals: list[float], years: list[int]) -> list[float]:
    """Fill zero gaps between non-zero values using linear interpolation."""
    result = list(vals)
    n = len(result)
    # Forward fill first non-zero
    first_nz = next((i for i, v in enumerate(result) if v > 0), None)
    if first_nz is None:
        return result
    # Interpolate between non-zero pairs
    i = first_nz
    while i < n:
        if result[i] == 0:
            # Find next non-zero
            j = i + 1
            while j < n and result[j] == 0:
                j += 1
            if j < n:
                # Interpolate i..j
                for k in range(i, j):
                    t = (k - (i - 1)) / (j - (i - 1))
                    result[k] = result[i - 1] * (1 - t) + result[j] * t
            i = j
        else:
            i += 1
    return result


def _build_river_data(papers: list[dict]) -> Optional[dict]:
    keywords = _top_keywords(papers, n=8)
    if not keywords:
        return None

    years = sorted(set(
        int(p["year"]) for p in papers
        if str(p.get("year", "")).isdigit() and 1900 < int(p["year"]) <= 2030
    ))
    if len(years) < 2:
        return None

    nK, nY = len(keywords), len(years)
    year_idx = {y: i for i, y in enumerate(years)}

    # Raw frequency matrix [ki][yi]
    freq_raw = [[0] * nY for _ in range(nK)]
    for p in papers:
        yr = p.get("year", "")
        if not str(yr).isdigit():
            continue
        y = int(yr)
        if y not in year_idx:
            continue
        yi   = year_idx[y]
        text = (p.get("title", "") or "") + " " + (p.get("abstract", "") or "")
        toks = _tokenize(text)
        n_tok = len(toks) or 1
        cnt  = collections.Counter(toks)
        for ki, kw in enumerate(keywords):
            # Use TF: occurrences / total tokens, scaled ×100
            freq_raw[ki][yi] += round(cnt.get(kw, 0) / n_tok * 100, 3)

    # Smooth gaps with interpolation
    freq_smooth = [_interpolate(freq_raw[ki], years) for ki in range(nK)]

    # Normalize so max stack per year = 1
    year_totals = []
    for yi in range(nY):
        year_totals.append(sum(freq_smooth[ki][yi] for ki in range(nK)) or 1)
    max_total = max(year_totals)
    freq_norm = [[freq_smooth[ki][yi] / max_total for yi in range(nY)] for ki in range(nK)]

    # ── Velocity: avg(last 2 years) − avg(prev 2 years)
    velocity = []
    for ki, kw in enumerate(keywords):
        vals = freq_smooth[ki]
        if nY >= 4:
            recent = sum(vals[-2:]) / 2
            prev   = sum(vals[-4:-2]) / 2
        elif nY >= 2:
            recent, prev = vals[-1], vals[-2]
        else:
            recent, prev = vals[-1], 0.0
        vel = recent - prev

        # Sparkline: last 4 years raw (normalized locally)
        spark_raw = [freq_raw[ki][max(0, nY - 4 + j)] for j in range(4)]
        spark_max = max(spark_raw) or 1
        sparkline = [round(v / spark_max, 3) for v in spark_raw]

        velocity.append({
            "kw":        kw,
            "ki":        ki,
            "vel":       round(vel, 3),
            "trend":     "hot"    if vel > 0.3 else
                         "cold"   if vel < -0.3 else "stable",
            "sparkline": sparkline,
        })

    # Sort by absolute velocity (biggest change first)
    velocity.sort(key=lambda x: -abs(x["vel"]))
    max_vel = max(abs(v["vel"]) for v in velocity) or 1
    for v in velocity:
        v["vel_norm"] = round(abs(v["vel"]) / max_vel, 3)

    # ── Forecast: linear regression on last 4 years
    future_years = [years[-1] + 1, years[-1] + 2]
    forecast_freq = []
    confidence    = []
    for ki in range(nK):
        vals   = freq_raw[ki]
        use_n  = min(4, nY)
        xs     = list(range(use_n))
        ys     = vals[-use_n:]
        intercept, slope = _linreg(xs, ys)
        r2 = _r_squared(xs, ys, intercept, slope)
        proj = [max(0.0, round(intercept + slope * (use_n + i), 3))
                for i in range(2)]
        forecast_freq.append(proj)
        confidence.append(round(r2 * 100))

    # Recent actual (last 2 years) for comparison bars
    recent_freq = [[freq_raw[ki][max(0, nY - 2 + j)] for j in range(2)]
                   for ki in range(nK)]

    COLORS = [
        "#00d4ff", "#b39dfa", "#ff7a1a", "#00ffaa",
        "#f472b6", "#facc15", "#4ade80", "#f87171",
    ]

    return {
        "keywords":      keywords,
        "colors":        COLORS[:nK],
        "years":         years,
        "freq":          freq_norm,
        "freq_raw":      freq_raw,
        "velocity":      velocity,
        "forecast_years":  future_years,
        "forecast_freq":   forecast_freq,
        "recent_years":    years[-2:],
        "recent_freq":     recent_freq,
        "confidence":      confidence,
    }


def river_stats(papers: list[dict]) -> dict:
    """Metric cards for Streamlit UI."""
    data = _build_river_data(papers)
    if not data:
        return {}
    top_hot  = next((v for v in data["velocity"] if v["trend"] == "hot"),  None)
    top_cold = next((v for v in data["velocity"] if v["trend"] == "cold"), None)
    return {
        "total_keywords": len(data["keywords"]),
        "year_span":      f"{data['years'][0]} – {data['years'][-1]}",
        "top_rising":     top_hot["kw"]  if top_hot  else "—",
        "top_declining":  top_cold["kw"] if top_cold else "—",
    }


# ─────────────────────────────────────────────────────────────────
# 3. HTML RENDER
# ─────────────────────────────────────────────────────────────────

def render_topic_river(papers: list[dict], height: int = 620) -> str:
    data = _build_river_data(papers)
    if not data:
        return "<div style='color:#7aa8cc;font-family:monospace;padding:20px'>Tidak cukup data untuk Topic River (butuh minimal 2 tahun berbeda).</div>"

    data_json = (
        json.dumps(data, ensure_ascii=False)
        .replace("<", r"\u003c")
        .replace("/", r"\/")
    )
    H = height

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{H}px;overflow:hidden;
  background:#030d1a;color:#c8daf0;
  font-family:'Inter',sans-serif;
  user-select:none;
}}
:root{{
  --bg:      #030d1a;
  --bg2:     #061526;
  --bg3:     #081f38;
  --border:  rgba(0,212,255,.14);
  --border2: rgba(0,212,255,.28);
  --glow:    rgba(0,212,255,.55);
  --text-hi: #e8f4ff;
  --text-mid:#7aa8cc;
  --text-lo: #2d5070;
  --cyan:    #00d4ff;
  --purple:  #b39dfa;
  --orange:  #ff7a1a;
  --green:   #00ffaa;
  --mono:    'JetBrains Mono',monospace;
  --disp:    'Orbitron',monospace;
  --sans:    'Inter',sans-serif;
}}

/* ── Root ── */
#rw{{
  display:flex;flex-direction:column;
  width:100%;height:{H}px;
  background:var(--bg);
  position:relative;overflow:hidden;
}}
/* Ambient glow top-left */
#rw::before{{
  content:'';position:absolute;
  top:-60px;left:-60px;width:320px;height:320px;
  background:radial-gradient(circle, rgba(0,180,255,.07) 0%, transparent 70%);
  pointer-events:none;z-index:0;
}}
/* Scanline texture */
#rw::after{{
  content:'';position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(
    0deg,transparent,transparent 2px,
    rgba(0,0,0,.06) 2px,rgba(0,0,0,.06) 3px
  );
}}

/* ── Header bar ── */
#hdr{{
  flex-shrink:0;height:42px;
  display:flex;align-items:center;gap:14px;
  padding:0 18px;
  background:rgba(3,15,30,.98);
  border-bottom:1px solid var(--border);
  z-index:20;position:relative;
}}
.hdr-title{{
  font-family:var(--disp);font-size:11px;font-weight:700;
  letter-spacing:3px;color:var(--cyan);
  text-shadow:0 0 14px rgba(0,212,255,.5);
}}
.hdr-sep{{width:1px;height:18px;background:var(--border);}}
.hdr-sub{{
  font-family:var(--mono);font-size:9px;color:var(--text-lo);
  letter-spacing:1.5px;
}}
.live-dot{{
  width:7px;height:7px;border-radius:50%;
  background:var(--green);margin-left:auto;
  box-shadow:0 0 8px var(--green);
  animation:pulse-dot 2s ease-in-out infinite;
}}
@keyframes pulse-dot{{
  0%,100%{{opacity:1;transform:scale(1);}}
  50%{{opacity:.4;transform:scale(.7);}}
}}
.hdr-live{{
  font-family:var(--mono);font-size:8px;color:var(--green);
  letter-spacing:2px;
}}

/* ── 3-panel body ── */
#body{{
  flex:1;display:flex;
  min-height:0;position:relative;z-index:2;
}}

/* ── Panel base ── */
.panel{{
  display:flex;flex-direction:column;
  overflow:hidden;position:relative;
}}
.panel-hdr{{
  flex-shrink:0;padding:10px 14px 8px;
  border-bottom:1px solid var(--border);
  background:rgba(3,15,30,.7);
}}
.panel-title{{
  font-family:var(--disp);font-size:9px;font-weight:700;
  letter-spacing:3px;color:var(--text-mid);
  text-transform:uppercase;
}}
.panel-sub{{
  font-family:var(--mono);font-size:8px;color:var(--text-lo);
  margin-top:3px;letter-spacing:.5px;
}}
.panel-body{{
  flex:1;overflow:hidden;position:relative;
}}

/* ── Panel Left ── */
#pl{{
  width:230px;flex-shrink:0;
  border-right:1px solid var(--border);
}}
#vel-list{{
  height:100%;overflow-y:auto;padding:8px 0;
}}
#vel-list::-webkit-scrollbar{{width:3px;}}
#vel-list::-webkit-scrollbar-track{{background:transparent;}}
#vel-list::-webkit-scrollbar-thumb{{background:rgba(0,212,255,.2);border-radius:3px;}}

/* Velocity card */
.vcard{{
  padding:9px 14px;cursor:pointer;
  border-left:3px solid transparent;
  transition:background .15s,border-color .15s;
  position:relative;
}}
.vcard:hover{{background:rgba(0,212,255,.04);}}
.vcard.active{{
  border-left-color:var(--cc,var(--cyan));
  background:rgba(0,212,255,.07);
}}
.vcard.active .vc-kw{{color:var(--text-hi);}}

.vc-top{{display:flex;align-items:center;gap:7px;margin-bottom:6px;}}
.vc-rank{{
  font-family:var(--mono);font-size:9px;color:var(--text-lo);
  width:16px;text-align:right;flex-shrink:0;
}}
.vc-kw{{
  font-family:var(--mono);font-size:12px;font-weight:600;
  color:var(--cc,var(--cyan));
  letter-spacing:.5px;flex:1;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}}
.vc-badge{{
  font-family:var(--mono);font-size:7px;letter-spacing:1.5px;
  padding:2px 6px;border-radius:3px;font-weight:700;
  flex-shrink:0;
}}
.badge-hot{{
  background:rgba(255,122,26,.15);color:var(--orange);
  border:1px solid rgba(255,122,26,.3);
}}
.badge-cold{{
  background:rgba(0,180,255,.1);color:var(--cyan);
  border:1px solid rgba(0,180,255,.25);
}}
.badge-stable{{
  background:rgba(100,130,160,.1);color:var(--text-lo);
  border:1px solid rgba(100,130,160,.2);
}}

/* Velocity bar */
.vc-bar-wrap{{
  display:flex;align-items:center;gap:7px;margin-bottom:5px;
}}
.vc-vel-lbl{{
  font-family:var(--mono);font-size:10px;font-weight:600;
  min-width:38px;text-align:right;flex-shrink:0;
}}
.vc-bar-bg{{
  flex:1;height:4px;
  background:rgba(255,255,255,.05);border-radius:2px;overflow:hidden;
}}
.vc-bar-fill{{
  height:100%;border-radius:2px;
  transition:width .6s cubic-bezier(.4,0,.2,1);
}}

/* Sparkline */
.vc-spark{{
  width:100%;height:18px;
}}

/* ── Panel Middle ── */
#pm{{flex:1;border-right:1px solid var(--border);}}
#sv-wrap{{
  position:absolute;inset:0;padding:8px 10px 28px 40px;
}}
#sv{{width:100%;height:100%;overflow:visible;}}
/* SVG elements */
.stream-path{{
  transition:opacity .3s,filter .3s;
  cursor:crosshair;
}}
.stream-path.dimmed{{opacity:.06;filter:none;}}
.stream-path.bright{{
  filter:drop-shadow(0 0 8px var(--cc));
}}
.x-tick{{
  font-family:var(--mono);font-size:9px;fill:#2d5070;text-anchor:middle;
}}
.crosshair{{stroke:rgba(0,212,255,.4);stroke-width:1;stroke-dasharray:4 3;}}

/* Tooltip */
#tip{{
  position:absolute;display:none;pointer-events:none;
  background:rgba(3,15,30,.97);
  border:1px solid rgba(0,212,255,.3);border-radius:8px;
  padding:10px 13px;min-width:160px;
  box-shadow:0 8px 32px rgba(0,0,0,.75),0 0 16px rgba(0,212,255,.05);
  backdrop-filter:blur(12px);z-index:50;
}}
.tip-year{{
  font-family:var(--disp);font-size:10px;color:var(--cyan);
  letter-spacing:2px;margin-bottom:7px;
  border-bottom:1px solid rgba(0,212,255,.15);padding-bottom:5px;
}}
.tip-row{{
  display:flex;align-items:center;gap:7px;
  font-family:var(--mono);font-size:10px;margin-bottom:3px;
}}
.tip-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}
.tip-kw{{flex:1;color:var(--text-mid);}}
.tip-val{{color:var(--text-hi);font-weight:600;}}

/* ── Panel Right ── */
#pr{{width:220px;flex-shrink:0;}}
#fc-wrap{{
  position:absolute;inset:0;
  padding:10px 14px;
  display:flex;flex-direction:column;gap:0;
  overflow-y:auto;
}}
#fc-wrap::-webkit-scrollbar{{width:3px;}}
#fc-wrap::-webkit-scrollbar-thumb{{background:rgba(0,212,255,.15);border-radius:3px;}}

.fc-kw-title{{
  font-family:var(--mono);font-size:11px;font-weight:600;
  letter-spacing:.5px;margin-bottom:4px;
}}
.fc-conf{{
  font-family:var(--mono);font-size:8.5px;color:var(--text-lo);
  margin-bottom:12px;
}}
.fc-conf span{{color:var(--green);}}

.fc-bars{{display:flex;flex-direction:column;gap:8px;}}
.fc-bar-row{{display:flex;flex-direction:column;gap:3px;}}
.fc-bar-label{{
  font-family:var(--mono);font-size:9px;color:var(--text-mid);
  display:flex;justify-content:space-between;align-items:center;
}}
.fc-bar-lbl-type{{
  font-size:7.5px;letter-spacing:1px;
  padding:1px 5px;border-radius:2px;
}}
.lbl-actual{{background:rgba(0,212,255,.1);color:var(--cyan);}}
.lbl-forecast{{background:rgba(179,157,250,.1);color:var(--purple);}}

.fc-bar-track{{
  height:10px;background:rgba(255,255,255,.04);
  border-radius:3px;overflow:hidden;position:relative;
}}
.fc-bar-fill{{
  height:100%;border-radius:3px;
  transition:width .7s cubic-bezier(.4,0,.2,1);
}}
.fc-bar-fill.actual{{
  background:linear-gradient(90deg,var(--cyan),rgba(0,180,200,.7));
}}
.fc-bar-fill.forecast{{
  background:repeating-linear-gradient(
    90deg,
    rgba(179,157,250,.6) 0px,rgba(179,157,250,.6) 6px,
    transparent 6px,transparent 10px
  );
}}
.fc-divider{{
  width:100%;height:1px;background:var(--border);
  margin:12px 0;
}}
.fc-hint{{
  font-family:var(--mono);font-size:8px;color:var(--text-lo);
  letter-spacing:.5px;line-height:1.5;margin-top:8px;
}}

/* ── Glow filters ── */
</style>
</head>
<body>
<div id="rw">

<!-- Header -->
<div id="hdr">
  <span class="hdr-title">TOPIC RIVER</span>
  <div class="hdr-sep"></div>
  <span class="hdr-sub">RESEARCH MOMENTUM ANALYSIS</span>
  <div class="live-dot" style="margin-left:auto"></div>
  <span class="hdr-live">LIVE</span>
</div>

<!-- Body: 3 panels -->
<div id="body">

  <!-- Left: Velocity Ranking -->
  <div class="panel" id="pl">
    <div class="panel-hdr">
      <div class="panel-title">Velocity Ranking</div>
      <div class="panel-sub">Kecepatan perubahan topik</div>
    </div>
    <div class="panel-body">
      <div id="vel-list"></div>
    </div>
  </div>

  <!-- Middle: Streamgraph -->
  <div class="panel" id="pm">
    <div class="panel-hdr" style="display:flex;justify-content:space-between;align-items:center">
      <div>
        <div class="panel-title">Topic River</div>
        <div class="panel-sub">Evolusi volume topik dari waktu ke waktu</div>
      </div>
      <div id="river-hint" style="font-family:var(--mono);font-size:8px;color:var(--text-lo)">
        hover = detail &nbsp;·&nbsp; klik keyword kiri = focus
      </div>
    </div>
    <div class="panel-body" id="pm-body">
      <div id="sv-wrap">
        <svg id="sv" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <filter id="glow-sm" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="b"/>
              <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>
          <g id="g-streams"></g>
          <g id="g-axis"></g>
          <g id="g-cross" visibility="hidden">
            <line id="vline" class="crosshair" y1="0" y2="1"/>
          </g>
        </svg>
      </div>
      <div id="tip"></div>
    </div>
  </div>

  <!-- Right: Forecast -->
  <div class="panel" id="pr">
    <div class="panel-hdr">
      <div class="panel-title">2-Year Forecast</div>
      <div class="panel-sub">Proyeksi tren berbasis regresi linear</div>
    </div>
    <div class="panel-body">
      <div id="fc-wrap"></div>
    </div>
  </div>

</div><!-- #body -->
</div><!-- #rw -->

<script>
/* ════════════════════════════════════════
   DATA
════════════════════════════════════════ */
const D = {data_json};

/* ════════════════════════════════════════
   STATE
════════════════════════════════════════ */
let SEL = null;   // selected keyword index (null = all)

/* ════════════════════════════════════════
   HELPERS
════════════════════════════════════════ */
function ns(tag, a={{}}) {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(a).forEach(([k,v]) => el.setAttribute(k, v));
  return el;
}}
function esc(s) {{
  return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}
function fmt(v) {{
  return v > 10 ? v.toFixed(0) : v.toFixed(2);
}}

/* Cardinal spline: smooth bezier through points [[x,y], ...] */
function cspline(pts, tension=0.38) {{
  if (pts.length < 2) return '';
  let d = `M${{pts[0][0].toFixed(1)}},${{pts[0][1].toFixed(1)}}`;
  for (let i = 0; i < pts.length - 1; i++) {{
    const p0 = pts[Math.max(0, i-1)];
    const p1 = pts[i];
    const p2 = pts[i+1];
    const p3 = pts[Math.min(pts.length-1, i+2)];
    const cp1x = p1[0] + (p2[0]-p0[0]) * tension / 3;
    const cp1y = p1[1] + (p2[1]-p0[1]) * tension / 3;
    const cp2x = p2[0] - (p3[0]-p1[0]) * tension / 3;
    const cp2y = p2[1] - (p3[1]-p1[1]) * tension / 3;
    d += ` C${{cp1x.toFixed(1)}},${{cp1y.toFixed(1)}} ${{cp2x.toFixed(1)}},${{cp2y.toFixed(1)}} ${{p2[0].toFixed(1)}},${{p2[1].toFixed(1)}}`;
  }}
  return d;
}}

/* Hex → rgba */
function hexA(hex, a) {{
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  return `rgba(${{r}},${{g}},${{b}},${{a}})`;
}}

/* ════════════════════════════════════════
   SELECT
════════════════════════════════════════ */
function select(ki) {{
  SEL = (SEL === ki) ? null : ki;
  renderLeft();
  renderMiddle();
  renderRight();
}}

/* ════════════════════════════════════════
   PANEL LEFT — VELOCITY
════════════════════════════════════════ */
function renderLeft() {{
  const list = document.getElementById('vel-list');
  list.innerHTML = '';

  D.velocity.forEach((v, rank) => {{
    const ki  = v.ki;
    const clr = D.colors[ki];
    const isActive = SEL === ki;
    const isOther  = SEL !== null && SEL !== ki;

    const card = document.createElement('div');
    card.className = 'vcard' + (isActive ? ' active' : '');
    card.style.setProperty('--cc', clr);
    card.style.opacity = isOther ? '0.35' : '1';
    card.addEventListener('click', () => select(ki));

    const velSign   = v.vel >= 0 ? '+' : '';
    const velColor  = v.vel > 0.3 ? '#ff7a1a' : v.vel < -0.3 ? '#00d4ff' : '#7aa8cc';
    const badgeCls  = v.trend === 'hot' ? 'badge-hot' : v.trend === 'cold' ? 'badge-cold' : 'badge-stable';
    const badgeTxt  = v.trend === 'hot' ? 'NAIK' : v.trend === 'cold' ? 'TURUN' : 'STABIL';
    const barColor  = v.vel > 0 ? '#ff7a1a' : '#00d4ff';
    const barW      = Math.round(v.vel_norm * 100);

    // Sparkline SVG
    const spW = 180, spH = 18;
    const spPts = v.sparkline.map((sv, si) => [
      Math.round((si / (v.sparkline.length-1)) * spW),
      Math.round((1 - sv) * (spH - 4) + 2)
    ]);
    let spPath = '';
    if (spPts.length > 1) {{
      spPath = cspline(spPts, 0.3);
    }}

    card.innerHTML = `
      <div class="vc-top">
        <span class="vc-rank">${{rank+1}}</span>
        <span class="vc-kw">${{esc(v.kw.toUpperCase())}}</span>
        <span class="vc-badge ${{badgeCls}}">${{badgeTxt}}</span>
      </div>
      <div class="vc-bar-wrap">
        <span class="vc-vel-lbl" style="color:${{velColor}}">${{velSign}}${{v.vel.toFixed(2)}}</span>
        <div class="vc-bar-bg">
          <div class="vc-bar-fill"
               style="width:${{barW}}%;background:${{barColor}};
                      box-shadow:0 0 6px ${{hexA(barColor,.5)}}">
          </div>
        </div>
      </div>
      <svg class="vc-spark" viewBox="0 0 ${{spW}} ${{spH}}" preserveAspectRatio="none">
        ${{spPath ? `<path d="${{spPath}}" fill="none" stroke="${{clr}}" stroke-width="1.4" opacity=".6"/>` : ''}}
        ${{spPts.map(p=>`<circle cx="${{p[0]}}" cy="${{p[1]}}" r="2" fill="${{clr}}" opacity=".8"/>`).join('')}}
      </svg>
    `;
    list.appendChild(card);
  }});
}}

/* ════════════════════════════════════════
   PANEL MIDDLE — STREAMGRAPH
════════════════════════════════════════ */
function renderMiddle() {{
  const wrap = document.getElementById('sv-wrap');
  const W    = wrap.clientWidth;
  const H    = wrap.clientHeight;
  const PAD  = {{l:44, r:10, t:12, b:28}};
  const pW   = W - PAD.l - PAD.r;
  const pH   = H - PAD.t - PAD.b;

  const nY = D.years.length;
  const nK = D.keywords.length;

  function xOf(yi) {{ return PAD.l + (yi / (nY-1)) * pW; }}

  // Stacked cumulative [ki][yi]
  const stack = [];
  const cum   = new Array(nY).fill(0);
  for (let ki = 0; ki < nK; ki++) {{
    const top = cum.map((c, yi) => c + D.freq[ki][yi]);
    stack.push({{ bot: [...cum], top: [...top] }});
    for (let yi = 0; yi < nY; yi++) cum[yi] = top[yi];
  }}
  const maxY = Math.max(...cum) || 1;
  function yOf(v) {{ return PAD.t + pH - (v / maxY) * pH; }}

  // Resize SVG
  const svg = document.getElementById('sv');
  svg.setAttribute('viewBox', `0 0 ${{W}} ${{H}}`);
  svg.setAttribute('width',  W);
  svg.setAttribute('height', H);

  // ── Streams
  const gS = document.getElementById('g-streams');
  gS.innerHTML = '';

  for (let ki = nK-1; ki >= 0; ki--) {{
    const clr = D.colors[ki];
    const isActive = SEL === null || SEL === ki;
    const isBright = SEL === ki;

    const topPts = D.years.map((_,yi) => [xOf(yi), yOf(stack[ki].top[yi])]);
    const botRev = D.years.map((_,yi) => [xOf(yi), yOf(stack[ki].bot[yi])]).reverse();

    const topD = cspline(topPts);
    const botD = cspline(botRev).replace(/^M/, 'L');
    const d    = topD + ' ' + botD + ' Z';

    const path = ns('path', {{
      d,
      fill:            hexA(clr, isBright ? 0.72 : isActive ? 0.52 : 0.06),
      stroke:          clr,
      'stroke-width':  isBright ? '2' : '1',
      'stroke-opacity':isActive  ? (isBright ? '1' : '0.45') : '0.06',
      class:           'stream-path' + (!isActive ? ' dimmed' : isBright ? ' bright' : ''),
      'data-ki':       ki,
    }});
    if (isBright) path.setAttribute('filter', 'url(#glow-sm)');
    gS.appendChild(path);

    // Label at last year
    if (isActive && !isBright) {{
      const ly   = yOf((stack[ki].top[nY-1] + stack[ki].bot[nY-1]) / 2);
      const lblX = xOf(nY-1) - 4;
      if (stack[ki].top[nY-1] - stack[ki].bot[nY-1] > 0.04) {{
        const t = ns('text', {{
          x: lblX, y: ly,
          fill: clr,
          'font-family': "'JetBrains Mono',monospace",
          'font-size': '9',
          'text-anchor': 'end',
          'dominant-baseline': 'central',
          opacity: '.75',
        }});
        t.textContent = D.keywords[ki];
        gS.appendChild(t);
      }}
    }}
  }}

  // ── X Axis
  const gA = document.getElementById('g-axis');
  gA.innerHTML = '';
  const ay = PAD.t + pH + 2;
  gA.appendChild(ns('line', {{
    x1: PAD.l, y1: ay, x2: W - PAD.r, y2: ay,
    stroke: 'rgba(0,212,255,.12)'
  }}));
  D.years.forEach((yr, yi) => {{
    const x = xOf(yi);
    gA.appendChild(ns('line', {{x1:x,y1:ay,x2:x,y2:ay+4,stroke:'rgba(0,212,255,.2)'}}));
    const t = ns('text', {{x, y: ay+14, class:'x-tick'}});
    t.textContent = yr;
    gA.appendChild(t);
  }});

  // ── Crosshair vline sizing
  const vl = document.getElementById('vline');
  vl.setAttribute('x1', xOf(0));
  vl.setAttribute('x2', xOf(0));
  vl.setAttribute('y1', PAD.t);
  vl.setAttribute('y2', PAD.t + pH);
  vl.setAttribute('stroke', 'rgba(0,212,255,.5)');
  vl.setAttribute('stroke-width', '1');
  vl.setAttribute('stroke-dasharray', '4 3');

  // Store layout for hover
  svg._layout = {{PAD, pW, pH, nY, maxY, xOf, yOf, stack}};
}}

/* ════════════════════════════════════════
   STREAMGRAPH HOVER
════════════════════════════════════════ */
function setupHover() {{
  const wrap = document.getElementById('sv-wrap');
  const tip  = document.getElementById('tip');
  const gC   = document.getElementById('g-cross');
  const vl   = document.getElementById('vline');

  wrap.addEventListener('mousemove', e => {{
    const svg = document.getElementById('sv');
    const lay = svg._layout;
    if (!lay) return;

    const rect = wrap.getBoundingClientRect();
    const mx   = e.clientX - rect.left - lay.PAD.l;
    const nY   = D.years.length;

    // Snap to nearest year
    const yi = Math.max(0, Math.min(nY-1, Math.round(mx / lay.pW * (nY-1))));
    const x  = lay.xOf(yi);

    // Move crosshair
    gC.setAttribute('visibility', 'visible');
    vl.setAttribute('x1', x); vl.setAttribute('x2', x);

    // Build tooltip
    const yr    = D.years[yi];
    const rows  = D.keywords.map((kw, ki) => {{
      const raw = D.freq_raw[ki][yi];
      return {{kw, ki, raw, clr: D.colors[ki]}};
    }}).filter(r => r.raw > 0).sort((a,b) => b.raw - a.raw);

    if (rows.length === 0) {{ tip.style.display='none'; return; }}

    tip.innerHTML = `
      <div class="tip-year">${{yr}}</div>
      ${{rows.map(r => `
        <div class="tip-row">
          <span class="tip-dot" style="background:${{r.clr}}"></span>
          <span class="tip-kw">${{esc(r.kw)}}</span>
          <span class="tip-val">${{r.raw.toFixed(2)}}</span>
        </div>
      `).join('')}}
    `;

    // Position tooltip
    const tipW = 170, tipH = tip.offsetHeight || 120;
    let tx = e.clientX - rect.left + 14;
    let ty = e.clientY - rect.top  - 10;
    if (tx + tipW > wrap.clientWidth)  tx = e.clientX - rect.left - tipW - 10;
    if (ty + tipH > wrap.clientHeight) ty = e.clientY - rect.top  - tipH - 10;
    tip.style.cssText = `display:block;left:${{tx}}px;top:${{ty}}px`;
  }});

  wrap.addEventListener('mouseleave', () => {{
    document.getElementById('g-cross').setAttribute('visibility','hidden');
    tip.style.display = 'none';
  }});
}}

/* ════════════════════════════════════════
   PANEL RIGHT — FORECAST
════════════════════════════════════════ */
function renderRight() {{
  const wrap = document.getElementById('fc-wrap');
  wrap.innerHTML = '';

  const ki  = SEL ?? 0;   // default to first keyword
  const clr = D.colors[ki];
  const kw  = D.keywords[ki].toUpperCase();
  const conf= D.confidence[ki];

  // Header
  const hdr = document.createElement('div');
  hdr.innerHTML = `
    <div class="fc-kw-title" style="color:${{clr}}">${{esc(kw)}}</div>
    <div class="fc-conf">Confidence: <span>${{conf}}%</span>
      &nbsp;(${{conf>=70?'Tinggi':conf>=40?'Sedang':'Rendah'}})
    </div>
  `;
  wrap.appendChild(hdr);

  // Compute max for scaling
  const allVals = [
    ...D.recent_freq[ki],
    ...D.forecast_freq[ki],
  ];
  const maxVal = Math.max(...allVals) || 1;

  const barsDiv = document.createElement('div');
  barsDiv.className = 'fc-bars';

  // Recent years (actual)
  D.recent_years.forEach((yr, j) => {{
    const val = D.recent_freq[ki][j];
    const pct = Math.round(val / maxVal * 100);
    const row = document.createElement('div');
    row.className = 'fc-bar-row';
    row.innerHTML = `
      <div class="fc-bar-label">
        <span>${{yr}}</span>
        <span class="fc-bar-lbl-type lbl-actual">AKTUAL</span>
        <span style="color:var(--cyan);font-weight:600">${{val.toFixed(2)}}</span>
      </div>
      <div class="fc-bar-track">
        <div class="fc-bar-fill actual" style="width:${{pct}}%;
          box-shadow:0 0 8px ${{hexA(clr,.4)}}">
        </div>
      </div>
    `;
    barsDiv.appendChild(row);
  }});

  // Divider
  const div = document.createElement('div');
  div.className = 'fc-divider';
  barsDiv.appendChild(div);

  // Forecast years (projected)
  D.forecast_years.forEach((yr, j) => {{
    const val = D.forecast_freq[ki][j];
    const pct = Math.round(val / maxVal * 100);
    const row = document.createElement('div');
    row.className = 'fc-bar-row';
    row.innerHTML = `
      <div class="fc-bar-label">
        <span style="color:var(--purple)">${{yr}}</span>
        <span class="fc-bar-lbl-type lbl-forecast">PROYEKSI</span>
        <span style="color:var(--purple);font-weight:600">${{val.toFixed(2)}}</span>
      </div>
      <div class="fc-bar-track">
        <div class="fc-bar-fill forecast" style="width:${{pct}}%">
        </div>
      </div>
    `;
    barsDiv.appendChild(row);
  }});

  wrap.appendChild(barsDiv);

  // All keywords mini summary
  const allDiv = document.createElement('div');
  allDiv.innerHTML = `
    <div class="fc-divider"></div>
    <div style="font-family:var(--mono);font-size:8px;color:var(--text-lo);
                letter-spacing:1px;margin-bottom:8px">
      SEMUA KEYWORD — PROYEKSI ${{D.forecast_years[0]}}
    </div>
  `;
  // Mini bars for all keywords
  const allMax = Math.max(...D.forecast_freq.map(f => f[0])) || 1;
  D.keywords.forEach((kw2, ki2) => {{
    const val2 = D.forecast_freq[ki2][0];
    const pct2 = Math.round(val2 / allMax * 100);
    const clr2 = D.colors[ki2];
    const isS  = ki2 === ki;
    const row  = document.createElement('div');
    row.style.cssText = `display:flex;align-items:center;gap:6px;margin-bottom:5px;
      cursor:pointer;opacity:${{isS?'1':'0.5'}};`;
    row.innerHTML = `
      <span style="font-family:var(--mono);font-size:8.5px;color:${{clr2}};
                   width:72px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        ${{esc(kw2)}}
      </span>
      <div style="flex:1;height:5px;background:rgba(255,255,255,.04);border-radius:2px;overflow:hidden">
        <div style="width:${{pct2}}%;height:100%;background:${{clr2}};
                    border-radius:2px;opacity:.7;
                    transition:width .6s cubic-bezier(.4,0,.2,1)">
        </div>
      </div>
      <span style="font-family:var(--mono);font-size:8px;color:var(--text-lo);
                   min-width:28px;text-align:right">
        ${{val2.toFixed(1)}}
      </span>
    `;
    row.addEventListener('click', () => select(ki2));
    allDiv.appendChild(row);
  }});

  wrap.appendChild(allDiv);

  // Hint
  const hint = document.createElement('div');
  hint.className = 'fc-hint';
  hint.textContent = `Basis: regresi ${{Math.min(4,D.years.length)}} tahun terakhir · Klik keyword untuk ubah`;
  wrap.appendChild(hint);
}}

/* ════════════════════════════════════════
   INIT
════════════════════════════════════════ */
function init() {{
  renderLeft();
  renderMiddle();
  renderRight();
  setupHover();

  // Animate bars after render
  setTimeout(() => {{
    document.querySelectorAll('.vc-bar-fill').forEach(el => {{
      const w = el.style.width;
      el.style.width = '0%';
      requestAnimationFrame(() => {{
        requestAnimationFrame(() => {{ el.style.width = w; }});
      }});
    }});
  }}, 80);

  // Resize
  let rt;
  window.addEventListener('resize', () => {{
    clearTimeout(rt);
    rt = setTimeout(() => {{ renderMiddle(); }}, 120);
  }});
}}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : setTimeout(init, 60);
</script>
</body>
</html>"""
