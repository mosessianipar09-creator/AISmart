"""
contradiction_detector.py
=========================
Contradiction Detector — User memilih Paper A vs Paper B secara bebas.

Layout 3 panel:
  Kiri   = Paper A (dropdown + metadata + klaim)
  Tengah = Battle Arena (meter animasi + keyword battle + verdict)
  Kanan  = Paper B (dropdown + metadata + klaim)

Semua interaksi real-time di browser — ganti dropdown = semua update instan.

Fungsi publik:
  render_contradiction(papers, height=640) → str  HTML siap embed Streamlit
"""

import re
import json
import math
import collections
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# 1. NLP HELPERS
# ─────────────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","as","is","was","are","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","not",
    "this","that","these","those","it","its","we","our","their","they",
    "paper","study","research","propose","present","show","result","results",
    "approach","method","methods","using","used","use","based","novel","new",
    "existing","previous","however","also","which","such","than","more","most",
    "work","model","system","data","two","three","one","can","well",
    "significant","significantly","evaluate","experiment","dataset",
})

_POS_SIGNALS = [
    "improve","improves","improved","improvement","outperform","outperforms",
    "superior","better","effective","efficient","accurate","robust","strong",
    "significant","increase","enhance","advantage","promising","novel",
    "demonstrate","confirms","validates","supports","achieves","success",
    "beneficial","positive","high","greater","faster","larger","best",
]
_NEG_SIGNALS = [
    "fail","fails","failed","failure","poor","worse","inferior","ineffective",
    "inaccurate","weak","insignificant","decrease","limitation","drawback",
    "challenge","problem","issue","concern","limited","lacks","unable",
    "insufficient","low","smaller","slower","worst","negative","doubt",
]

