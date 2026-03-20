"""
contradiction_detector.py v3
============================
Perbaikan utama dari v2:
  . Breakdown Skor selalu terlihat (tidak perlu scroll)
  . Arena dibagi 2 baris: baris atas = meter+breakdown, baris bawah = verdict+keywords
  . Font dinaikkan signifikan (body 14px, judul paper 15px, abstrak 12px)
  . History panel lebih terlihat
  . Battle Royale tetap ada

Fungsi publik:
  render_contradiction(papers, height=700) -> str
"""

import json


def _norm(p: dict, i: int) -> dict:
    title = (p.get("title") or "Untitled").strip()
    ab    = (p.get("abstract") or "").strip()
    try:    c = int(p.get("citations") or 0)
    except: c = 0
    try:    y = int(p.get("year") or 0)
    except: y = 0
    return {
        "id": i, "title": title,
        "short": (title[:60] + "\u2026") if len(title) > 60 else title,
        "authors": (p.get("authors") or "N/A")[:80],
        "year": y or 0, "citations": c,
        "venue": (p.get("venue") or "Unknown")[:60],
        "abstract": ab[:700] + ("\u2026" if len(ab) > 700 else ""),
        "source": p.get("source") or "unknown",
        "link": p.get("link") or "#",
    }


def render_contradiction(papers: list, height: int = 700) -> str:
    if len(papers) < 2:
        return "<div style='padding:20px;color:#7aa8cc;font-family:monospace'>Butuh minimal 2 paper.</div>"

    norm = [_norm(p, i) for i, p in enumerate(papers)]
    pj   = (
        json.dumps(norm, ensure_ascii=True)  # FIX: was ensure_ascii=False, caused UnicodeEncodeError in Streamlit
        .replace("<", r"\u003c")
        .replace("/", r"\/")
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:100%;height:{height}px;overflow:hidden;background:#030c18;color:#c8daf0;font-family:'Inter',sans-serif;user-select:none;}}
:root{{
  --bg:#030c18;--bg2:#061829;--bdr:rgba(0,210,255,.14);--bdr2:rgba(0,210,255,.35);
  --th:#eaf4ff;--tm:#90bcd8;--tl:#2d5070;
  --cyan:#00d4ff;--green:#00ffaa;--red:#ff4d6a;--amber:#ffb830;--purp:#c4aafe;
  --mono:'JetBrains Mono',monospace;--disp:'Orbitron',monospace;--sans:'Inter',sans-serif;
}}
/* scanlines */
body::after{{content:'';position:fixed;inset:0;pointer-events:none;z-index:997;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04) 2px,rgba(0,0,0,.04) 3px);}}

/* -- HEADER -- */
#hdr{{
  height:46px;display:flex;align-items:center;gap:14px;
  padding:0 18px;background:rgba(3,12,24,.98);
  border-bottom:1px solid var(--bdr);flex-shrink:0;z-index:20;
}}
.hdr-ttl{{font-family:var(--disp);font-size:12px;font-weight:700;letter-spacing:3px;color:var(--red);text-shadow:0 0 14px rgba(255,77,106,.5);}}
.hdr-sep{{width:1px;height:22px;background:var(--bdr);}}
.hdr-sub{{font-family:var(--mono);font-size:10px;color:var(--tl);letter-spacing:1.5px;}}
#mode-btns{{display:flex;gap:7px;margin-left:auto;}}
.mbn{{padding:6px 14px;border-radius:5px;cursor:pointer;font-family:var(--mono);font-size:10px;letter-spacing:.8px;border:1px solid var(--bdr);color:var(--tm);background:transparent;transition:all .15s;}}
.mbn:hover{{border-color:var(--bdr2);color:var(--th);}}
.mbn.on{{border-color:var(--amber);color:var(--amber);background:rgba(255,184,48,.08);box-shadow:0 0 10px rgba(255,184,48,.15);}}
#pcnt{{font-family:var(--mono);font-size:10px;color:var(--tl);letter-spacing:1px;}}

/* -- ROOT -- */
#root{{height:calc({height}px - 46px);display:flex;flex-direction:column;}}
.view{{display:none;flex:1;min-height:0;}}
.view.on{{display:flex;}}

/* ======================
   DUEL VIEW
====================== */
#v-duel{{flex-direction:row;}}

/* Paper panels */
.ppnl{{
  width:295px;flex-shrink:0;
  display:flex;flex-direction:column;overflow:hidden;
}}
#ppnl-a{{border-right:1px solid var(--bdr);}}
#ppnl-b{{border-left:1px solid var(--bdr);}}

.ppnl-hdr{{
  flex-shrink:0;padding:11px 14px 10px;
  border-bottom:1px solid var(--bdr);
  background:rgba(3,12,24,.75);
}}
.ppnl-lbl{{font-family:var(--disp);font-size:9.5px;font-weight:700;letter-spacing:3px;text-transform:uppercase;}}
.ppnl-hint{{font-family:var(--mono);font-size:9px;color:var(--tl);margin-top:3px;letter-spacing:.5px;}}

