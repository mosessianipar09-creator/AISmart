"""
contradiction_detector.py  v4
==============================
REWRITE TOTAL:
  • JSON.parse via <script type="application/json"> — NO MORE SYNTAX ERRORS ever
  • Claim Extraction + Claim vs Claim head-to-head battle
  • Auto-Highlight abstrak (hijau=positif, merah=negatif, ungu=shared)
  • Stance Detection per kalimat (SUPPORTS / CONTRADICTS / NEUTRAL)
  • Reconciliation Hint — kenapa mungkin tidak benar-benar kontradiksi
  • Evidence Timeline — kronologi posisi riset
  • 4 tabs di arena: VERDICT / CLAIMS / KEYWORDS / TIMELINE
  • Score breakdown 4 dimensi: keyword + signal + claim + time
  • Battle Royale upgrade: HOT badge untuk most controversial paper
  • Export sintesis siap tempel ke bab metodologi/tinjauan pustaka
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
        "short": (title[:55] + "\u2026") if len(title) > 55 else title,
        "authors": (p.get("authors") or "N/A")[:80],
        "year": y or 0, "citations": c,
        "venue": (p.get("venue") or "Unknown")[:60],
        "abstract": ab[:800] + ("\u2026" if len(ab) > 800 else ""),
        "source": p.get("source") or "unknown",
        "link": p.get("link") or "#",
    }


def render_contradiction(papers: list, height: int = 700) -> str:
    if len(papers) < 2:
        return "<div style='padding:20px;color:#7aa8cc;font-family:monospace'>Butuh minimal 2 paper.</div>"

    norm = [_norm(p, i) for i, p in enumerate(papers)]
    pj   = json.dumps(norm, ensure_ascii=True)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:100%;height:{height}px;overflow:hidden;background:#020810;color:#c8daf0;font-family:'Space Grotesk',sans-serif;}}
:root{{
  --bg:#020810;--bg2:#06121f;--bg3:#0a1a2e;
  --bdr:rgba(0,210,255,.12);--bdr2:rgba(0,210,255,.4);
  --th:#f0f8ff;--tm:#8ab8d4;--tl:#2a4a66;--tdim:#1a3044;
  --cyan:#00d4ff;--green:#00ffaa;--red:#ff4060;--amber:#ffb830;--purp:#b794f4;--pink:#ff6eb4;
  --mono:'JetBrains Mono',monospace;--disp:'Orbitron',monospace;--sans:'Space Grotesk',sans-serif;
}}
body::before{{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(ellipse 80% 40% at 50% -10%,rgba(0,120,200,.08),transparent),
             radial-gradient(ellipse 40% 60% at 100% 80%,rgba(100,0,200,.05),transparent);}}
body::after{{content:'';position:fixed;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.03) 2px,rgba(0,0,0,.03) 3px);}}

#hdr{{position:relative;z-index:10;height:48px;display:flex;align-items:center;gap:12px;
  padding:0 16px;border-bottom:1px solid var(--bdr);background:rgba(2,8,16,.97);flex-shrink:0;}}
.hdr-logo{{font-family:var(--disp);font-size:11px;font-weight:900;letter-spacing:4px;color:var(--red);
  text-shadow:0 0 20px rgba(255,64,96,.6);}}
.hdr-sep{{width:1px;height:20px;background:var(--bdr);}}
.hdr-sub{{font-family:var(--mono);font-size:9px;color:var(--tl);letter-spacing:2px;}}
.hdr-modes{{display:flex;gap:6px;margin-left:auto;}}
.mbn{{padding:5px 13px;border-radius:4px;cursor:pointer;font-family:var(--mono);font-size:9.5px;
  letter-spacing:1px;border:1px solid var(--bdr);color:var(--tm);background:transparent;transition:all .15s;}}
.mbn:hover{{border-color:var(--cyan);color:var(--cyan);background:rgba(0,212,255,.06);}}
.mbn.on{{border-color:var(--amber);color:var(--amber);background:rgba(255,184,48,.1);box-shadow:0 0 12px rgba(255,184,48,.2);}}
#pcnt{{font-family:var(--mono);font-size:9px;color:var(--tl);letter-spacing:1px;white-space:nowrap;}}

#root{{position:relative;z-index:2;height:calc({height}px - 48px);display:flex;flex-direction:column;}}
.view{{display:none;flex:1;min-height:0;}}
.view.on{{display:flex;}}

/* DUEL */
#v-duel{{flex-direction:row;}}
.ppnl{{width:280px;flex-shrink:0;display:flex;flex-direction:column;overflow:hidden;background:var(--bg2);}}
#ppnl-a{{border-right:1px solid var(--bdr);}}
#ppnl-b{{border-left:1px solid var(--bdr);}}
.ppnl-hdr{{flex-shrink:0;padding:10px 13px 9px;border-bottom:1px solid var(--bdr);background:rgba(2,8,16,.6);}}
.ppnl-lbl{{font-family:var(--disp);font-size:9px;font-weight:700;letter-spacing:3px;}}
.ppnl-hint{{font-family:var(--mono);font-size:8.5px;color:var(--tl);margin-top:2px;}}
.psel{{width:100%;margin-top:8px;background:rgba(6,18,32,.95);border:1px solid var(--bdr);
  border-radius:6px;color:var(--cyan);padding:8px 11px;font-family:var(--mono);font-size:11px;
  cursor:pointer;outline:none;appearance:none;transition:border-color .15s;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2300d4ff'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center;padding-right:28px;}}
.psel:focus{{border-color:var(--cyan);box-shadow:0 0 8px rgba(0,212,255,.2);}}
.psel option{{background:#061220;color:#c8daf0;}}
.pinfo{{flex:1;overflow-y:auto;padding:12px 13px;}}
.pinfo::-webkit-scrollbar{{width:3px;}}
.pinfo::-webkit-scrollbar-thumb{{background:rgba(0,210,255,.15);border-radius:3px;}}
.pi-title{{font-family:var(--sans);font-size:14px;font-weight:700;color:var(--th);line-height:1.4;margin-bottom:8px;}}
.pi-meta{{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;}}
.chip{{font-family:var(--mono);font-size:9.5px;padding:2px 9px;border-radius:4px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);color:var(--tm);}}
.chip.yr{{color:var(--cyan);border-color:rgba(0,212,255,.2);background:rgba(0,212,255,.06);}}
.chip.ct{{color:var(--amber);border-color:rgba(255,184,48,.2);background:rgba(255,184,48,.06);}}
.pi-sec{{font-family:var(--mono);font-size:8px;letter-spacing:2.5px;color:var(--tl);text-transform:uppercase;margin:10px 0 6px;}}
.ab-wrap{{font-family:var(--sans);font-size:11.5px;color:var(--tm);line-height:1.65;}}
.ab-wrap mark.pos{{background:rgba(0,255,170,.18);color:#00ffaa;border-radius:2px;padding:0 2px;font-style:normal;}}
.ab-wrap mark.neg{{background:rgba(255,64,96,.18);color:#ff6080;border-radius:2px;padding:0 2px;font-style:normal;}}
.ab-wrap mark.kw{{background:rgba(184,130,255,.15);color:#c4a0ff;border-radius:2px;padding:0 2px;font-style:normal;}}
.stance-wrap{{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px;}}
.stance{{font-family:var(--mono);font-size:9px;padding:2px 8px;border-radius:3px;font-weight:600;letter-spacing:.5px;}}
.st-s{{background:rgba(0,255,170,.1);color:#00ffaa;border:1px solid rgba(0,255,170,.25);}}
.st-c{{background:rgba(255,64,96,.1);color:#ff6080;border:1px solid rgba(255,64,96,.25);}}
.st-n{{background:rgba(255,255,255,.05);color:var(--tl);border:1px solid rgba(255,255,255,.08);}}
.pi-link{{display:inline-block;margin-top:10px;font-family:var(--mono);font-size:9.5px;letter-spacing:1px;text-decoration:none;opacity:.8;transition:opacity .15s;}}
.pi-link:hover{{opacity:1;}}

/* ARENA */
#arena{{flex:1;display:flex;flex-direction:column;position:relative;overflow:hidden;background:linear-gradient(180deg,#030c1a,#020810);}}
#arena::before{{content:'';position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(0,212,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(0,212,255,.018) 1px,transparent 1px);
  background-size:28px 28px;}}
.arena-hdr{{flex-shrink:0;padding:9px 15px;border-bottom:1px solid var(--bdr);background:rgba(2,8,16,.7);
  display:flex;align-items:center;justify-content:center;gap:12px;position:relative;z-index:2;}}
.arena-ttl{{font-family:var(--disp);font-size:9px;font-weight:700;letter-spacing:4px;color:var(--amber);text-shadow:0 0 12px rgba(255,184,48,.4);}}
#btn-swap{{position:absolute;right:12px;background:rgba(255,184,48,.08);border:1px solid rgba(255,184,48,.3);
  border-radius:5px;padding:5px 12px;font-family:var(--mono);font-size:9.5px;color:var(--amber);cursor:pointer;transition:all .15s;}}
#btn-swap:hover{{background:rgba(255,184,48,.2);}}

#score-zone{{flex-shrink:0;display:flex;border-bottom:1px solid var(--bdr);position:relative;z-index:1;}}
#meter-col{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:12px 16px;border-right:1px solid var(--bdr);gap:7px;}}
.m-lbl{{font-family:var(--disp);font-size:8.5px;letter-spacing:3px;color:var(--tl);}}
.m-score{{font-family:var(--disp);font-size:44px;font-weight:900;letter-spacing:1px;line-height:1;transition:color .6s;text-shadow:0 0 30px currentColor;}}
.m-sub{{font-family:var(--mono);font-size:9.5px;color:var(--tl);letter-spacing:2px;}}
.m-track{{width:100%;height:16px;background:rgba(255,255,255,.04);border-radius:8px;overflow:hidden;border:1px solid rgba(255,255,255,.06);}}
.m-fill{{height:100%;border-radius:8px;transition:width 1s cubic-bezier(.4,0,.2,1);position:relative;overflow:hidden;}}
.m-fill::after{{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.25),transparent);animation:sheen 2s ease-in-out infinite;}}
@keyframes sheen{{from{{transform:translateX(-100%)}}to{{transform:translateX(200%)}}}}
.m-ticks{{width:100%;display:flex;justify-content:space-between;}}
.mtick{{font-family:var(--mono);font-size:8px;color:var(--tdim);}}
#bd-col{{flex:1;padding:12px 15px;display:flex;flex-direction:column;justify-content:center;gap:0;}}
.bd-hdr{{font-family:var(--disp);font-size:8px;letter-spacing:2.5px;color:var(--tl);text-transform:uppercase;margin-bottom:9px;}}
.bd-row{{display:flex;align-items:center;gap:8px;margin-bottom:7px;}}
.bd-key{{font-family:var(--mono);font-size:10px;color:var(--tm);width:110px;flex-shrink:0;text-align:right;}}
.bd-bg{{flex:1;height:9px;background:rgba(255,255,255,.05);border-radius:4px;overflow:hidden;}}
.bd-fill{{height:100%;border-radius:4px;transition:width .9s cubic-bezier(.4,0,.2,1);}}
.bd-val{{font-family:var(--disp);font-size:11px;font-weight:700;width:28px;flex-shrink:0;}}

#arena-tabs{{flex-shrink:0;display:flex;border-bottom:1px solid var(--bdr);background:rgba(2,8,16,.5);position:relative;z-index:2;}}
.atab{{flex:1;padding:7px 4px;text-align:center;font-family:var(--mono);font-size:9px;letter-spacing:1px;
  color:var(--tl);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;}}
.atab:hover{{color:var(--tm);}}
.atab.on{{color:var(--cyan);border-bottom-color:var(--cyan);background:rgba(0,212,255,.05);}}
#arena-body{{flex:1;overflow-y:auto;position:relative;z-index:1;}}
#arena-body::-webkit-scrollbar{{width:3px;}}
#arena-body::-webkit-scrollbar-thumb{{background:rgba(0,212,255,.1);border-radius:3px;}}
.apanel{{display:none;padding:14px 16px 50px;flex-direction:column;gap:10px;}}
.apanel.on{{display:flex;}}

.verdict-box{{padding:12px 14px;border-radius:8px;border:1px solid;}}
.verdict-ttl{{font-family:var(--disp);font-size:9.5px;font-weight:700;letter-spacing:2px;margin-bottom:6px;}}
.verdict-txt{{font-family:var(--sans);font-size:12.5px;line-height:1.6;color:var(--tm);}}
.recon-box{{padding:10px 13px;border-radius:6px;background:rgba(184,130,255,.07);border:1px solid rgba(184,130,255,.2);margin-top:2px;}}
.recon-lbl{{font-family:var(--mono);font-size:8.5px;letter-spacing:2px;color:var(--purp);margin-bottom:5px;}}
.recon-txt{{font-family:var(--sans);font-size:11.5px;color:#c0a0e8;line-height:1.55;}}

.claim-pair{{border:1px solid rgba(255,255,255,.06);border-radius:7px;overflow:hidden;margin-bottom:2px;}}
.cp-hdr{{display:flex;font-family:var(--mono);font-size:8.5px;letter-spacing:1px;}}
.cp-a{{flex:1;padding:5px 10px;background:rgba(0,255,170,.06);color:var(--green);text-align:center;}}
.cp-vs{{padding:5px 8px;background:rgba(255,255,255,.03);color:var(--tl);border-left:1px solid rgba(255,255,255,.06);border-right:1px solid rgba(255,255,255,.06);}}
.cp-b{{flex:1;padding:5px 10px;background:rgba(255,64,96,.06);color:var(--red);text-align:center;}}
.cp-body{{display:flex;}}
.cp-ta{{flex:1;padding:9px 11px;font-family:var(--sans);font-size:11px;color:var(--tm);line-height:1.55;text-align:right;background:rgba(0,255,170,.03);border-top:1px solid rgba(255,255,255,.04);}}
.cp-icon{{padding:9px 7px;display:flex;align-items:center;font-size:14px;border-top:1px solid rgba(255,255,255,.04);}}
.cp-tb{{flex:1;padding:9px 11px;font-family:var(--sans);font-size:11px;color:var(--tm);line-height:1.55;background:rgba(255,64,96,.03);border-top:1px solid rgba(255,255,255,.04);}}
.no-claims{{text-align:center;font-family:var(--mono);font-size:10.5px;color:var(--tl);padding:20px;opacity:.6;}}

.kb-sec{{font-family:var(--mono);font-size:8.5px;letter-spacing:2px;color:var(--tl);text-transform:uppercase;text-align:center;margin-bottom:8px;}}
.kb-shared{{display:flex;flex-wrap:wrap;gap:5px;justify-content:center;margin-bottom:10px;}}
.kb-tag{{font-family:var(--mono);font-size:9.5px;padding:3px 9px;border-radius:4px;background:rgba(184,130,255,.1);border:1px solid rgba(184,130,255,.25);color:var(--purp);}}
.kb-row{{display:flex;align-items:center;border-radius:5px;overflow:hidden;border:1px solid rgba(255,255,255,.06);margin-bottom:5px;}}
.kb-a{{flex:1;padding:7px 10px;text-align:right;background:rgba(0,255,170,.06);font-family:var(--mono);font-size:10.5px;color:var(--green);font-weight:600;}}
.kb-mid{{padding:7px 8px;background:rgba(255,255,255,.03);font-family:var(--mono);font-size:8.5px;color:var(--tl);border-left:1px solid rgba(255,255,255,.06);border-right:1px solid rgba(255,255,255,.06);}}
.kb-b{{flex:1;padding:7px 10px;background:rgba(255,64,96,.06);font-family:var(--mono);font-size:10.5px;color:var(--red);font-weight:600;}}

.tl-item{{display:flex;gap:10px;align-items:flex-start;margin-bottom:8px;}}
.tl-year{{font-family:var(--disp);font-size:13px;font-weight:700;color:var(--amber);width:44px;flex-shrink:0;line-height:1.2;}}
.tl-bar{{width:3px;flex-shrink:0;border-radius:2px;margin-top:4px;align-self:stretch;min-height:16px;}}
.tl-info{{flex:1;}}
.tl-title{{font-family:var(--sans);font-size:11px;font-weight:600;color:var(--th);margin-bottom:3px;line-height:1.4;}}
.tl-stance{{display:inline-block;font-family:var(--mono);font-size:8.5px;letter-spacing:.5px;padding:2px 7px;border-radius:3px;margin-bottom:4px;}}
.tl-snippet{{font-family:var(--sans);font-size:10.5px;color:var(--tm);line-height:1.5;}}

.btn-export{{width:100%;padding:10px;text-align:center;background:rgba(184,130,255,.07);
  border:1px solid rgba(184,130,255,.3);border-radius:6px;color:var(--purp);cursor:pointer;
  font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;transition:all .15s;}}
.btn-export:hover{{background:rgba(184,130,255,.18);border-color:var(--purp);box-shadow:0 0 12px rgba(184,130,255,.2);}}

#hist{{position:absolute;bottom:0;left:0;right:0;background:rgba(2,8,16,.97);
  border-top:1px solid var(--bdr);z-index:30;transition:height .28s cubic-bezier(.4,0,.2,1);height:36px;overflow:hidden;}}
#hist.open{{height:128px;}}
#hist-tog{{height:36px;display:flex;align-items:center;gap:8px;padding:0 14px;cursor:pointer;}}
.hist-lbl{{font-family:var(--mono);font-size:9px;color:var(--tl);letter-spacing:1.5px;}}
#hist-cnt{{font-family:var(--mono);font-size:9px;color:var(--cyan);padding:1px 7px;border-radius:3px;background:rgba(0,212,255,.07);border:1px solid rgba(0,212,255,.2);}}
.hist-arr{{margin-left:auto;font-size:10px;color:var(--tl);transition:transform .28s;}}
#hist.open .hist-arr{{transform:rotate(180deg);}}
#hist-list{{height:92px;overflow-x:auto;overflow-y:hidden;display:flex;gap:8px;padding:0 14px 10px;align-items:center;}}
#hist-list::-webkit-scrollbar{{height:3px;}}
#hist-list::-webkit-scrollbar-thumb{{background:rgba(0,212,255,.15);border-radius:3px;}}
.hcard{{flex-shrink:0;width:155px;background:rgba(6,18,32,.95);border:1px solid var(--bdr);border-radius:6px;padding:8px 10px;cursor:pointer;transition:border-color .15s;}}
.hcard:hover{{border-color:var(--cyan);}}
.hcard-sc{{font-family:var(--disp);font-size:18px;font-weight:900;letter-spacing:1px;line-height:1;}}
.hcard-tt{{font-family:var(--mono);font-size:8px;color:var(--tl);margin-top:5px;line-height:1.4;}}

.empty{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;opacity:.35;}}
.empty-ic{{font-size:36px;}}
.empty-tx{{font-family:var(--mono);font-size:11px;color:var(--tl);letter-spacing:.5px;text-align:center;line-height:1.65;}}

/* ROYALE */
#v-royale{{flex-direction:column;}}
.ry-hdr{{flex-shrink:0;padding:10px 16px;border-bottom:1px solid var(--bdr);background:rgba(2,8,16,.8);display:flex;align-items:center;justify-content:space-between;}}
.ry-ttl{{font-family:var(--disp);font-size:10px;font-weight:700;letter-spacing:3px;color:var(--purp);text-shadow:0 0 12px rgba(184,130,255,.4);}}
.ry-sub{{font-family:var(--mono);font-size:8.5px;color:var(--tl);margin-top:3px;}}
#ry-legend{{display:flex;gap:12px;}}
.ry-leg{{font-family:var(--mono);font-size:8.5px;display:flex;align-items:center;gap:5px;}}
.ry-dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0;}}
#ry-body{{flex:1;overflow:auto;padding:14px 16px;}}
#ry-body::-webkit-scrollbar{{width:4px;height:4px;}}
#ry-body::-webkit-scrollbar-thumb{{background:rgba(0,212,255,.15);border-radius:3px;}}
#ry-table{{border-collapse:collapse;}}
.rt-corner{{width:32px;height:32px;}}
.rt-ch{{font-family:var(--mono);font-size:9px;color:var(--tm);padding:0 5px;max-width:100px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;writing-mode:vertical-rl;transform:rotate(180deg);height:90px;vertical-align:bottom;padding-bottom:6px;}}
.rt-rh{{font-family:var(--mono);font-size:9px;color:var(--tm);padding:3px 10px;max-width:120px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;}}
.rt-cell{{width:44px;height:44px;text-align:center;cursor:pointer;border:1px solid rgba(255,255,255,.03);transition:transform .12s,box-shadow .12s;vertical-align:middle;}}
.rt-cell:hover{{transform:scale(1.18);z-index:5;box-shadow:0 0 16px rgba(0,0,0,.8);}}
.rt-cell span{{font-family:var(--disp);font-size:10.5px;font-weight:700;}}
.rt-diag{{background:rgba(255,255,255,.02);cursor:default;}}
.rt-diag:hover{{transform:none;box-shadow:none;}}
.most-badge{{font-family:var(--mono);font-size:7.5px;padding:1px 5px;border-radius:3px;background:rgba(255,184,48,.15);border:1px solid rgba(255,184,48,.35);color:var(--amber);margin-left:5px;vertical-align:middle;}}
</style>
</head>
<body>

<script type="application/json" id="__papers_data__">{pj}</script>

<div id="hdr">
  <span class="hdr-logo">&#9889; CONTRADICTION DETECTOR</span>
  <div class="hdr-sep"></div>
  <span class="hdr-sub">V4 &nbsp;&#183;&nbsp; CLAIM ANALYSIS ENGINE</span>
  <div class="hdr-modes">
    <button class="mbn on" id="btn-duel"   onclick="setMode('duel')">&#9876; 1 VS 1</button>
    <button class="mbn"    id="btn-royale" onclick="setMode('royale')">&#127942; BATTLE ROYALE</button>
  </div>
  <div class="hdr-sep"></div>
  <span id="pcnt"></span>
</div>

<div id="root">
  <div class="view on" id="v-duel">

    <div class="ppnl" id="ppnl-a">
      <div class="ppnl-hdr" style="border-top:3px solid var(--green)">
        <div class="ppnl-lbl" style="color:var(--green)">&#9672; PAPER A</div>
        <div class="ppnl-hint">Pilih paper pertama</div>
        <select class="psel" id="sel-a" onchange="onSel()"></select>
      </div>
      <div class="pinfo" id="info-a">
        <div class="empty"><div class="empty-ic">&#128196;</div><div class="empty-tx">Pilih Paper A</div></div>
      </div>
    </div>

    <div id="arena">
      <div class="arena-hdr">
        <span class="arena-ttl">&#9876; BATTLE ARENA</span>
        <button id="btn-swap" onclick="swap()">&#8644; SWAP</button>
      </div>

      <div id="score-zone">
        <div id="meter-col">
          <div class="m-lbl">CONTRADICTION SCORE</div>
          <div class="m-score" id="m-score" style="color:var(--tl)">&#8212;</div>
          <div class="m-sub">/ 100</div>
          <div class="m-track"><div class="m-fill" id="m-fill" style="width:0%"></div></div>
          <div class="m-ticks"><span class="mtick">SEJALAN</span><span class="mtick">50</span><span class="mtick">KONFLIK</span></div>
        </div>
        <div id="bd-col">
          <div class="bd-hdr">&#11041; Score Breakdown</div>
          <div class="bd-row">
            <div class="bd-key">Keyword overlap</div>
            <div class="bd-bg"><div class="bd-fill" id="bd-kw" style="width:0%;background:var(--purp)"></div></div>
            <div class="bd-val" id="bv-kw" style="color:var(--purp)">0</div>
          </div>
          <div class="bd-row">
            <div class="bd-key">Signal clash</div>
            <div class="bd-bg"><div class="bd-fill" id="bd-sg" style="width:0%;background:var(--red)"></div></div>
            <div class="bd-val" id="bv-sg" style="color:var(--red)">0</div>
          </div>
          <div class="bd-row">
            <div class="bd-key">Claim conflict</div>
            <div class="bd-bg"><div class="bd-fill" id="bd-cl" style="width:0%;background:var(--pink)"></div></div>
            <div class="bd-val" id="bv-cl" style="color:var(--pink)">0</div>
          </div>
          <div class="bd-row" style="margin-bottom:0">
            <div class="bd-key">Time gap</div>
            <div class="bd-bg"><div class="bd-fill" id="bd-tm" style="width:0%;background:var(--amber)"></div></div>
            <div class="bd-val" id="bv-tm" style="color:var(--amber)">0</div>
          </div>
        </div>
      </div>

      <div id="arena-tabs">
        <div class="atab on" id="tab-verdict"  onclick="setTab('verdict')">&#9889; VERDICT</div>
        <div class="atab"    id="tab-claims"   onclick="setTab('claims')">&#128196; CLAIMS</div>
        <div class="atab"    id="tab-keywords" onclick="setTab('keywords')">&#128273; KEYWORDS</div>
        <div class="atab"    id="tab-timeline" onclick="setTab('timeline')">&#128337; TIMELINE</div>
      </div>

      <div id="arena-body">
        <div class="apanel on" id="panel-verdict">
          <div class="empty"><div class="empty-ic">&#9889;</div><div class="empty-tx">Pilih Paper A dan B<br>untuk analisis</div></div>
        </div>
        <div class="apanel" id="panel-claims">
          <div class="empty"><div class="empty-ic">&#128196;</div><div class="empty-tx">Pilih dua paper</div></div>
        </div>
        <div class="apanel" id="panel-keywords">
          <div class="empty"><div class="empty-ic">&#128273;</div><div class="empty-tx">Pilih dua paper</div></div>
        </div>
        <div class="apanel" id="panel-timeline">
          <div class="empty"><div class="empty-ic">&#128337;</div><div class="empty-tx">Pilih dua paper</div></div>
        </div>
      </div>

      <div id="hist">
        <div id="hist-tog" onclick="document.getElementById('hist').classList.toggle('open')">
          <span style="font-size:12px">&#128203;</span>
          <span class="hist-lbl">RIWAYAT</span>
          <span id="hist-cnt">0</span>
          <span class="hist-arr">&#9650;</span>
        </div>
        <div id="hist-list"></div>
      </div>
    </div>

    <div class="ppnl" id="ppnl-b">
      <div class="ppnl-hdr" style="border-top:3px solid var(--red)">
        <div class="ppnl-lbl" style="color:var(--red)">&#9672; PAPER B</div>
        <div class="ppnl-hint">Pilih paper kedua</div>
        <select class="psel" id="sel-b" onchange="onSel()"></select>
      </div>
      <div class="pinfo" id="info-b">
        <div class="empty"><div class="empty-ic">&#128196;</div><div class="empty-tx">Pilih Paper B</div></div>
      </div>
    </div>

  </div>

  <div class="view" id="v-royale">
    <div class="ry-hdr">
      <div>
        <div class="ry-ttl">&#127942; BATTLE ROYALE MATRIX</div>
        <div class="ry-sub">Klik sel &#8594; buka duel &nbsp;&#183;&nbsp; &#9889; = most controversial paper</div>
      </div>
      <div id="ry-legend">
        <div class="ry-leg"><div class="ry-dot" style="background:#ff4060"></div><span style="color:#ff6080">Konflik Tinggi</span></div>
        <div class="ry-leg"><div class="ry-dot" style="background:#ffb830"></div><span style="color:#ffcc60">Berpotensi</span></div>
        <div class="ry-leg"><div class="ry-dot" style="background:#00ffaa"></div><span style="color:#60ffc0">Sejalan</span></div>
      </div>
    </div>
    <div id="ry-body"><table id="ry-table"></table></div>
  </div>
</div>

<script>
const PAPERS = JSON.parse(document.getElementById('__papers_data__').textContent);

const SW = new Set(["a","an","the","and","or","but","in","on","at","to","for","of","with","by","from","as","is","was","are","were","be","been","have","has","had","do","does","did","will","would","could","should","may","might","not","this","that","these","those","it","its","we","our","their","they","paper","study","research","propose","present","show","result","results","approach","method","methods","using","used","use","based","novel","new","existing","previous","however","also","which","such","than","more","most","work","model","system","data","two","three","one","can","well","significant","significantly","evaluate","experiment","dataset"]);
const POS=["improve","improves","improved","outperform","superior","better","effective","efficient","accurate","robust","strong","increase","enhance","advantage","promising","validates","supports","achieves","success","beneficial","positive","greater","faster","best","significant","high","boost","gain","exceed","surpass"];
const NEG=["fail","fails","failed","failure","poor","worse","inferior","ineffective","inaccurate","weak","insignificant","decrease","limitation","drawback","challenge","problem","limited","lacks","unable","insufficient","smaller","slower","worst","negative","doubt","low","lack","inadequate","suboptimal"];
const CP=[["improve","fail"],["effective","ineffective"],["accurate","inaccurate"],["robust","weak"],["superior","inferior"],["increase","decrease"],["high","low"],["strong","weak"],["better","worse"],["success","failure"],["beneficial","harmful"],["positive","negative"],["greater","smaller"],["faster","slower"],["best","worst"],["validates","contradicts"],["supports","refutes"],["significant","insignificant"],["boost","decrease"],["gain","lack"]];

function esc(s){{return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function tok(t){{return((t||'').toLowerCase().match(/[a-z][a-z0-9-]{{2,}}/g)||[]).filter(w=>!SW.has(w));}}
function sclr(s){{return s>=65?'#ff4060':s>=35?'#ffb830':'#00ffaa';}}
function sbg(s){{return s>=65?'rgba(255,64,96,.08)':s>=35?'rgba(255,184,48,.08)':'rgba(0,255,170,.08)';}}
function sbdr(s){{return s>=65?'rgba(255,64,96,.35)':s>=35?'rgba(255,184,48,.35)':'rgba(0,255,170,.35)';}}
function slbl(s){{return s>=65?'\u26a1 KONFLIK TINGGI':s>=35?'\u26a0\ufe0f BERPOTENSI BERBEDA':'\u2705 RELATIF SEJALAN';}}

function extractClaims(text){{
  if(!text)return[];
  return(text.match(/[^.!?]{{20,}}[.!?]/g)||[]).map(s=>s.trim()).filter(s=>s.length>25&&s.length<250).slice(0,8);
}}

function highlightAbs(text,sharedKws){{
  if(!text)return'';
  let out=esc(text);
  POS.forEach(w=>{{out=out.replace(new RegExp('\\b'+w+'\\b','gi'),m=>'<mark class="pos">'+m+'</mark>');}});
  NEG.forEach(w=>{{out=out.replace(new RegExp('\\b'+w+'\\b','gi'),m=>'<mark class="neg">'+m+'</mark>');}});
  sharedKws.slice(0,8).forEach(k=>{{if(k.length>3)out=out.replace(new RegExp('\\b'+k+'\\b','gi'),m=>'<mark class="kw">'+m+'</mark>');}});
  return out;
}}

function detectStance(text){{
  const t=(text||'').toLowerCase();
  const p=POS.filter(w=>t.includes(w)).length;
  const n=NEG.filter(w=>t.includes(w)).length;
  if(p>n)return{{label:'SUPPORTS',cls:'st-s'}};
  if(n>p)return{{label:'CONTRADICTS',cls:'st-c'}};
  return{{label:'NEUTRAL',cls:'st-n'}};
}}

function reconcileHint(p1,p2){{
  const y1=parseInt(p1.year)||0,y2=parseInt(p2.year)||0,gap=Math.abs(y1-y2);
  if(gap>=5)return'Diterbitkan '+gap+' tahun berbeda \u2014 kemungkinan konteks teknologi atau paradigma riset yang berbeda.';
  const t1=(p1.abstract||'').toLowerCase(),t2=(p2.abstract||'').toLowerCase();
  if((t1.includes('clinical')||t1.includes('patient'))!==(t2.includes('clinical')||t2.includes('patient')))
    return'Salah satu paper berfokus klinis, yang lain mungkin bersifat teoritis atau komputasional.';
  if(p1.venue&&p2.venue&&p1.venue!==p2.venue&&p1.venue!=='Unknown')
    return'Venue berbeda \u2014 mungkin menyasar audiens atau subdomain yang tidak identik.';
  return'Kontradiksi kemungkinan bersumber dari perbedaan dataset, ukuran sampel, atau definisi operasional variabel.';
}}

function buildClaimPairs(p1,p2){{
  const c1=extractClaims(p1.abstract),c2=extractClaims(p2.abstract);
  if(!c1.length||!c2.length)return[];
  const pairs=[];
  for(let i=0;i<Math.min(c1.length,c2.length,4);i++){{
    const s1=detectStance(c1[i]),s2=detectStance(c2[i]);
    const conflict=(s1.label==='SUPPORTS'&&s2.label==='CONTRADICTS')||(s1.label==='CONTRADICTS'&&s2.label==='SUPPORTS');
    pairs.push({{a:c1[i],b:c2[i],conflict,s1,s2}});
  }}
  return pairs.sort((a,b)=>b.conflict-a.conflict);
}}

const _BC={{}};
function battle(ia,ib){{
  const k=ia<ib?ia+'_'+ib:ib+'_'+ia;
  if(_BC[k])return _BC[k];
  const p1=PAPERS[ia],p2=PAPERS[ib];
  const t1=((p1.title||'')+' '+(p1.abstract||'')).toLowerCase();
  const t2=((p2.title||'')+' '+(p2.abstract||'')).toLowerCase();
  const s1=new Set(tok(t1)),s2=new Set(tok(t2));
  const sh=[...s1].filter(w=>s2.has(w)&&!SW.has(w)).sort();
  const pos1=POS.filter(w=>t1.includes(w)),neg1=NEG.filter(w=>t1.includes(w));
  const pos2=POS.filter(w=>t2.includes(w)),neg2=NEG.filter(w=>t2.includes(w));
  const ct=[],cs=new Set();
  for(const[a,b]of CP){{
    const k2=a+'|'+b;if(cs.has(k2))continue;
    if(pos1.includes(a)&&neg2.includes(b)){{ct.push({{a,b}});cs.add(k2);}}
    else if(neg1.includes(b)&&pos2.includes(a)){{ct.push({{a:b,b:a}});cs.add(k2);}}
  }}
  const cp=buildClaimPairs(p1,p2);
  const yr1=parseInt(p1.year)||0,yr2=parseInt(p2.year)||0,tGap=Math.min(Math.abs(yr1-yr2),16);
  const kwS=Math.min(sh.length*3,30),sgS=Math.min(ct.length*16,48),clS=Math.min(cp.filter(x=>x.conflict).length*10,18),tmS=tGap;
  const sc=Math.min(100,kwS+sgS+clS+tmS);
  const r={{sc,sh:sh.slice(0,12),pos1:pos1.slice(0,6),neg1:neg1.slice(0,6),pos2:pos2.slice(0,6),neg2:neg2.slice(0,6),ct:ct.slice(0,6),claimPairs:cp,bd:{{kw:kwS,sg:sgS,cl:clS,tm:tmS}},recon:reconcileHint(p1,p2),vl:sc>=65?'high':sc>=35?'medium':'low',vt:sc>=65?'Paper ini menunjukkan KONTRADIKSI SIGNIFIKAN. Keduanya membahas topik serupa ('+sh.length+' keyword overlap) namun sinyal dan klaim menunjukkan arah yang berlawanan \u2014 kemungkinan perbedaan metodologi, dataset, atau konteks studi.':sc>=35?'Terdapat POTENSI PERBEDAAN antara kedua paper. Ada '+sh.length+' keyword bersama namun beberapa klaim mungkin bertentangan. Disarankan membaca kedua abstrak secara menyeluruh.':'Kedua paper relatif SEJALAN. Mereka berbagi '+sh.length+' keyword dan tidak menunjukkan sinyal yang eksplisit berlawanan. Kemungkinan besar saling melengkapi.'}};
  _BC[k]=r;return r;
}}

function renderInfo(elId,paper,side,bt){{
  const el=document.getElementById(elId);
  const clr=side==='a'?'var(--green)':'var(--red)';
  const sh=bt?bt.sh:[];
  const absHtml=highlightAbs(paper.abstract,sh);
  const stances=extractClaims(paper.abstract).slice(0,4).map(c=>{{const st=detectStance(c);return'<span class="stance '+st.cls+'">'+st.label+'</span>';}}).join('');
  el.innerHTML='<div class="pi-title">'+esc(paper.title)+'</div>'+
    '<div class="pi-meta"><span class="chip yr">&#128197; '+paper.year+'</span><span class="chip ct">&#8679; '+Number(paper.citations).toLocaleString()+' sitasi</span><span class="chip">'+esc(paper.source)+'</span></div>'+
    '<div class="pi-sec">Penulis</div><div style="font-family:var(--mono);font-size:10.5px;color:var(--tm);margin-bottom:8px;line-height:1.45">'+esc(paper.authors)+'</div>'+
    '<div class="pi-sec">Abstrak <span style="color:var(--tl);font-size:7.5px;margin-left:4px">&#9632;hijau=positif &#9632;merah=negatif &#9632;ungu=shared</span></div>'+
    '<div class="ab-wrap" style="margin-bottom:8px">'+absHtml+'</div>'+
    (stances?'<div class="pi-sec">Stance</div><div class="stance-wrap">'+stances+'</div><br>':'')+
    '<a href="'+esc(paper.link)+'" target="_blank" class="pi-link" style="color:'+clr+'">&#10135; BUKA PAPER LENGKAP</a>';
}}

function updateScore(bt){{
  const sc=bt.sc,clr=sclr(sc);
  document.getElementById('m-score').textContent=sc;
  document.getElementById('m-score').style.color=clr;
  document.getElementById('m-score').style.textShadow='0 0 30px '+clr;
  const fill=document.getElementById('m-fill');
  fill.style.width=sc+'%';
  fill.style.background=sc>=65?'linear-gradient(90deg,#ff4060,#ff1040)':sc>=35?'linear-gradient(90deg,#ffb830,#ff8800)':'linear-gradient(90deg,#00ffaa,#00c87a)';
  fill.style.boxShadow='0 0 14px '+(sc>=65?'rgba(255,64,96,.5)':sc>=35?'rgba(255,184,48,.5)':'rgba(0,255,170,.5)');
  const max={{kw:30,sg:48,cl:18,tm:16}};
  ['kw','sg','cl','tm'].forEach(k=>{{document.getElementById('bd-'+k).style.width=Math.round(bt.bd[k]/max[k]*100)+'%';document.getElementById('bv-'+k).textContent='+'+bt.bd[k];}});
}}

function renderPanels(ia,ib,bt){{
  const sc=bt.sc;
  // VERDICT
  document.getElementById('panel-verdict').innerHTML=
    '<div class="verdict-box" style="border-color:'+sbdr(sc)+';background:'+sbg(sc)+'">'+
    '<div class="verdict-ttl" style="color:'+sclr(sc)+'">'+slbl(sc)+'</div>'+
    '<div class="verdict-txt">'+esc(bt.vt)+'</div></div>'+
    '<div class="recon-box"><div class="recon-lbl">&#129300; RECONCILIATION HINT</div><div class="recon-txt">'+esc(bt.recon)+'</div></div>'+
    '<button class="btn-export" onclick="doExport('+ia+','+ib+')">&#11015; EXPORT SINTESIS LITERATURE</button>';

  // CLAIMS
  const pairs=bt.claimPairs;
  if(!pairs.length){{document.getElementById('panel-claims').innerHTML='<div class="no-claims">Abstrak terlalu pendek<br>untuk ekstraksi klaim.</div>';}}
  else{{
    document.getElementById('panel-claims').innerHTML='<div style="font-family:var(--mono);font-size:8.5px;color:var(--tl);letter-spacing:1.5px;text-align:center;margin-bottom:4px">CLAIM VS CLAIM \u2014 HEAD TO HEAD</div>'+
    pairs.map(p=>'<div class="claim-pair" style="border-color:'+(p.conflict?'rgba(255,64,96,.25)':'rgba(255,255,255,.06)')+'">'+
      '<div class="cp-hdr"><div class="cp-a">A &nbsp;<span class="'+p.s1.cls+'" style="font-size:8px;padding:1px 5px;border-radius:2px;background:rgba(0,0,0,.3)">'+p.s1.label+'</span></div>'+
      '<div class="cp-vs">'+(p.conflict?'&#9889;':'&#8651;')+'</div>'+
      '<div class="cp-b"><span class="'+p.s2.cls+'" style="font-size:8px;padding:1px 5px;border-radius:2px;background:rgba(0,0,0,.3)">'+p.s2.label+'</span> &nbsp;B</div></div>'+
      '<div class="cp-body"><div class="cp-ta">'+esc(p.a)+'</div><div class="cp-icon">'+(p.conflict?'&#9889;':'&#10231;')+'</div><div class="cp-tb">'+esc(p.b)+'</div></div></div>'
    ).join('');
  }}

  // KEYWORDS
  document.getElementById('panel-keywords').innerHTML=
    '<div class="kb-sec">&#128273; Keyword Bersama ('+bt.sh.length+')</div>'+
    '<div class="kb-shared">'+(bt.sh.length?bt.sh.map(k=>'<span class="kb-tag">'+esc(k)+'</span>').join(''):'<span style="font-family:var(--mono);font-size:10px;color:var(--tl)">Tidak ada</span>')+'</div>'+
    (bt.ct.length?'<div class="kb-sec" style="margin-top:4px">&#9889; Sinyal Berlawanan ('+bt.ct.length+')</div>'+bt.ct.map(c=>'<div class="kb-row"><div class="kb-a">'+esc(c.a)+'</div><div class="kb-mid">&#8596;</div><div class="kb-b">'+esc(c.b)+'</div></div>').join(''):'<div style="text-align:center;font-family:var(--mono);font-size:10px;color:var(--tl);padding:14px">Tidak ada sinyal eksplisit yang berlawanan</div>');

  // TIMELINE
  const sorted=[ia,ib].map(i=>PAPERS[i]).sort((a,b)=>(a.year||0)-(b.year||0));
  document.getElementById('panel-timeline').innerHTML=
    '<div style="font-family:var(--mono);font-size:8.5px;color:var(--tl);letter-spacing:1.5px;text-align:center;margin-bottom:8px">EVIDENCE TIMELINE \u2014 KRONOLOGI POSISI RISET</div>'+
    sorted.map((p,idx)=>{{
      const isA=PAPERS.indexOf(p)===ia;
      const clr=isA?'#00ffaa':'#ff4060';
      const st=detectStance(p.abstract);
      const snip=(extractClaims(p.abstract)[0]||'').substring(0,120);
      return '<div class="tl-item"><div class="tl-year" style="color:'+clr+'">'+(p.year||'?')+'</div>'+
        '<div class="tl-bar" style="background:'+clr+'"></div>'+
        '<div class="tl-info"><div class="tl-title" style="color:'+clr+'">'+esc(p.short)+'</div>'+
        '<span class="tl-stance '+st.cls+'">'+st.label+'</span>'+
        (snip?'<div class="tl-snippet">'+esc(snip)+'...</div>':'')+
        '</div></div>'+(idx<sorted.length-1?'<div style="height:1px;background:var(--bdr);margin:6px 0 6px 54px"></div>':'');
    }}).join('');
}}

const _H=[];
function addH(ia,ib,sc){{
  if(_H.find(h=>(h.ia===ia&&h.ib===ib)||(h.ia===ib&&h.ib===ia)))return;
  _H.unshift({{ia,ib,sc}});
  document.getElementById('hist-cnt').textContent=_H.length;
  document.getElementById('hist-list').innerHTML=_H.map(h=>{{
    const pa=PAPERS[h.ia],pb=PAPERS[h.ib],clr=sclr(h.sc);
    return'<div class="hcard" onclick="loadH('+h.ia+','+h.ib+')"><div class="hcard-sc" style="color:'+clr+';text-shadow:0 0 12px '+clr+'">'+h.sc+'</div><div class="hcard-tt">'+esc(pa.short.substring(0,20))+'\u2026<br><span style="color:var(--tl)">vs</span> '+esc(pb.short.substring(0,20))+'\u2026</div></div>';
  }}).join('');
}}
function loadH(ia,ib){{document.getElementById('sel-a').value=ia;document.getElementById('sel-b').value=ib;onSel();}}

function setTab(t){{
  ['verdict','claims','keywords','timeline'].forEach(x=>{{
    document.getElementById('tab-'+x).classList.toggle('on',x===t);
    document.getElementById('panel-'+x).classList.toggle('on',x===t);
  }});
}}

function onSel(){{
  const ia=parseInt(document.getElementById('sel-a').value);
  const ib=parseInt(document.getElementById('sel-b').value);
  const bt=(ia>=0&&ib>=0&&ia!==ib)?battle(ia,ib):null;
  if(ia>=0&&PAPERS[ia])renderInfo('info-a',PAPERS[ia],'a',bt);
  if(ib>=0&&PAPERS[ib])renderInfo('info-b',PAPERS[ib],'b',bt);
  if(bt){{updateScore(bt);renderPanels(ia,ib,bt);addH(ia,ib,bt.sc);}}
  else{{
    document.getElementById('m-score').textContent='\u2014';
    document.getElementById('m-score').style.color='var(--tl)';
    document.getElementById('m-fill').style.width='0%';
    ['kw','sg','cl','tm'].forEach(id=>{{document.getElementById('bd-'+id).style.width='0%';document.getElementById('bv-'+id).textContent='0';}});
    document.getElementById('panel-verdict').innerHTML=ia===ib&&ia>=0
      ?'<div class="empty"><div class="empty-ic">&#9888;</div><div class="empty-tx">Paper A dan B tidak boleh sama</div></div>'
      :'<div class="empty"><div class="empty-ic">&#9889;</div><div class="empty-tx">Pilih Paper A dan B<br>untuk memulai analisis</div></div>';
  }}
}}

function swap(){{const sa=document.getElementById('sel-a'),sb=document.getElementById('sel-b');[sa.value,sb.value]=[sb.value,sa.value];onSel();}}

function doExport(ia,ib){{
  const bt=battle(ia,ib),pa=PAPERS[ia],pb=PAPERS[ib];
  const sl=bt.sc>=65?'KONTRADIKTIF':bt.sc>=35?'BERPOTENSI BERBEDA':'SEJALAN';
  const S='='.repeat(60),S2='-'.repeat(60);
  const conflictClaims=bt.claimPairs.filter(p=>p.conflict).slice(0,3).map((p,i)=>'  Klaim '+(i+1)+'A: '+p.a.substring(0,100)+'\n  Klaim '+(i+1)+'B: '+p.b.substring(0,100)).join('\n');
  const rep=[S,'LAPORAN SINTESIS LITERATURE REVIEW',S,'',
    'Paper A : '+pa.title,'  Tahun  : '+pa.year+' | Sitasi: '+pa.citations,'  Penulis: '+pa.authors,'',
    'Paper B : '+pb.title,'  Tahun  : '+pb.year+' | Sitasi: '+pb.citations,'  Penulis: '+pb.authors,'',S2,
    'HASIL: '+sl+' (Score: '+bt.sc+'/100)','',
    'Breakdown  : Keyword +'+bt.bd.kw+' | Signal +'+bt.bd.sg+' | Claim +'+bt.bd.cl+' | Time +'+bt.bd.tm,
    'Keyword    : '+(bt.sh.join(', ')||'\u2014'),
    'Sinyal     : '+(bt.ct.map(c=>c.a+' \u2194 '+c.b).join('; ')||'\u2014'),'',
    (conflictClaims?'Claim Konflik:\n'+conflictClaims+'\n':''),
    'Reconciliation: '+bt.recon,'',S2,
    'KALIMAT SIAP PAKAI (Tinjauan Pustaka):','',
    '"'+pa.title+' ('+pa.year+') '+(bt.sc>=65?'secara signifikan bertentangan dengan':bt.sc>=35?'menunjukkan perbedaan pandangan dengan':'sejalan dengan')+
    ' '+pb.title+' ('+pb.year+'). Keduanya membahas topik terkait ('+bt.sh.slice(0,5).join(', ')+')'+(bt.ct.length?', namun terdapat perbedaan sinyal pada aspek: '+bt.ct.slice(0,3).map(c=>c.a+' vs '+c.b).join('; ')+'.':'.')+'"',
    '',S].join('\n');
  const blob=new Blob([rep],{{type:'text/plain;charset=utf-8'}});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='sintesis_'+pa.year+'_vs_'+pb.year+'.txt';a.click();URL.revokeObjectURL(url);
}}

function renderRoyale(){{
  const scores=PAPERS.map((_,i)=>{{let t=0;PAPERS.forEach((_,j)=>{{if(i!==j)t+=battle(i,j).sc;}});return t;}});
  const hotIdx=scores.indexOf(Math.max(...scores));
  let html='<thead><tr><th class="rt-corner"></th>';
  PAPERS.forEach((p,i)=>{{html+='<th class="rt-ch" title="'+esc(p.title)+'">'+esc(p.short.substring(0,16))+(i===hotIdx?'&#9889;':'')+'</th>';}});
  html+='</tr></thead><tbody>';
  PAPERS.forEach((pa,ia)=>{{
    html+='<tr><td class="rt-rh" title="'+esc(pa.title)+'">'+esc(pa.short.substring(0,20))+(ia===hotIdx?'<span class="most-badge">HOT</span>':'')+'</td>';
    PAPERS.forEach((pb,ib)=>{{
      if(ia===ib){{html+='<td class="rt-cell rt-diag"><div style="display:flex;align-items:center;justify-content:center;height:100%;font-family:var(--mono);font-size:8px;color:var(--tdim)">\u2014</div></td>';}}
      else{{
        const bt=battle(ia,ib),clr=sclr(bt.sc);
        const bg=bt.sc>=65?'rgba(255,64,96,'+(0.04+bt.sc/700)+')':bt.sc>=35?'rgba(255,184,48,'+(0.03+bt.sc/800)+')':'rgba(0,255,170,'+(0.02+bt.sc/1000)+')';
        html+='<td class="rt-cell" style="background:'+bg+'" title="'+esc(pa.short)+' vs '+esc(pb.short)+': '+bt.sc+'" onclick="openRoyale('+ia+','+ib+')"><span style="color:'+clr+'">'+bt.sc+'</span></td>';
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

(function init(){{
  const sa=document.getElementById('sel-a'),sb=document.getElementById('sel-b');
  const ph='<option value="-1">\u2014 Pilih paper \u2014</option>';
  const opts=PAPERS.map(p=>'<option value="'+p.id+'">'+p.year+' \u00b7 '+esc(p.short)+'</option>').join('');
  sa.innerHTML=ph+opts;sb.innerHTML=ph+opts;
  document.getElementById('pcnt').textContent=PAPERS.length+' PAPERS';
  if(PAPERS.length>=2){{sa.value='0';sb.value='1';onSel();}}
}})();
</script>
</body>
</html>"""