_CONTRA_PAIRS = {
    frozenset(["improve","fail"]),
    frozenset(["effective","ineffective"]),
    frozenset(["accurate","inaccurate"]),
    frozenset(["robust","weak"]),
    frozenset(["superior","inferior"]),
    frozenset(["increase","decrease"]),
    frozenset(["high","low"]),
    frozenset(["strong","weak"]),
    frozenset(["better","worse"]),
    frozenset(["success","failure"]),
    frozenset(["beneficial","harmful"]),
    frozenset(["positive","negative"]),
    frozenset(["greater","smaller"]),
    frozenset(["faster","slower"]),
    frozenset(["best","worst"]),
    frozenset(["validates","challenges"]),
    frozenset(["supports","contradicts"]),
    frozenset(["confirms","refutes"]),
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _extract_claims(text: str, n: int = 4) -> list[str]:
    """Extract n key claim-like sentences from abstract."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Score each sentence by presence of signal words
    scored = []
    for s in sentences:
        sl = s.lower()
        score = 0
        for w in _POS_SIGNALS + _NEG_SIGNALS:
            if w in sl:
                score += 1
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    result = [s for _, s in scored[:n] if len(s) > 20]
    if not result:
        result = [s for s in sentences[:n] if len(s) > 20]
    return result[:n]


def _compute_battle(p1: dict, p2: dict) -> dict:
    """
    Compute full battle data between two papers.
    Returns dict with all data needed for the JS render.
    """
    text1 = ((p1.get("title") or "") + " " + (p1.get("abstract") or "")).lower()
    text2 = ((p2.get("title") or "") + " " + (p2.get("abstract") or "")).lower()

    tok1 = set(_tokenize(text1))
    tok2 = set(_tokenize(text2))

    # Shared keywords
    shared = sorted((tok1 & tok2) - _STOPWORDS)

    # Positive / negative signals per paper
    pos1 = [w for w in _POS_SIGNALS if w in text1]
    neg1 = [w for w in _NEG_SIGNALS if w in text1]
    pos2 = [w for w in _POS_SIGNALS if w in text2]
    neg2 = [w for w in _NEG_SIGNALS if w in text2]

    # Find actual contradiction pairs
    contra_found = []
    for w1 in (pos1 + neg1):
        for w2 in (pos2 + neg2):
            if frozenset([w1, w2]) in _CONTRA_PAIRS and w1 != w2:
                if w1 in pos1 and w2 in neg2:
                    contra_found.append({"a": w1, "b": w2, "dir": "A→positive, B→negative"})
                elif w1 in neg1 and w2 in pos2:
                    contra_found.append({"a": w1, "b": w2, "dir": "A→negative, B→positive"})

    # Deduplicate
    seen = set()
    contra_dedup = []
    for c in contra_found:
        key = frozenset([c["a"], c["b"]])
        if key not in seen:
            seen.add(key)
            contra_dedup.append(c)

    # Score components
    shared_score   = min(len(shared) * 3, 30)
    contra_score   = min(len(contra_dedup) * 18, 54)
    try:
        yr_gap     = abs(int(p1.get("year", 0) or 0) - int(p2.get("year", 0) or 0))
    except Exception:
        yr_gap = 0
    time_score     = min(yr_gap * 1, 16)
    conflict_score = min(100, shared_score + contra_score + time_score)

    # Verdict
    if conflict_score >= 65:
        verdict_level = "high"
        verdict_text  = (
            f"Paper ini menunjukkan KONTRADIKSI SIGNIFIKAN. "
            f"Keduanya membahas topik yang sama ({len(shared)} keyword bersama) "
            f"namun menggunakan sinyal yang berlawanan — "
            f"kemungkinan perbedaan metodologi, dataset, atau populasi studi."
        )
    elif conflict_score >= 35:
        verdict_level = "medium"
        verdict_text  = (
            f"Terdapat POTENSI PERBEDAAN antara kedua paper. "
            f"Keduanya berbagi {len(shared)} keyword namun beberapa klaim mungkin bertentangan. "
            f"Disarankan membaca kedua abstrak secara menyeluruh."
        )
    else:
        verdict_level = "low"
        verdict_text  = (
            f"Kedua paper relatif SEJALAN. "
            f"Mereka berbagi {len(shared)} keyword dan tidak menunjukkan sinyal yang secara eksplisit berlawanan. "
            f"Kemungkinan besar saling melengkapi."
        )

    # Claims
    claims1 = _extract_claims(p1.get("abstract") or p1.get("title") or "")
    claims2 = _extract_claims(p2.get("abstract") or p2.get("title") or "")

    return {
        "score":         conflict_score,
        "shared":        shared[:10],
        "pos1":          pos1[:6],
        "neg1":          neg1[:6],
        "pos2":          pos2[:6],
        "neg2":          neg2[:6],
        "contra":        contra_dedup[:6],
        "verdict_level": verdict_level,
        "verdict_text":  verdict_text,
        "claims1":       claims1,
        "claims2":       claims2,
    }


def _normalize_paper(p: dict, idx: int) -> dict:
    title    = (p.get("title") or "Untitled").strip()
    abstract = (p.get("abstract") or "").strip()
    try:
        cites = int(p.get("citations") or 0)
    except Exception:
        cites = 0
    try:
        year = int(p.get("year") or 0)
    except Exception:
        year = 0

    return {
        "id":       idx,
        "title":    title,
        "short":    (title[:60] + "…") if len(title) > 60 else title,
        "authors":  (p.get("authors") or "N/A")[:80],
        "year":     year or "?",
        "citations":cites,
        "venue":    (p.get("venue") or "Unknown")[:60],
        "abstract": abstract[:600] + ("…" if len(abstract) > 600 else ""),
        "source":   p.get("source") or "unknown",
        "link":     p.get("link") or "#",
    }


def render_contradiction(papers: list[dict], height: int = 640) -> str:
    if len(papers) < 2:
        return "<div style='color:#7aa8cc;font-family:monospace;padding:20px'>Butuh minimal 2 paper.</div>"

    norm = [_normalize_paper(p, i) for i, p in enumerate(papers)]

    # Pre-compute all pair battles (cached in JS)
    battles: dict[str, dict] = {}
    for i in range(len(norm)):
        for j in range(i + 1, len(norm)):
            key = f"{i}_{j}"
            battles[key] = _compute_battle(papers[i], papers[j])

    papers_json  = json.dumps(norm,    ensure_ascii=False).replace("<", r"\u003c").replace("/", r"\/")
    battles_json = json.dumps(battles, ensure_ascii=False).replace("<", r"\u003c").replace("/", r"\/")

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;overflow:hidden;
  background:#030c18;color:#c8daf0;
  font-family:'Inter',sans-serif;user-select:none;
}}
:root{{
  --bg:     #030c18;
  --bg2:    #061626;
  --bg3:    #0a1e35;
  --border: rgba(0,200,255,.13);
  --hi:     rgba(0,200,255,.28);
  --text-h: #e8f4ff;
  --text-m: #7aa8cc;
  --text-l: #2d5070;
  --cyan:   #00d4ff;
  --green:  #00ffaa;
  --red:    #ff4d6a;
  --amber:  #ffb830;
  --purple: #b39dfa;
  --mono:   'JetBrains Mono',monospace;
  --disp:   'Orbitron',monospace;
  --sans:   'Inter',sans-serif;
}}

/* scanlines */
body::after{{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:999;
  background:repeating-linear-gradient(
    0deg,transparent,transparent 2px,rgba(0,0,0,.05) 2px,rgba(0,0,0,.05) 3px
  );
}}

/* ── Header ── */
#hdr{{
  height:40px;display:flex;align-items:center;gap:14px;
  padding:0 16px;
  background:rgba(3,12,24,.98);
  border-bottom:1px solid var(--border);
  position:relative;z-index:10;
}}
.hdr-title{{
  font-family:var(--disp);font-size:11px;font-weight:700;
  letter-spacing:3px;color:var(--red);
  text-shadow:0 0 14px rgba(255,77,106,.5);
}}
.hdr-sep{{width:1px;height:18px;background:var(--border);}}
.hdr-sub{{font-family:var(--mono);font-size:8.5px;color:var(--text-l);letter-spacing:1.5px;}}
.hdr-count{{
  margin-left:auto;font-family:var(--mono);font-size:9px;
  color:var(--text-l);letter-spacing:1px;
}}

/* ── Body ── */
#body{{
  height:calc({height}px - 40px);
  display:flex;gap:0;
}}

/* ── Panel base ── */
.pnl{{
  display:flex;flex-direction:column;overflow:hidden;
}}

/* ── Paper panels (left / right) ── */
.paper-pnl{{
  width:282px;flex-shrink:0;
  border-right:1px solid var(--border);
}}
#pr.paper-pnl{{border-right:none;border-left:1px solid var(--border);}}

.pnl-hdr{{
  flex-shrink:0;padding:9px 12px 7px;
  border-bottom:1px solid var(--border);
  background:rgba(3,12,24,.7);
}}
.pnl-title{{
  font-family:var(--disp);font-size:8px;font-weight:700;
  letter-spacing:3px;text-transform:uppercase;
}}
.pnl-sub{{
  font-family:var(--mono);font-size:7.5px;color:var(--text-l);
  margin-top:2px;letter-spacing:.5px;
}}

/* Dropdown */
.paper-sel{{
  width:100%;margin-top:8px;
  background:rgba(6,22,38,.95);
  border:1px solid var(--border);border-radius:6px;
  color:var(--cyan);padding:7px 10px;
  font-family:var(--mono);font-size:10px;
  cursor:pointer;outline:none;
  appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2300d4ff'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center;
  padding-right:28px;
  transition:border-color .15s;
}}
.paper-sel:focus{{border-color:var(--hi);}}
.paper-sel option{{background:#061626;color:#c8daf0;}}

/* Paper info card */
.paper-info{{
  flex:1;overflow-y:auto;padding:10px 12px;
}}
.paper-info::-webkit-scrollbar{{width:3px;}}
.paper-info::-webkit-scrollbar-thumb{{background:rgba(0,200,255,.15);border-radius:3px;}}

.pi-title{{
  font-family:var(--sans);font-size:11.5px;font-weight:600;
  color:var(--text-h);line-height:1.4;margin-bottom:8px;
}}
.pi-meta{{
  display:flex;flex-wrap:wrap;gap:5px;margin-bottom:9px;
}}
.pi-chip{{
  font-family:var(--mono);font-size:8.5px;
  padding:2px 8px;border-radius:4px;
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.08);
  color:var(--text-m);
}}
.pi-chip.year{{color:var(--cyan);border-color:rgba(0,212,255,.2);background:rgba(0,212,255,.06);}}
.pi-chip.cite{{color:var(--amber);border-color:rgba(255,184,48,.2);background:rgba(255,184,48,.06);}}

.pi-section{{
  font-family:var(--mono);font-size:7.5px;letter-spacing:2px;
  color:var(--text-l);text-transform:uppercase;margin-bottom:5px;margin-top:9px;
}}
.pi-abstract{{
  font-family:var(--sans);font-size:10px;color:var(--text-m);
  line-height:1.55;
}}

/* Claims */
.claim-item{{
  display:flex;align-items:flex-start;gap:6px;
  margin-bottom:6px;
}}
.claim-dot{{
  width:5px;height:5px;border-radius:50%;margin-top:5px;flex-shrink:0;
}}
.claim-text{{
  font-family:var(--sans);font-size:9.5px;color:var(--text-m);
  line-height:1.45;
}}

/* Signal tags */
.sig-wrap{{display:flex;flex-wrap:wrap;gap:4px;}}
.sig-tag{{
  font-family:var(--mono);font-size:8px;
  padding:2px 7px;border-radius:3px;
  font-weight:600;letter-spacing:.5px;
}}
.sig-pos{{
  background:rgba(0,255,170,.08);color:var(--green);
  border:1px solid rgba(0,255,170,.2);
}}
.sig-neg{{
  background:rgba(255,77,106,.08);color:var(--red);
  border:1px solid rgba(255,77,106,.2);
}}

/* ── Battle Arena (center) ── */
#arena{{
  flex:1;
  display:flex;flex-direction:column;
  background:linear-gradient(180deg,#040e1c 0%,#030c18 100%);
  position:relative;overflow:hidden;
}}
/* Grid overlay */
#arena::before{{
  content:'';position:absolute;inset:0;pointer-events:none;
  background-image:
    linear-gradient(rgba(0,200,255,.03) 1px,transparent 1px),
    linear-gradient(90deg,rgba(0,200,255,.03) 1px,transparent 1px);
  background-size:32px 32px;
}}

.arena-hdr{{
  flex-shrink:0;padding:8px 14px 7px;
  border-bottom:1px solid var(--border);
  text-align:center;
  background:rgba(3,12,24,.6);
}}
.arena-title{{
  font-family:var(--disp);font-size:8px;font-weight:700;
  letter-spacing:3px;color:var(--amber);
  text-shadow:0 0 10px rgba(255,184,48,.3);
}}

.arena-body{{
  flex:1;display:flex;flex-direction:column;
  align-items:center;padding:16px 20px;
  gap:14px;overflow-y:auto;
  position:relative;z-index:1;
}}
.arena-body::-webkit-scrollbar{{width:3px;}}
.arena-body::-webkit-scrollbar-thumb{{background:rgba(0,200,255,.1);}}

/* ── Contradiction Meter ── */
#meter-wrap{{
  width:100%;display:flex;flex-direction:column;align-items:center;gap:6px;
}}
.meter-label{{
  font-family:var(--disp);font-size:9px;letter-spacing:2.5px;
  color:var(--text-l);text-transform:uppercase;
}}
.meter-track{{
  width:100%;height:22px;
  background:rgba(255,255,255,.04);
  border-radius:11px;overflow:hidden;
  border:1px solid rgba(255,255,255,.07);
  position:relative;
}}
.meter-fill{{
  height:100%;border-radius:11px;
  transition:width 1s cubic-bezier(.4,0,.2,1),background 1s;
  position:relative;
}}
.meter-fill::after{{
  content:'';position:absolute;inset:0;border-radius:11px;
  background:linear-gradient(90deg,transparent 0%,rgba(255,255,255,.15) 50%,transparent 100%);
  animation:sheen 2s ease-in-out infinite;
}}
@keyframes sheen{{
  0%{{transform:translateX(-100%);}}
  100%{{transform:translateX(100%);}}
}}
.meter-score{{
  font-family:var(--disp);font-size:28px;font-weight:700;
  letter-spacing:2px;
  transition:color .8s;
  line-height:1;
  text-shadow:0 0 20px currentColor;
}}
.meter-score-sub{{
  font-family:var(--mono);font-size:9px;color:var(--text-l);
  letter-spacing:2px;
}}
.meter-ticks{{
  width:100%;display:flex;justify-content:space-between;
  padding:0 2px;
}}
.meter-tick{{
  font-family:var(--mono);font-size:7.5px;color:var(--text-l);
}}

/* ── Verdict Badge ── */
#verdict{{
  width:100%;padding:11px 14px;border-radius:8px;
  border:1px solid;
  transition:all .6s;
}}
.verdict-level{{
  font-family:var(--disp);font-size:8.5px;font-weight:700;
  letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;
}}
.verdict-text{{
  font-family:var(--sans);font-size:10px;line-height:1.55;color:var(--text-m);
}}

/* ── Keyword Battle ── */
#kw-battle{{
  width:100%;
}}
.kb-title{{
  font-family:var(--mono);font-size:8px;letter-spacing:2px;
  color:var(--text-l);text-transform:uppercase;
  text-align:center;margin-bottom:8px;
}}
.kb-shared{{
  display:flex;flex-wrap:wrap;gap:4px;justify-content:center;
  margin-bottom:10px;
}}
.kb-shared-tag{{
  font-family:var(--mono);font-size:8.5px;
  padding:2px 8px;border-radius:4px;
  background:rgba(179,157,250,.09);
  border:1px solid rgba(179,157,250,.22);
  color:var(--purple);
}}
.kb-contra-list{{
  display:flex;flex-direction:column;gap:5px;
}}
.kb-contra-row{{
  display:flex;align-items:center;gap:0;
  border-radius:5px;overflow:hidden;
  border:1px solid rgba(255,255,255,.06);
}}
.kb-a{{
  flex:1;padding:5px 8px;text-align:right;
  background:rgba(0,255,170,.07);
  font-family:var(--mono);font-size:9px;color:var(--green);font-weight:600;
}}
.kb-vs{{
  padding:5px 7px;
  background:rgba(255,255,255,.04);
  font-family:var(--mono);font-size:7.5px;color:var(--text-l);
  border-left:1px solid rgba(255,255,255,.06);
  border-right:1px solid rgba(255,255,255,.06);
}}
.kb-b{{
  flex:1;padding:5px 8px;text-align:left;
  background:rgba(255,77,106,.07);
  font-family:var(--mono);font-size:9px;color:var(--red);font-weight:600;
}}

/* ── Empty state ── */
#empty-state{{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;gap:10px;opacity:.5;
}}
.es-icon{{font-size:32px;}}
.es-text{{font-family:var(--mono);font-size:10px;color:var(--text-l);letter-spacing:1px;text-align:center;}}

/* ── Swap button ── */
#btn-swap{{
  position:absolute;top:8px;right:12px;
  background:rgba(255,184,48,.08);
  border:1px solid rgba(255,184,48,.25);
  border-radius:5px;padding:4px 10px;
  font-family:var(--mono);font-size:8.5px;color:var(--amber);
  cursor:pointer;letter-spacing:.5px;
  transition:all .15s;z-index:5;
}}
#btn-swap:hover{{background:rgba(255,184,48,.18);border-color:var(--amber);}}
</style>
</head>
<body>

<!-- Header -->
<div id="hdr">
  <span class="hdr-title">⚡ CONTRADICTION DETECTOR</span>
  <div class="hdr-sep"></div>
  <span class="hdr-sub">PILIH 2 PAPER — ANALISIS REAL-TIME</span>
  <span class="hdr-count" id="paper-count"></span>
</div>

<!-- Body -->
<div id="body">

  <!-- Left: Paper A -->
  <div class="pnl paper-pnl" id="pl">
    <div class="pnl-hdr" style="border-top:2px solid var(--green)">
      <div class="pnl-title" style="color:var(--green)">◈ Paper A</div>
      <div class="pnl-sub">Pilih paper pertama</div>
      <select class="paper-sel" id="sel-a" onchange="onSelect()"></select>
    </div>
    <div class="paper-info" id="info-a">
      <div style="height:100%;display:flex;align-items:center;justify-content:center;opacity:.3">
        <span style="font-family:var(--mono);font-size:9px;color:var(--text-l)">Pilih paper di atas</span>
      </div>
    </div>
  </div>

  <!-- Center: Battle Arena -->
  <div class="pnl" id="arena">
    <div class="arena-hdr" style="position:relative">
      <div class="arena-title">⚔ BATTLE ARENA</div>
      <button id="btn-swap" onclick="swapPapers()">⇄ SWAP</button>
    </div>
    <div class="arena-body" id="arena-body">
      <div id="empty-state">
        <div class="es-icon">⚡</div>
        <div class="es-text">Pilih Paper A dan Paper B<br>untuk memulai analisis</div>
      </div>
    </div>
  </div>

  <!-- Right: Paper B -->
  <div class="pnl paper-pnl" id="pr">
    <div class="pnl-hdr" style="border-top:2px solid var(--red)">
      <div class="pnl-title" style="color:var(--red)">◈ Paper B</div>
      <div class="pnl-sub">Pilih paper kedua</div>
      <select class="paper-sel" id="sel-b" onchange="onSelect()"></select>
    </div>
    <div class="paper-info" id="info-b">
      <div style="height:100%;display:flex;align-items:center;justify-content:center;opacity:.3">
        <span style="font-family:var(--mono);font-size:9px;color:var(--text-l)">Pilih paper di atas</span>
      </div>
    </div>
  </div>

</div><!-- #body -->

<script>
/* ════════════════════
   DATA
════════════════════ */
const PAPERS  = {papers_json};
const BATTLES = {battles_json};

/* ════════════════════
   HELPERS
════════════════════ */
function esc(s){{
  return String(s??'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function getBattle(ia, ib){{
  if (ia === ib || ia < 0 || ib < 0) return null;
  const key = ia < ib ? `${{ia}}_${{ib}}` : `${{ib}}_${{ia}}`;
  return BATTLES[key] || null;
}}

function scoreColor(s){{
  if (s >= 65) return '#ff4d6a';
  if (s >= 35) return '#ffb830';
  return '#00ffaa';
}}

function scoreLabel(s){{
  if (s >= 65) return '⚡ KONFLIK TINGGI';
  if (s >= 35) return '⚠️ BERPOTENSI BEDA';
  return '✅ RELATIF SEJALAN';
}}

/* ════════════════════
   POPULATE SELECTS
════════════════════ */
function populateSelects(){{
  const sa = document.getElementById('sel-a');
  const sb = document.getElementById('sel-b');
  const placeholder = '<option value="-1">— Pilih paper —</option>';
  const opts = PAPERS.map(p =>
    `<option value="${{p.id}}">${{esc(p.year)}} · ${{esc(p.short)}}</option>`
  ).join('');
  sa.innerHTML = placeholder + opts;
  sb.innerHTML = placeholder + opts;
  // Default: select first two
  if (PAPERS.length >= 2){{
    sa.value = '0';
    sb.value = '1';
    onSelect();
  }}
  document.getElementById('paper-count').textContent =
    PAPERS.length + ' PAPER TERSEDIA';
}}

/* ════════════════════
   SWAP
════════════════════ */
function swapPapers(){{
  const sa = document.getElementById('sel-a');
  const sb = document.getElementById('sel-b');
  const tmp = sa.value;
  sa.value  = sb.value;
  sb.value  = tmp;
  onSelect();
}}

/* ════════════════════
   RENDER PAPER INFO
════════════════════ */
function renderPaperInfo(containerId, paper, side){{
  const el  = document.getElementById(containerId);
  const clr = side === 'a' ? 'var(--green)' : 'var(--red)';
  const sigPos = side === 'a'
    ? (paper._signals?.pos1 || [])
    : (paper._signals?.pos2 || []);
  const sigNeg = side === 'a'
    ? (paper._signals?.neg1 || [])
    : (paper._signals?.neg2 || []);
  const claims = side === 'a'
    ? (paper._claims1 || [])
    : (paper._claims2 || []);

  el.innerHTML = `
    <div class="pi-title">${{esc(paper.title)}}</div>
    <div class="pi-meta">
      <span class="pi-chip year">📅 ${{paper.year}}</span>
      <span class="pi-chip cite">↑ ${{Number(paper.citations).toLocaleString()}} sitasi</span>
      <span class="pi-chip">${{esc(paper.source)}}</span>
    </div>
    <div class="pi-section">Penulis</div>
    <div style="font-family:var(--mono);font-size:9px;color:var(--text-m);margin-bottom:8px">
      ${{esc(paper.authors)}}
    </div>
    <div class="pi-section">Abstrak</div>
    <div class="pi-abstract" style="margin-bottom:10px">${{esc(paper.abstract)}}</div>
    ${{sigPos.length||sigNeg.length ? `
    <div class="pi-section">Sinyal</div>
    <div class="sig-wrap" style="margin-bottom:8px">
      ${{sigPos.map(w=>`<span class="sig-tag sig-pos">+ ${{w}}</span>`).join('')}}
      ${{sigNeg.map(w=>`<span class="sig-tag sig-neg">− ${{w}}</span>`).join('')}}
    </div>` : ''}}
    ${{claims.length ? `
    <div class="pi-section">Klaim Utama</div>
    ${{claims.map(c=>`
      <div class="claim-item">
        <div class="claim-dot" style="background:${{clr}}"></div>
        <div class="claim-text">${{esc(c)}}</div>
      </div>
    `).join('')}}` : ''}}
    <div style="margin-top:10px">
      <a href="${{esc(paper.link)}}" target="_blank"
         style="font-family:var(--mono);font-size:8.5px;color:${{clr}};
                text-decoration:none;letter-spacing:1px">
        ↗ BUKA PAPER
      </a>
    </div>
  `;
}}

/* ════════════════════
   RENDER BATTLE ARENA
════════════════════ */
function renderArena(battle, ia, ib){{
  const arena = document.getElementById('arena-body');
  const score = battle.score;
  const clr   = scoreColor(score);
  const lbl   = scoreLabel(score);

  const verdictBg = score >= 65
    ? 'rgba(255,77,106,.07)'
    : score >= 35 ? 'rgba(255,184,48,.07)' : 'rgba(0,255,170,.07)';
  const verdictBorder = score >= 65
    ? 'rgba(255,77,106,.3)'
    : score >= 35 ? 'rgba(255,184,48,.3)' : 'rgba(0,255,170,.3)';

  // Shared keywords HTML
  const sharedHtml = battle.shared.length
    ? battle.shared.map(k=>`<span class="kb-shared-tag">${{esc(k)}}</span>`).join('')
    : '<span style="font-family:var(--mono);font-size:9px;color:var(--text-l)">Tidak ada keyword bersama</span>';

  // Contradiction pairs HTML
  const contraHtml = battle.contra.length
    ? battle.contra.map(c=>`
        <div class="kb-contra-row">
          <div class="kb-a">${{esc(c.a)}}</div>
          <div class="kb-vs">↔</div>
          <div class="kb-b">${{esc(c.b)}}</div>
        </div>
      `).join('')
    : `<div style="text-align:center;font-family:var(--mono);font-size:9px;color:var(--text-l);padding:8px">
        Tidak ada sinyal yang secara eksplisit berlawanan
       </div>`;

  arena.innerHTML = `
    <!-- Meter -->
    <div id="meter-wrap" style="width:100%;display:flex;flex-direction:column;align-items:center;gap:6px;">
      <div class="meter-label">Contradiction Meter</div>
      <div class="meter-score" style="color:${{clr}}">${{score}}</div>
      <div class="meter-score-sub">/ 100</div>
      <div class="meter-track" style="width:100%">
        <div class="meter-fill"
             style="width:${{score}}%;
                    background:linear-gradient(90deg,${{score>=65?'#ff4d6a':score>=35?'#ffb830':'#00ffaa'}},
                    ${{score>=65?'#ff1744':score>=35?'#ff8f00':'#00c87a'}});
                    box-shadow:0 0 16px ${{clr}}55">
        </div>
      </div>
      <div class="meter-ticks" style="width:100%;display:flex;justify-content:space-between;padding:0 2px">
        <span class="meter-tick">0 SEJALAN</span>
        <span class="meter-tick">50</span>
        <span class="meter-tick">BERTENTANGAN 100</span>
      </div>
    </div>

    <!-- Verdict -->
    <div id="verdict" style="width:100%;padding:11px 14px;border-radius:8px;
         border:1px solid ${{verdictBorder}};background:${{verdictBg}}">
      <div class="verdict-level" style="color:${{clr}}">${{lbl}}</div>
      <div class="verdict-text">${{esc(battle.verdict_text)}}</div>
    </div>

    <!-- Keyword Battle -->
    <div id="kw-battle" style="width:100%">
      <div class="kb-title">🔑 Keyword Bersama (${{battle.shared.length}})</div>
      <div class="kb-shared">${{sharedHtml}}</div>
      ${{battle.contra.length ? `
      <div class="kb-title" style="margin-top:8px">⚔ Sinyal Berlawanan (${{battle.contra.length}})</div>
      <div class="kb-contra-list" style="width:100%">
        <div style="display:flex;margin-bottom:4px">
          <div style="flex:1;text-align:right;font-family:var(--mono);font-size:7.5px;
                      color:var(--green);letter-spacing:1px;padding-right:8px">PAPER A</div>
          <div style="width:28px"></div>
          <div style="flex:1;font-family:var(--mono);font-size:7.5px;
                      color:var(--red);letter-spacing:1px;padding-left:8px">PAPER B</div>
        </div>
        ${{contraHtml}}
      </div>` : `<div class="kb-contra-list">${{contraHtml}}</div>`}}
    </div>
  `;
}}

/* ════════════════════
   MAIN: ON SELECT
════════════════════ */
function onSelect(){{
  const ia = parseInt(document.getElementById('sel-a').value);
  const ib = parseInt(document.getElementById('sel-b').value);

  // Render paper info (always, even without battle)
  if (ia >= 0 && PAPERS[ia]){{
    const pa = PAPERS[ia];
    const battle = (ib >= 0 && ib !== ia) ? getBattle(ia, ib) : null;
    if (battle){{
      pa._signals = battle;
      pa._claims1 = battle.claims1;
    }}
    renderPaperInfo('info-a', pa, 'a');
  }}

  if (ib >= 0 && PAPERS[ib]){{
    const pb = PAPERS[ib];
    const battle = (ia >= 0 && ia !== ib) ? getBattle(ia, ib) : null;
    if (battle){{
      pb._signals = battle;
      pb._claims2 = battle.claims2;
    }}
    renderPaperInfo('info-b', pb, 'b');
  }}

  // Battle arena
  if (ia >= 0 && ib >= 0 && ia !== ib){{
    const battle = getBattle(ia, ib);
    if (battle){{
      document.getElementById('empty-state') && (document.getElementById('empty-state').remove());
      renderArena(battle, ia, ib);
    }}
  }} else if (ia === ib && ia >= 0){{
    document.getElementById('arena-body').innerHTML = `
      <div id="empty-state" style="display:flex;flex-direction:column;align-items:center;
           justify-content:center;height:100%;gap:10px;opacity:.5">
        <div class="es-icon">⚠️</div>
        <div class="es-text">Paper A dan B tidak boleh sama</div>
      </div>`;
  }}
}}

/* ════════════════════
   INIT
════════════════════ */
populateSelects();
</script>
</body>
</html>"""