/* Dropdown */
.psel{{
  width:100%;margin-top:10px;
  background:rgba(6,22,38,.95);border:1px solid var(--bdr);border-radius:7px;
  color:var(--cyan);padding:9px 12px;
  font-family:var(--mono);font-size:11.5px;
  cursor:pointer;outline:none;appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2300d4ff'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 11px center;
  padding-right:30px;transition:border-color .15s;
}}
.psel:focus{{border-color:var(--bdr2);}}
.psel option{{background:#061829;color:#c8daf0;}}

/* Paper info */
.pinfo{{flex:1;overflow-y:auto;padding:13px 14px;}}
.pinfo::-webkit-scrollbar{{width:3px;}}
.pinfo::-webkit-scrollbar-thumb{{background:rgba(0,210,255,.15);border-radius:3px;}}

.pi-title{{font-family:var(--sans);font-size:15px;font-weight:700;color:var(--th);line-height:1.4;margin-bottom:10px;}}
.pi-chips{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;}}
.chip{{font-family:var(--mono);font-size:10px;padding:3px 10px;border-radius:5px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);color:var(--tm);}}
.chip.yr{{color:var(--cyan);border-color:rgba(0,212,255,.25);background:rgba(0,212,255,.07);}}
.chip.ct{{color:var(--amber);border-color:rgba(255,184,48,.25);background:rgba(255,184,48,.07);}}

.pi-sec{{font-family:var(--mono);font-size:8.5px;letter-spacing:2px;color:var(--tl);text-transform:uppercase;margin-bottom:6px;margin-top:12px;}}
.pi-abs{{font-family:var(--sans);font-size:12px;color:var(--tm);line-height:1.6;}}

.sig-wrap{{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px;}}
.sig{{font-family:var(--mono);font-size:10px;padding:3px 9px;border-radius:4px;font-weight:600;letter-spacing:.5px;}}
.sig-p{{background:rgba(0,255,170,.09);color:var(--green);border:1px solid rgba(0,255,170,.22);}}
.sig-n{{background:rgba(255,77,106,.09);color:var(--red);border:1px solid rgba(255,77,106,.22);}}

.claim-item{{display:flex;gap:8px;margin-bottom:8px;align-items:flex-start;}}
.claim-dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0;margin-top:5px;}}
.claim-txt{{font-family:var(--sans);font-size:11.5px;color:var(--tm);line-height:1.5;}}

.pi-link{{display:inline-block;margin-top:11px;font-family:var(--mono);font-size:10px;letter-spacing:1px;text-decoration:none;}}

/* ======================
   ARENA (center)
====================== */
#arena{{
  flex:1;display:flex;flex-direction:column;
  background:linear-gradient(180deg,#040f1d,#030c18);
  position:relative;overflow:hidden;
}}
#arena::before{{
  content:'';position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(0,210,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,210,255,.025) 1px,transparent 1px);
  background-size:32px 32px;
}}

/* Arena header row */
.arena-hdr{{
  flex-shrink:0;padding:10px 16px 9px;
  border-bottom:1px solid var(--bdr);
  background:rgba(3,12,24,.65);
  display:flex;align-items:center;justify-content:center;
  position:relative;z-index:2;
}}
.arena-ttl{{font-family:var(--disp);font-size:9.5px;font-weight:700;letter-spacing:3px;color:var(--amber);text-shadow:0 0 10px rgba(255,184,48,.35);}}
#btn-swap{{
  position:absolute;right:12px;
  background:rgba(255,184,48,.08);border:1px solid rgba(255,184,48,.28);
  border-radius:6px;padding:6px 13px;
  font-family:var(--mono);font-size:10px;color:var(--amber);
  cursor:pointer;letter-spacing:.5px;transition:all .15s;
}}
#btn-swap:hover{{background:rgba(255,184,48,.2);border-color:var(--amber);}}

/* -- TOP SECTION: meter + breakdown (always visible, fixed height) -- */
#arena-top{{
  flex-shrink:0;
  display:flex;gap:0;
  border-bottom:1px solid var(--bdr);
  position:relative;z-index:1;
}}

/* Meter block (left half of top) */
#meter-block{{
  flex:1;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:14px 20px 12px;
  border-right:1px solid var(--bdr);
  gap:8px;
}}
.meter-lbl{{font-family:var(--disp);font-size:9.5px;letter-spacing:2.5px;color:var(--tl);text-transform:uppercase;}}
.meter-score{{font-family:var(--disp);font-size:40px;font-weight:700;letter-spacing:2px;line-height:1;transition:color .7s;text-shadow:0 0 24px currentColor;}}
.meter-sub{{font-family:var(--mono);font-size:10.5px;color:var(--tl);letter-spacing:2px;}}
.meter-track{{width:100%;height:18px;background:rgba(255,255,255,.05);border-radius:9px;overflow:hidden;border:1px solid rgba(255,255,255,.07);}}
.meter-fill{{height:100%;border-radius:9px;transition:width 1s cubic-bezier(.4,0,.2,1);position:relative;overflow:hidden;}}
.meter-fill::after{{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.2),transparent);animation:sh 2.2s ease-in-out infinite;}}
@keyframes sh{{from{{transform:translateX(-100%)}}to{{transform:translateX(200%)}}}}
.meter-ticks{{width:100%;display:flex;justify-content:space-between;}}
.mtick{{font-family:var(--mono);font-size:9px;color:var(--tl);}}

/* Breakdown block (right half of top) */
#breakdown-block{{
  flex:1;
  padding:14px 18px 12px;
  display:flex;flex-direction:column;justify-content:center;
  gap:0;
}}
.bd-title{{
  font-family:var(--disp);font-size:8.5px;letter-spacing:2.5px;
  color:var(--tl);text-transform:uppercase;margin-bottom:10px;
}}
.bd-row{{display:flex;align-items:center;gap:10px;margin-bottom:9px;}}
.bd-key{{font-family:var(--mono);font-size:11px;color:var(--tm);width:130px;flex-shrink:0;text-align:right;}}
.bd-bg{{flex:1;height:10px;background:rgba(255,255,255,.06);border-radius:5px;overflow:hidden;}}
.bd-fill{{height:100%;border-radius:5px;transition:width .9s cubic-bezier(.4,0,.2,1);}}
.bd-val{{font-family:var(--disp);font-size:12px;font-weight:600;width:32px;text-align:left;flex-shrink:0;}}

/* -- BOTTOM SECTION: verdict + keywords (scrollable) -- */
#arena-bot{{
  flex:1;overflow-y:auto;
  padding:14px 20px 44px;
  display:flex;flex-direction:column;gap:12px;
  position:relative;z-index:1;
}}
#arena-bot::-webkit-scrollbar{{width:3px;}}
#arena-bot::-webkit-scrollbar-thumb{{background:rgba(0,210,255,.12);border-radius:3px;}}

/* Verdict */
.verdict-wrap{{padding:13px 16px;border-radius:9px;border:1px solid;transition:all .6s;}}
.verdict-lbl{{font-family:var(--disp);font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;}}
.verdict-txt{{font-family:var(--sans);font-size:13px;line-height:1.6;color:var(--tm);}}

/* Keyword battle */
.kb-title{{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;color:var(--tl);text-transform:uppercase;text-align:center;margin-bottom:9px;}}
.kb-shared{{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-bottom:12px;}}
.kb-stag{{font-family:var(--mono);font-size:10px;padding:3px 10px;border-radius:4px;background:rgba(196,170,254,.1);border:1px solid rgba(196,170,254,.25);color:var(--purp);}}
.kb-crow{{display:flex;align-items:center;border-radius:6px;overflow:hidden;border:1px solid rgba(255,255,255,.07);margin-bottom:6px;}}
.kb-a{{flex:1;padding:7px 10px;text-align:right;background:rgba(0,255,170,.07);font-family:var(--mono);font-size:11px;color:var(--green);font-weight:600;}}
.kb-vs{{padding:7px 9px;background:rgba(255,255,255,.04);font-family:var(--mono);font-size:9px;color:var(--tl);border-left:1px solid rgba(255,255,255,.07);border-right:1px solid rgba(255,255,255,.07);}}
.kb-b{{flex:1;padding:7px 10px;background:rgba(255,77,106,.07);font-family:var(--mono);font-size:11px;color:var(--red);font-weight:600;}}

/* Export */
.btn-exp{{
  width:100%;padding:11px;text-align:center;
  background:rgba(196,170,254,.07);border:1px solid rgba(196,170,254,.27);
  border-radius:7px;color:var(--purp);cursor:pointer;
  font-family:var(--mono);font-size:10.5px;letter-spacing:1.5px;
  text-transform:uppercase;transition:all .15s;
}}
.btn-exp:hover{{background:rgba(196,170,254,.18);border-color:var(--purp);}}

/* -- HISTORY PANEL -- */
#hist{{
  position:absolute;bottom:0;left:0;right:0;
  background:rgba(3,12,24,.97);
  border-top:1px solid var(--bdr);
  z-index:30;
  transition:height .3s cubic-bezier(.4,0,.2,1);
  height:38px;overflow:hidden;
}}
#hist.open{{height:135px;}}
#hist-toggle{{
  height:38px;display:flex;align-items:center;gap:9px;
  padding:0 16px;cursor:pointer;
}}
.hist-lbl{{font-family:var(--mono);font-size:10px;color:var(--tl);letter-spacing:1.5px;}}
#hist-cnt{{font-family:var(--mono);font-size:9.5px;color:var(--cyan);padding:1px 8px;border-radius:3px;background:rgba(0,212,255,.08);border:1px solid rgba(0,212,255,.2);}}
.hist-arr{{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--tl);transition:transform .3s;}}
#hist.open .hist-arr{{transform:rotate(180deg);}}
#hist-list{{height:97px;overflow-x:auto;overflow-y:hidden;display:flex;gap:9px;padding:0 16px 10px;align-items:center;}}
#hist-list::-webkit-scrollbar{{height:3px;}}
#hist-list::-webkit-scrollbar-thumb{{background:rgba(0,210,255,.15);border-radius:3px;}}
.hcard{{flex-shrink:0;width:180px;background:rgba(6,22,38,.92);border:1px solid var(--bdr);border-radius:7px;padding:9px 11px;cursor:pointer;transition:border-color .15s;}}
.hcard:hover{{border-color:var(--bdr2);}}
.hcard-sc{{font-family:var(--disp);font-size:16px;font-weight:700;letter-spacing:1px;line-height:1;}}
.hcard-tt{{font-family:var(--mono);font-size:8.5px;color:var(--tl);margin-top:6px;line-height:1.45;}}

/* ======================
   BATTLE ROYALE
====================== */
#v-royale{{flex-direction:column;}}
.ry-hdr{{flex-shrink:0;padding:11px 18px 10px;border-bottom:1px solid var(--bdr);background:rgba(3,12,24,.7);}}
.ry-ttl{{font-family:var(--disp);font-size:10.5px;font-weight:700;letter-spacing:3px;color:var(--purp);}}
.ry-sub{{font-family:var(--mono);font-size:9.5px;color:var(--tl);margin-top:3px;}}
#ry-body{{flex:1;overflow:auto;padding:16px 18px;}}
#ry-body::-webkit-scrollbar{{width:4px;height:4px;}}
#ry-body::-webkit-scrollbar-thumb{{background:rgba(0,210,255,.15);border-radius:3px;}}
#ry-table{{border-collapse:collapse;}}
.rt-cr{{width:36px;height:36px;}}
.rt-ch{{font-family:var(--mono);font-size:10px;color:var(--tm);padding:0 6px;max-width:110px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;writing-mode:vertical-rl;transform:rotate(180deg);height:95px;vertical-align:bottom;padding-bottom:7px;}}
.rt-rh{{font-family:var(--mono);font-size:10px;color:var(--tm);padding:4px 11px;max-width:130px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;}}
.rt-cell{{width:46px;height:46px;text-align:center;cursor:pointer;border:1px solid rgba(255,255,255,.04);transition:transform .12s,box-shadow .12s;vertical-align:middle;}}
.rt-cell:hover{{transform:scale(1.15);z-index:5;box-shadow:0 0 14px rgba(0,0,0,.6);}}
.rt-cell span{{font-family:var(--disp);font-size:11px;font-weight:700;}}
.rt-diag{{background:rgba(255,255,255,.03);cursor:default;}}
.rt-diag:hover{{transform:none;box-shadow:none;}}

/* -- Empty state -- */
.empty{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:12px;opacity:.38;}}
.empty-ic{{font-size:38px;}}
.empty-tx{{font-family:var(--mono);font-size:12px;color:var(--tl);letter-spacing:1px;text-align:center;line-height:1.65;}}
</style>
</head>
<body>

<!-- HEADER -->
<div id="hdr">
  <span class="hdr-ttl">&#9889; CONTRADICTION DETECTOR</span>
  <div class="hdr-sep"></div>
  <span class="hdr-sub">ANALISIS KONTRADIKSI REAL-TIME</span>
  <div id="mode-btns">
    <button class="mbn on" id="btn-duel"   onclick="setMode('duel')">&#9876; 1 VS 1</button>
    <button class="mbn"    id="btn-royale" onclick="setMode('royale')">&#127942; BATTLE ROYALE</button>
  </div>
  <div class="hdr-sep"></div>
  <span id="pcnt"></span>
</div>

<!-- ROOT -->
<div id="root">

  <!-- == DUEL == -->
  <div class="view on" id="v-duel">

    <!-- Paper A -->
    <div class="ppnl" id="ppnl-a">
      <div class="ppnl-hdr" style="border-top:3px solid var(--green)">
        <div class="ppnl-lbl" style="color:var(--green)">&#9672; Paper A</div>
        <div class="ppnl-hint">Pilih paper pertama</div>
        <select class="psel" id="sel-a" onchange="onSel()"></select>
      </div>
      <div class="pinfo" id="info-a">
        <div class="empty"><div class="empty-ic">&#128196;</div><div class="empty-tx">Pilih Paper A<br>dari dropdown di atas</div></div>
      </div>
    </div>

    <!-- ARENA -->
    <div id="arena">
      <!-- Header row -->
      <div class="arena-hdr">
        <span class="arena-ttl">&#9876; BATTLE ARENA</span>
        <button id="btn-swap" onclick="swap()">&#8644; SWAP</button>
      </div>

      <!-- TOP: Meter + Breakdown (always visible) -->
      <div id="arena-top">
        <div id="meter-block">
          <div class="meter-lbl">Contradiction Meter</div>
          <div class="meter-score" id="m-score" style="color:#2d5070">&#8212;</div>
          <div class="meter-sub">/ 100</div>
          <div class="meter-track">
            <div class="meter-fill" id="m-fill" style="width:0%"></div>
          </div>
          <div class="meter-ticks">
            <span class="mtick">0 SEJALAN</span>
            <span class="mtick">50</span>
            <span class="mtick">BERTENTANGAN 100</span>
          </div>
        </div>
        <div id="breakdown-block">
          <div class="bd-title">&#11041; Breakdown Skor</div>
          <div class="bd-row">
            <div class="bd-key">Keyword bersama</div>
            <div class="bd-bg"><div class="bd-fill" id="bd-sh" style="width:0%;background:#c4aafe;box-shadow:0 0 7px #c4aafe44"></div></div>
            <div class="bd-val" id="bv-sh" style="color:#c4aafe">0</div>
          </div>
          <div class="bd-row">
            <div class="bd-key">Sinyal berlawanan</div>
            <div class="bd-bg"><div class="bd-fill" id="bd-sig" style="width:0%;background:#ff4d6a;box-shadow:0 0 7px #ff4d6a44"></div></div>
            <div class="bd-val" id="bv-sig" style="color:#ff4d6a">0</div>
          </div>
          <div class="bd-row" style="margin-bottom:0">
            <div class="bd-key">Gap waktu</div>
            <div class="bd-bg"><div class="bd-fill" id="bd-tm" style="width:0%;background:#ffb830;box-shadow:0 0 7px #ffb83044"></div></div>
            <div class="bd-val" id="bv-tm" style="color:#ffb830">0</div>
          </div>
        </div>
      </div>

      <!-- BOTTOM: Verdict + Keywords (scrollable) -->
      <div id="arena-bot">
        <div class="empty" id="arena-empty">
          <div class="empty-ic">&#9889;</div>
          <div class="empty-tx">Pilih Paper A dan B<br>untuk memulai analisis kontradiksi</div>
        </div>
      </div>

      <!-- History Panel -->
      <div id="hist">
        <div id="hist-toggle" onclick="document.getElementById('hist').classList.toggle('open')">
          <span style="font-size:13px">&#128203;</span>
          <span class="hist-lbl">RIWAYAT BATTLE</span>
          <span id="hist-cnt">0</span>
          <span class="hist-arr">&#9650;</span>
        </div>
        <div id="hist-list"></div>
      </div>
    </div>

    <!-- Paper B -->
    <div class="ppnl" id="ppnl-b">
      <div class="ppnl-hdr" style="border-top:3px solid var(--red)">
        <div class="ppnl-lbl" style="color:var(--red)">&#9672; Paper B</div>
        <div class="ppnl-hint">Pilih paper kedua</div>
        <select class="psel" id="sel-b" onchange="onSel()"></select>
      </div>
      <div class="pinfo" id="info-b">
        <div class="empty"><div class="empty-ic">&#128196;</div><div class="empty-tx">Pilih Paper B<br>dari dropdown di atas</div></div>
      </div>
    </div>

  </div><!-- #v-duel -->

  <!-- == BATTLE ROYALE == -->
  <div class="view" id="v-royale">
    <div class="ry-hdr">
      <div class="ry-ttl">&#127942; BATTLE ROYALE MATRIX</div>
      <div class="ry-sub">Setiap sel = conflict score antar dua paper &#183; Klik sel &#8594; buka duel langsung</div>
    </div>
    <div id="ry-body"><table id="ry-table"></table></div>
  </div>

</div><!-- #root -->

<script>
/* DATA */
const PAPERS = {pj};

/* NLP */
const SW = new Set(["a","an","the","and","or","but","in","on","at","to","for","of","with","by","from","as","is","was","are","were","be","been","have","has","had","do","does","did","will","would","could","should","may","might","not","this","that","these","those","it","its","we","our","their","they","paper","study","research","propose","present","show","result","results","approach","method","methods","using","used","use","based","novel","new","existing","previous","however","also","which","such","than","more","most","work","model","system","data","two","three","one","can","well","significant","significantly","evaluate","experiment","dataset"]);
const POS=["improve","improves","improved","outperform","superior","better","effective","efficient","accurate","robust","strong","increase","enhance","advantage","promising","confirms","validates","supports","achieves","success","beneficial","positive","greater","faster","best"];
const NEG=["fail","fails","failed","failure","poor","worse","inferior","ineffective","inaccurate","weak","insignificant","decrease","limitation","drawback","challenge","problem","limited","lacks","unable","insufficient","smaller","slower","worst","negative","doubt"];
const CP=[["improve","fail"],["effective","ineffective"],["accurate","inaccurate"],["robust","weak"],["superior","inferior"],["increase","decrease"],["high","low"],["strong","weak"],["better","worse"],["success","failure"],["beneficial","harmful"],["positive","negative"],["greater","smaller"],["faster","slower"],["best","worst"],["validates","challenges"],["supports","contradicts"],["confirms","refutes"]];

function tok(t){{return((t||'').toLowerCase().match(/[a-z][a-z0-9-]{{2,}}/g)||[]).filter(w=>!SW.has(w));}}

const _BC={{}};
function battle(ia,ib){{
  const k=ia<ib?ia+'_'+ib:ib+'_'+ia;
  if(_BC[k])return _BC[k];
  const p1=PAPERS[ia],p2=PAPERS[ib];
  const t1=((p1.title||'')+' '+(p1.abstract||'')).toLowerCase();
  const t2=((p2.title||'')+' '+(p2.abstract||'')).toLowerCase();
  const s1=new Set(tok(t1)),s2=new Set(tok(t2));
  const sh=[...s1].filter(w=>s2.has(w)&&!SW.has(w)).sort();
  const ps1=POS.filter(w=>t1.includes(w)),ng1=NEG.filter(w=>t1.includes(w));
  const ps2=POS.filter(w=>t2.includes(w)),ng2=NEG.filter(w=>t2.includes(w));
  const ct=[],cs=new Set();
  for(const[a,b]of CP){{
    const k2=a+'|'+b;if(cs.has(k2))continue;
    if(ps1.includes(a)&&ng2.includes(b)){{ct.push({{a,b}});cs.add(k2);}}
    else if(ng1.includes(b)&&ps2.includes(a)){{ct.push({{a:b,b:a}});cs.add(k2);}}
  }}
  const ss=Math.min(sh.length*3,30),cs2=Math.min(ct.length*18,54);
  const yr1=parseInt(p1.year)||0,yr2=parseInt(p2.year)||0;
  const ts=Math.min(Math.abs(yr1-yr2),16);
  const sc=Math.min(100,ss+cs2+ts);
  function exCl(txt){{
    const sn=(txt||'').split(/[.!?]\s+/).filter(s=>s.length>20);
    return sn.map(s=>{{const sl=s.toLowerCase();const score=[...POS,...NEG].filter(w=>sl.includes(w)).length;return{{s,score}};}}).sort((a,b)=>b.score-a.score).slice(0,3).map(x=>x.s);
  }}
  const r={{sc,sh:sh.slice(0,10),ps1:ps1.slice(0,6),ng1:ng1.slice(0,6),ps2:ps2.slice(0,6),ng2:ng2.slice(0,6),ct:ct.slice(0,6),cl1:exCl(p1.abstract),cl2:exCl(p2.abstract),bd:{{sh:ss,sig:cs2,tm:ts}},vl:sc>=65?'high':sc>=35?'medium':'low',vt:sc>=65?'Paper ini menunjukkan KONTRADIKSI SIGNIFIKAN. Keduanya membahas topik yang sama ('+sh.length+' keyword bersama) namun menggunakan sinyal yang berlawanan \u2014 kemungkinan perbedaan metodologi, dataset, atau populasi studi.':sc>=35?'Terdapat POTENSI PERBEDAAN antara kedua paper. Keduanya berbagi '+sh.length+' keyword namun beberapa klaim mungkin bertentangan. Disarankan membaca kedua abstrak secara menyeluruh.':'Kedua paper relatif SEJALAN. Mereka berbagi '+sh.length+' keyword dan tidak menunjukkan sinyal yang secara eksplisit berlawanan. Kemungkinan besar saling melengkapi.'}};
  _BC[k]=r;return r;
}}

function esc(s){{return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function sclr(s){{return s>=65?'#ff4d6a':s>=35?'#ffb830':'#00ffaa';}}
function slbl(s){{return s>=65?'\u26a1 KONFLIK TINGGI':s>=35?'\u26a0\ufe0f BERPOTENSI BEDA':'\u2705 RELATIF SEJALAN';}}

/* HISTORY */
const _H=[];
function addH(ia,ib,sc){{
  if(_H.find(h=>(h.ia===ia&&h.ib===ib)||(h.ia===ib&&h.ib===ia)))return;
  _H.unshift({{ia,ib,sc}});
  document.getElementById('hist-cnt').textContent=_H.length;
  document.getElementById('hist-list').innerHTML=_H.map(h=>{{
    const pa=PAPERS[h.ia],pb=PAPERS[h.ib];const clr=sclr(h.sc);
    return `<div class="hcard" onclick="loadH(${{h.ia}},${{h.ib}})"><div class="hcard-sc" style="color:${{clr}};text-shadow:0 0 10px ${{clr}}55">${{h.sc}}</div><div class="hcard-tt">${{esc(pa.short.substring(0,26))}}\u2026<br><span style="color:var(--tl)">vs</span> ${{esc(pb.short.substring(0,26))}}\u2026</div></div>`;
  }}).join('');
}}
function loadH(ia,ib){{document.getElementById('sel-a').value=ia;document.getElementById('sel-b').value=ib;onSel();}}

/* RENDER PAPER INFO */
function renderInfo(elId,paper,side,bt){{
  const el=document.getElementById(elId);
  const clr=side==='a'?'var(--green)':'var(--red)';
  const pos=side==='a'?(bt?.ps1||[]):(bt?.ps2||[]);
  const neg=side==='a'?(bt?.ng1||[]):(bt?.ng2||[]);
  const cls=side==='a'?(bt?.cl1||[]):(bt?.cl2||[]);
  el.innerHTML=`
    <div class="pi-title">${{esc(paper.title)}}</div>
    <div class="pi-chips">
      <span class="chip yr">&#128197; ${{paper.year||'?'}}</span>
      <span class="chip ct">\u2191 ${{Number(paper.citations).toLocaleString()}} sitasi</span>
      <span class="chip">${{esc(paper.source)}}</span>
    </div>
    <div class="pi-sec">Penulis</div>
    <div style="font-family:var(--mono);font-size:11px;color:var(--tm);margin-bottom:10px;line-height:1.45">${{esc(paper.authors)}}</div>
    <div class="pi-sec">Abstrak</div>
    <div class="pi-abs" style="margin-bottom:12px">${{esc(paper.abstract)}}</div>
    ${{pos.length||neg.length?`<div class="pi-sec">Sinyal Terdeteksi</div><div class="sig-wrap" style="margin-bottom:10px">${{pos.map(w=>`<span class="sig sig-p">+ ${{w}}</span>`).join('')}}${{neg.map(w=>`<span class="sig sig-n">\u2212 ${{w}}</span>`).join('')}}</div>`:''}}
    ${{cls.length?`<div class="pi-sec">Klaim Utama</div>${{cls.map(c=>`<div class="claim-item"><div class="claim-dot" style="background:${{clr}}"></div><div class="claim-txt">${{esc(c)}}</div></div>`).join('')}}`:''}}
    <a href="${{esc(paper.link)}}" target="_blank" class="pi-link" style="color:${{clr}}">\u2197 BUKA PAPER LENGKAP</a>
  `;
}}

/* UPDATE METER & BREAKDOWN */
function updateMeter(bt){{
  const sc=bt.sc;const clr=sclr(sc);
  document.getElementById('m-score').textContent=sc;
  document.getElementById('m-score').style.color=clr;
  document.getElementById('m-fill').style.width=sc+'%';
  document.getElementById('m-fill').style.background=`linear-gradient(90deg,${{clr}},${{sc>=65?'#ff1744':sc>=35?'#ff8f00':'#00c87a'}})`;
  document.getElementById('m-fill').style.boxShadow=`0 0 16px ${{clr}}44`;

  document.getElementById('bd-sh').style.width=Math.round(bt.bd.sh/30*100)+'%';
  document.getElementById('bv-sh').textContent='+'+bt.bd.sh;
  document.getElementById('bd-sig').style.width=Math.round(bt.bd.sig/54*100)+'%';
  document.getElementById('bv-sig').textContent='+'+bt.bd.sig;
  document.getElementById('bd-tm').style.width=Math.round(bt.bd.tm/16*100)+'%';
  document.getElementById('bv-tm').textContent='+'+bt.bd.tm;
}}

/* RENDER BOTTOM (verdict + keywords) */
function renderBot(ia,ib,bt){{
  const sc=bt.sc;const clr=sclr(sc);const lbl=slbl(sc);
  const vbg=bt.vl==='high'?'rgba(255,77,106,.07)':bt.vl==='medium'?'rgba(255,184,48,.07)':'rgba(0,255,170,.07)';
  const vbd=bt.vl==='high'?'rgba(255,77,106,.32)':bt.vl==='medium'?'rgba(255,184,48,.32)':'rgba(0,255,170,.32)';
  const sh=bt.sh.length?bt.sh.map(k=>`<span class="kb-stag">${{esc(k)}}</span>`).join(''):`<span style="font-family:var(--mono);font-size:10.5px;color:var(--tl)">Tidak ada keyword bersama</span>`;
  const ct=bt.ct.length?bt.ct.map(c=>`<div class="kb-crow"><div class="kb-a">${{esc(c.a)}}</div><div class="kb-vs">\u2194</div><div class="kb-b">${{esc(c.b)}}</div></div>`).join(''):`<div style="text-align:center;font-family:var(--mono);font-size:11px;color:var(--tl);padding:11px">Tidak ada sinyal eksplisit yang berlawanan</div>`;

  document.getElementById('arena-bot').innerHTML=`
    <div class="verdict-wrap" style="border-color:${{vbd}};background:${{vbg}}">
      <div class="verdict-lbl" style="color:${{clr}}">${{lbl}}</div>
      <div class="verdict-txt">${{esc(bt.vt)}}</div>
    </div>
    <div>
      <div class="kb-title">&#128273; Keyword Bersama (${{bt.sh.length}})</div>
      <div class="kb-shared">${{sh}}</div>
    </div>
    ${{bt.ct.length?`<div>
      <div style="display:flex;margin-bottom:6px">
        <div style="flex:1;text-align:right;font-family:var(--mono);font-size:9px;color:var(--green);letter-spacing:1px;padding-right:10px">PAPER A</div>
        <div style="width:32px"></div>
        <div style="flex:1;font-family:var(--mono);font-size:9px;color:var(--red);letter-spacing:1px;padding-left:10px">PAPER B</div>
      </div>
      ${{ct}}</div>`:`<div>${{ct}}</div>`}}
    <button class="btn-exp" onclick="doExport(${{ia}},${{ib}})">\u2b07 EXPORT LAPORAN LITERATURE REVIEW</button>
  `;
}}

/* EXPORT */
function doExport(ia,ib){{
  const bt=battle(ia,ib),pa=PAPERS[ia],pb=PAPERS[ib];
  const sl=bt.sc>=65?'KONTRADIKTIF':bt.sc>=35?'BERPOTENSI BERBEDA':'SEJALAN';
  const S='------------------------------------------------------------';
  const rep=
    'LAPORAN PERBANDINGAN LITERATUR\n'+S+
    '\nPaper A: '+pa.title+'\n  Tahun: '+pa.year+' | Sitasi: '+pa.citations+'\n  Penulis: '+pa.authors+
    '\n\nPaper B: '+pb.title+'\n  Tahun: '+pb.year+' | Sitasi: '+pb.citations+'\n  Penulis: '+pb.authors+
    '\n\n'+S+'\nHASIL: '+sl+' (Score: '+bt.sc+'/100)'+
    '\nBreakdown: Keyword +'+bt.bd.sh+' | Sinyal +'+bt.bd.sig+' | Waktu +'+bt.bd.tm+
    '\nKeyword Bersama: '+(bt.sh.join(', ')||'\u2014')+
    '\nSinyal Berlawanan: '+(bt.ct.map(c=>'"'+c.a+'" vs "'+c.b+'"').join('; ')||'\u2014')+
    '\n\n'+S+'\nKALIMAT LITERATURE REVIEW:\n\n"'+pa.title+' ('+pa.year+') '+
    (bt.sc>=65?'bertentangan secara signifikan dengan':bt.sc>=35?'menunjukkan perbedaan pandangan dengan':'sejalan dengan')+
    ' '+pb.title+' ('+pb.year+'). Kedua paper membahas topik yang berkaitan ('+bt.sh.join(', ')+')'+(bt.ct.length?', namun terdapat perbedaan sinyal pada aspek: '+bt.ct.map(c=>c.a+' vs '+c.b).join('; ')+'.':'.')+'"';
  const blob=new Blob([rep],{{type:'text/plain;charset=utf-8'}});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='battle_'+pa.year+'_vs_'+pb.year+'.txt';a.click();URL.revokeObjectURL(url);
}}

/* MAIN SELECT */
function onSel(){{
  const ia=parseInt(document.getElementById('sel-a').value);
  const ib=parseInt(document.getElementById('sel-b').value);
  const bt=(ia>=0&&ib>=0&&ia!==ib)?battle(ia,ib):null;

  if(ia>=0&&PAPERS[ia])renderInfo('info-a',PAPERS[ia],'a',bt);
  if(ib>=0&&PAPERS[ib])renderInfo('info-b',PAPERS[ib],'b',bt);

  if(bt){{
    updateMeter(bt);
    renderBot(ia,ib,bt);
    addH(ia,ib,bt.sc);
  }} else {{
    // Reset meter
    document.getElementById('m-score').textContent='\u2014';
    document.getElementById('m-score').style.color='#2d5070';
    document.getElementById('m-fill').style.width='0%';
    ['bd-sh','bd-sig','bd-tm'].forEach(id=>document.getElementById(id).style.width='0%');
    ['bv-sh','bv-sig','bv-tm'].forEach(id=>document.getElementById(id).textContent='0');
    document.getElementById('arena-bot').innerHTML=
      ia===ib&&ia>=0
      ?`<div class="empty"><div class="empty-ic">\u26a0\ufe0f</div><div class="empty-tx">Paper A dan B tidak boleh sama</div></div>`
      :`<div class="empty"><div class="empty-ic">\u26a1</div><div class="empty-tx">Pilih Paper A dan B<br>untuk memulai analisis</div></div>`;
  }}
}}

function swap(){{
  const sa=document.getElementById('sel-a'),sb=document.getElementById('sel-b');
  [sa.value,sb.value]=[sb.value,sa.value];onSel();
}}

/* BATTLE ROYALE */
function renderRoyale(){{
  let html='<thead><tr><th class="rt-cr"></th>';
  PAPERS.forEach(p=>{{html+=`<th class="rt-ch" title="${{esc(p.title)}}">${{esc(p.short.substring(0,18))}}</th>`;}});
  html+='</tr></thead><tbody>';
  PAPERS.forEach((pa,ia)=>{{
    html+=`<tr><td class="rt-rh" title="${{esc(pa.title)}}">${{esc(pa.short.substring(0,22))}}</td>`;
    PAPERS.forEach((pb,ib)=>{{
      if(ia===ib){{html+=`<td class="rt-cell rt-diag"></td>`;}}
      else{{
        const bt=battle(ia,ib);const clr=sclr(bt.sc);
        const bg=bt.sc>=65?`rgba(255,77,106,${{.05+bt.sc/600}})`:bt.sc>=35?`rgba(255,184,48,${{.04+bt.sc/700}})`:`rgba(0,255,170,${{.03+bt.sc/900}})`;
        html+=`<td class="rt-cell" style="background:${{bg}}" title="${{esc(pa.short)}} vs ${{esc(pb.short)}}: ${{bt.sc}}" onclick="openRoyale(${{ia}},${{ib}})"><span style="color:${{clr}}">${{bt.sc}}</span></td>`;
      }}
    }});
    html+='</tr>';
  }});
  html+='</tbody>';
  document.getElementById('ry-table').innerHTML=html;
}}

function openRoyale(ia,ib){{setMode('duel');document.getElementById('sel-a').value=ia;document.getElementById('sel-b').value=ib;onSel();}}

function setMode(m){{
  document.getElementById('v-duel').classList.toggle('on',m==='duel');
  document.getElementById('v-royale').classList.toggle('on',m==='royale');
  document.getElementById('btn-duel').classList.toggle('on',m==='duel');
  document.getElementById('btn-royale').classList.toggle('on',m==='royale');
  if(m==='royale')renderRoyale();
}}

/* INIT */
function init(){{
  const sa=document.getElementById('sel-a'),sb=document.getElementById('sel-b');
  const ph='<option value="-1">\u2014 Pilih paper \u2014</option>';
  const opts=PAPERS.map(p=>`<option value="${{p.id}}">${{p.year}} \u00b7 ${{esc(p.short)}}</option>`).join('');
  sa.innerHTML=ph+opts;sb.innerHTML=ph+opts;
  document.getElementById('pcnt').textContent=PAPERS.length+' PAPER TERSEDIA';
  if(PAPERS.length>=2){{sa.value='0';sb.value='1';onSel();}}
}}
init();
</script>
</body>
</html>"""
