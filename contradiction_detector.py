"""
contradiction_detector.py
=========================
Contradiction Detector v2 — Full Interactive Battle Arena
Fungsi publik: render_contradiction(papers, height=680) -> str
"""

import re
import json


def _normalize_paper(p: dict, idx: int) -> dict:
    title    = (p.get("title")    or "Untitled").strip()
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
        "short":    (title[:62] + "\u2026") if len(title) > 62 else title,
        "authors":  (p.get("authors") or "N/A")[:80],
        "year":     year or 0,
        "citations":cites,
        "venue":    (p.get("venue")   or "Unknown")[:60],
        "abstract": abstract[:700] + ("\u2026" if len(abstract) > 700 else ""),
        "source":   p.get("source")  or "unknown",
        "link":     p.get("link")    or "#",
    }


def render_contradiction(papers: list, height: int = 680) -> str:
    if len(papers) < 2:
        return "<div style='color:#7aa8cc;font-family:monospace;padding:20px'>Butuh minimal 2 paper.</div>"

    norm = [_normalize_paper(p, i) for i, p in enumerate(papers)]
    papers_json = (
        json.dumps(norm, ensure_ascii=False)
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
html,body{{width:100%;height:{H}px;overflow:hidden;background:#030c18;color:#c8daf0;font-family:'Inter',sans-serif;user-select:none;}}
:root{{
  --bg:#030c18;--bg2:#061626;--bdr:rgba(0,200,255,.13);--bdr2:rgba(0,200,255,.28);
  --th:#e8f4ff;--tm:#8ab8d8;--tl:#2d5070;
  --cyan:#00d4ff;--green:#00ffaa;--red:#ff4d6a;--amber:#ffb830;--purp:#b39dfa;
  --mono:'JetBrains Mono',monospace;--disp:'Orbitron',monospace;--sans:'Inter',sans-serif;
}}
body::after{{content:'';position:fixed;inset:0;pointer-events:none;z-index:998;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04) 2px,rgba(0,0,0,.04) 3px);}}
#hdr{{height:44px;display:flex;align-items:center;gap:12px;padding:0 18px;background:rgba(3,12,24,.98);border-bottom:1px solid var(--bdr);position:relative;z-index:20;flex-shrink:0;}}
.hdr-title{{font-family:var(--disp);font-size:12px;font-weight:700;letter-spacing:3px;color:var(--red);text-shadow:0 0 14px rgba(255,77,106,.5);}}
.hdr-sep{{width:1px;height:20px;background:var(--bdr);flex-shrink:0;}}
.hdr-sub{{font-family:var(--mono);font-size:9.5px;color:var(--tl);letter-spacing:1.5px;}}
#mode-btns{{display:flex;gap:6px;margin-left:auto;}}
.mbtn{{padding:5px 12px;border-radius:5px;cursor:pointer;font-family:var(--mono);font-size:9.5px;letter-spacing:.8px;border:1px solid var(--bdr);color:var(--tm);background:transparent;transition:all .15s;}}
.mbn:hover{{border-color:var(--bdr2);color:var(--th);}}
.mbn.on{{border-color:var(--amber);color:var(--amber);background:rgba(255,184,48,.08);}}
#root{{height:calc({H}px - 44px);display:flex;flex-direction:column;}}
.view{{display:none;flex:1;min-height:0;}}
.view.on{{display:flex;}}
/* DUEL */
#v-duel{{flex-direction:row;}}
.ppnl{{width:290px;flex-shrink:0;display:flex;flex-direction:column;overflow:hidden;}}
#ppnl-a{{border-right:1px solid var(--bdr);}}
#ppnl-b{{border-left:1px solid var(--bdr);}}
.ppnl-hdr{{flex-shrink:0;padding:10px 13px 9px;border-bottom:1px solid var(--bdr);background:rgba(3,12,24,.7);}}
.ppnl-lbl{{font-family:var(--disp);font-size:9px;font-weight:700;letter-spacing:3px;text-transform:uppercase;}}
.ppnl-hint{{font-family:var(--mono);font-size:8px;color:var(--tl);margin-top:3px;letter-spacing:.5px;}}
.psel{{width:100%;margin-top:9px;background:rgba(6,22,38,.95);border:1px solid var(--bdr);border-radius:6px;color:var(--cyan);padding:8px 11px;font-family:var(--mono);font-size:11px;cursor:pointer;outline:none;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2300d4ff'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;padding-right:28px;transition:border-color .15s;}}
.psel option{{background:#061626;color:#c8daf0;}}
.pinfo{{flex:1;overflow-y:auto;padding:12px 13px;}}
.pinfo::-webkit-scrollbar{{width:3px;}}
.pinfo::-webkit-scrollbar-thumb{{background:rgba(0,200,255,.15);border-radius:3px;}}
.pi-title{{font-family:var(--sans);font-size:13px;font-weight:600;color:var(--th);line-height:1.42;margin-bottom:9px;}}
.pi-chips{{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;}}
.chip{{font-family:var(--mono);font-size:9.5px;padding:3px 9px;border-radius:4px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:var(--tm);}}
.chip.yr{{color:var(--cyan);border-color:rgba(0,212,255,.22);background:rgba(0,212,255,.06);}}
.chip.ct{{color:var(--amber);border-color:rgba(255,184,48,.22);background:rgba(255,184,48,.06);}}
.pi-sec{{font-family:var(--mono);font-size:8px;letter-spacing:2px;color:var(--tl);text-transform:uppercase;margin-bottom:5px;margin-top:10px;}}
.pi-abs{{font-family:var(--sans);font-size:11px;color:var(--tm);line-height:1.55;}}
.sig-wrap{{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;}}
.sig{{font-family:var(--mono);font-size:9px;padding:2px 8px;border-radius:3px;font-weight:600;letter-spacing:.5px;}}
.sig-p{{background:rgba(0,255,170,.08);color:var(--green);border:1px solid rgba(0,255,170,.2);}}
.sig-n{{background:rgba(255,77,106,.08);color:var(--red);border:1px solid rgba(255,77,106,.2);}}
.claim-item{{display:flex;gap:7px;margin-bottom:7px;align-items:flex-start;}}
.claim-dot{{width:5px;height:5px;border-radius:50%;flex-shrink:0;margin-top:5px;}}
.claim-txt{{font-family:var(--sans);font-size:10.5px;color:var(--tm);line-height:1.45;}}
.pi-link{{display:inline-block;margin-top:10px;font-family:var(--mono);font-size:9.5px;letter-spacing:1px;text-decoration:none;}}
/* ARENA */
#arena{{flex:1;display:flex;flex-direction:column;background:linear-gradient(180deg,#040e1c,#030c18);position:relative;overflow:hidden;}}
#arena::before{{content:'';position:absolute;inset:0;pointer-events:none;background-image:linear-gradient(rgba(0,200,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,200,255,.025) 1px,transparent 1px);background-size:30px 30px;}}
.arena-hdr{{flex-shrink:0;padding:9px 16px 8px;border-bottom:1px solid var(--bdr);background:rgba(3,12,24,.6);display:flex;align-items:center;justify-content:center;position:relative;}}
.arena-title{{font-family:var(--disp);font-size:9px;font-weight:700;letter-spacing:3px;color:var(--amber);text-shadow:0 0 10px rgba(255,184,48,.3);}}
#btn-swap{{position:absolute;right:12px;top:50%;transform:translateY(-50%);background:rgba(255,184,48,.08);border:1px solid rgba(255,184,48,.25);border-radius:5px;padding:5px 12px;font-family:var(--mono);font-size:9.5px;color:var(--amber);cursor:pointer;letter-spacing:.5px;transition:all .15s;}}
#btn-swap:hover{{background:rgba(255,184,48,.18);border-color:var(--amber);}}
.arena-body{{flex:1;display:flex;flex-direction:column;align-items:center;padding:14px 20px;gap:13px;overflow-y:auto;position:relative;z-index:1;padding-bottom:46px;}}
.arena-body::-webkit-scrollbar{{width:3px;}}
.arena-body::-webkit-scrollbar-thumb{{background:rgba(0,200,255,.1);}}
/* METER */
.meter-lbl{{font-family:var(--disp);font-size:10px;letter-spacing:2.5px;color:var(--tl);text-transform:uppercase;}}
.meter-score{{font-family:var(--disp);font-size:34px;font-weight:700;letter-spacing:2px;line-height:1;transition:color .8s;text-shadow:0 0 22px currentColor;}}
.meter-sub{{font-family:var(--mono);font-size:10px;color:var(--tl);letter-spacing:2px;}}
.meter-track{{width:100%;height:24px;background:rgba(255,255,255,.04);border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,.07);}}
.meter-fill{{height:100%;border-radius:12px;transition:width 1s cubic-bezier(.4,0,.2,1);position:relative;overflow:hidden;}}
.meter-fill::after{{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.18),transparent);animation:sheen 2.2s ease-in-out infinite;}}
@keyframes sheen{{from{{transform:translateX(-100%)}}to{{transform:translateX(200%)}}}}
.mtick{{font-family:var(--mono);font-size:8.5px;color:var(--tl);}}
/* BREAKDOWN */
.conf-title{{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--tl);text-transform:uppercase;margin-bottom:8px;text-align:center;}}
.conf-row{{display:flex;align-items:center;gap:9px;margin-bottom:7px;}}
.conf-key{{font-family:var(--mono);font-size:10px;color:var(--tm);width:120px;flex-shrink:0;text-align:right;}}
.conf-bg{{flex:1;height:8px;background:rgba(255,255,255,.05);border-radius:4px;overflow:hidden;}}
.conf-fill{{height:100%;border-radius:4px;transition:width .8s cubic-bezier(.4,0,.2,1);}}
.conf-val{{font-family:var(--mono);font-size:10px;font-weight:600;width:28px;text-align:left;flex-shrink:0;}}
/* VERDICT */
.verdict-wrap{{width:100%;padding:12px 15px;border-radius:9px;border:1px solid;transition:all .6s;}}
.verdict-level{{font-family:var(--disp);font-size:9.5px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:7px;}}
.verdict-text{{font-family:var(--sans);font-size:11.5px;line-height:1.58;color:var(--tm);}}
/* KW BATTLE */
.kw-title{{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--tl);text-transform:uppercase;text-align:center;margin-bottom:8px;}}
.kw-shared{{display:flex;flex-wrap:wrap;gap:5px;justify-content:center;margin-bottom:10px;}}
.kw-stag{{font-family:var(--mono);font-size:9.5px;padding:3px 9px;border-radius:4px;background:rgba(179,157,250,.09);border:1px solid rgba(179,157,250,.22);color:var(--purp);}}
.kw-crow{{display:flex;align-items:center;border-radius:5px;overflow:hidden;border:1px solid rgba(255,255,255,.06);margin-bottom:5px;}}
.kw-a{{flex:1;padding:6px 9px;text-align:right;background:rgba(0,255,170,.07);font-family:var(--mono);font-size:10px;color:var(--green);font-weight:600;}}
.kw-vs{{padding:6px 8px;background:rgba(255,255,255,.04);font-family:var(--mono);font-size:8.5px;color:var(--tl);border-left:1px solid rgba(255,255,255,.06);border-right:1px solid rgba(255,255,255,.06);}}
.kw-b{{flex:1;padding:6px 9px;background:rgba(255,77,106,.07);font-family:var(--mono);font-size:10px;color:var(--red);font-weight:600;}}
/* EXPORT */
.btn-export{{width:100%;padding:10px;text-align:center;background:rgba(179,157,250,.07);border:1px solid rgba(179,157,250,.25);border-radius:7px;color:var(--purp);cursor:pointer;font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;transition:all .15s;}}
.btn-export:hover{{background:rgba(179,157,250,.16);border-color:var(--purp);}}
/* HISTORY */
#hist-panel{{position:absolute;bottom:0;left:0;right:0;background:rgba(3,12,24,.97);border-top:1px solid var(--bdr);z-index:30;transition:height .3s cubic-bezier(.4,0,.2,1);height:36px;overflow:hidden;}}
#hist-panel.open{{height:130px;}}
#hist-toggle{{height:36px;display:flex;align-items:center;gap:8px;padding:0 14px;cursor:pointer;}}
.hist-tlbl{{font-family:var(--mono);font-size:9.5px;color:var(--tl);letter-spacing:1.5px;}}
#hist-count{{font-family:var(--mono);font-size:9px;color:var(--cyan);padding:1px 7px;border-radius:3px;background:rgba(0,212,255,.08);border:1px solid rgba(0,212,255,.2);}}
.hist-arr{{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--tl);transition:transform .3s;}}
#hist-panel.open .hist-arr{{transform:rotate(180deg);}}
#hist-list{{height:94px;overflow-x:auto;overflow-y:hidden;display:flex;gap:8px;padding:0 14px 10px;align-items:center;}}
#hist-list::-webkit-scrollbar{{height:3px;}}
#hist-list::-webkit-scrollbar-thumb{{background:rgba(0,200,255,.15);border-radius:3px;}}
.hcard{{flex-shrink:0;width:170px;background:rgba(6,22,38,.9);border:1px solid var(--bdr);border-radius:7px;padding:8px 10px;cursor:pointer;transition:border-color .15s;}}
.hcard:hover{{border-color:var(--bdr2);}}
.hcard-score{{font-family:var(--disp);font-size:14px;font-weight:700;letter-spacing:1px;line-height:1;}}
.hcard-titles{{font-family:var(--mono);font-size:8px;color:var(--tl);margin-top:5px;line-height:1.45;}}
/* ROYALE */
#v-royale{{flex-direction:column;}}
.royale-hdr{{flex-shrink:0;padding:10px 18px 9px;border-bottom:1px solid var(--bdr);background:rgba(3,12,24,.7);}}
.royale-title{{font-family:var(--disp);font-size:10px;font-weight:700;letter-spacing:3px;color:var(--purp);}}
.royale-sub{{font-family:var(--mono);font-size:9px;color:var(--tl);margin-top:3px;}}
#royale-body{{flex:1;overflow:auto;padding:16px 18px;}}
#royale-body::-webkit-scrollbar{{width:4px;height:4px;}}
#royale-body::-webkit-scrollbar-thumb{{background:rgba(0,200,255,.15);border-radius:3px;}}
#royale-table{{border-collapse:collapse;}}
.rt-corner{{width:32px;height:32px;}}
.rt-ch{{font-family:var(--mono);font-size:9.5px;color:var(--tm);padding:0 6px;max-width:100px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;writing-mode:vertical-rl;transform:rotate(180deg);height:90px;vertical-align:bottom;padding-bottom:6px;}}
.rt-rh{{font-family:var(--mono);font-size:9.5px;color:var(--tm);padding:4px 10px;max-width:120px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;}}
.rt-cell{{width:44px;height:44px;text-align:center;cursor:pointer;border:1px solid rgba(255,255,255,.04);transition:transform .12s,box-shadow .12s;position:relative;vertical-align:middle;}}
.rt-cell:hover{{transform:scale(1.15);z-index:5;box-shadow:0 0 12px rgba(0,0,0,.6);}}
.rt-cell span{{font-family:var(--disp);font-size:10.5px;font-weight:700;letter-spacing:.5px;}}
.rt-diag{{background:rgba(255,255,255,.03);cursor:default;}}
.rt-diag:hover{{transform:none;box-shadow:none;}}
.empty-state{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;opacity:.4;}}
.es-icon{{font-size:36px;}}
.es-txt{{font-family:var(--mono);font-size:11px;color:var(--tl);letter-spacing:1px;text-align:center;line-height:1.6;}}
</style>
</head>
<body>
<div id="hdr">
  <span class="hdr-title">&#9889; CONTRADICTION DETECTOR</span>
  <div class="hdr-sep"></div>
  <span class="hdr-sub">ANALISIS REAL-TIME</span>
  <div id="mode-btns">
    <button class="mbn on" id="btn-duel"   onclick="setMode('duel')">&#9876; 1 VS 1</button>
    <button class="mbn"    id="btn-royale" onclick="setMode('royale')">&#127942; BATTLE ROYALE</button>
  </div>
  <div class="hdr-sep"></div>
  <span id="paper-count" style="font-family:var(--mono);font-size:9.5px;color:var(--tl)"></span>
</div>
<div id="root">
  <div class="view on" id="v-duel">
    <div class="ppnl" id="ppnl-a">
      <div class="ppnl-hdr" style="border-top:3px solid var(--green)">
        <div class="ppnl-lbl" style="color:var(--green)">&#9672; Paper A</div>
        <div class="ppnl-hint">Paper pertama untuk dibandingkan</div>
        <select class="psel" id="sel-a" onchange="onSelect()"></select>
      </div>
      <div class="pinfo" id="info-a">
        <div class="empty-state"><div class="es-icon">&#128196;</div><div class="es-txt">Pilih paper A</div></div>
      </div>
    </div>
    <div id="arena">
      <div class="arena-hdr">
        <div class="arena-title">&#9876; BATTLE ARENA</div>
        <button id="btn-swap" onclick="swapPapers()">&#8644; SWAP</button>
      </div>
      <div class="arena-body" id="arena-body">
        <div class="empty-state">
          <div class="es-icon">&#9889;</div>
          <div class="es-txt">Pilih Paper A dan Paper B<br>untuk memulai analisis kontradiksi</div>
        </div>
      </div>
      <div id="hist-panel">
        <div id="hist-toggle" onclick="toggleHistory()">
          <span style="font-size:12px">&#128203;</span>
          <span class="hist-tlbl">RIWAYAT BATTLE</span>
          <span id="hist-count">0</span>
          <span class="hist-arr">&#9650;</span>
        </div>
        <div id="hist-list"></div>
      </div>
    </div>
    <div class="ppnl" id="ppnl-b">
      <div class="ppnl-hdr" style="border-top:3px solid var(--red)">
        <div class="ppnl-lbl" style="color:var(--red)">&#9672; Paper B</div>
        <div class="ppnl-hint">Paper kedua untuk dibandingkan</div>
        <select class="psel" id="sel-b" onchange="onSelect()"></select>
      </div>
      <div class="pinfo" id="info-b">
        <div class="empty-state"><div class="es-icon">&#128196;</div><div class="es-txt">Pilih paper B</div></div>
      </div>
    </div>
  </div>
  <div class="view" id="v-royale">
    <div class="royale-hdr">
      <div class="royale-title">&#127942; BATTLE ROYALE MATRIX</div>
      <div class="royale-sub">Setiap sel = conflict score antar dua paper &#183; Klik sel untuk buka duel</div>
    </div>
    <div id="royale-body"><table id="royale-table"></table></div>
  </div>
</div>
<script>
const PAPERS = {papers_json};
const SW = new Set(["a","an","the","and","or","but","in","on","at","to","for","of","with","by","from","as","is","was","are","were","be","been","have","has","had","do","does","did","will","would","could","should","may","might","not","this","that","these","those","it","its","we","our","their","they","paper","study","research","propose","present","show","result","results","approach","method","methods","using","used","use","based","novel","new","existing","previous","however","also","which","such","than","more","most","work","model","system","data","two","three","one","can","well","significant","significantly","evaluate","experiment","dataset"]);
const POS=["improve","improves","improved","outperform","superior","better","effective","efficient","accurate","robust","strong","increase","enhance","advantage","promising","confirms","validates","supports","achieves","success","beneficial","positive","greater","faster","best"];
const NEG=["fail","fails","failed","failure","poor","worse","inferior","ineffective","inaccurate","weak","insignificant","decrease","limitation","drawback","challenge","problem","limited","lacks","unable","insufficient","smaller","slower","worst","negative","doubt"];
const CP=[["improve","fail"],["effective","ineffective"],["accurate","inaccurate"],["robust","weak"],["superior","inferior"],["increase","decrease"],["high","low"],["strong","weak"],["better","worse"],["success","failure"],["beneficial","harmful"],["positive","negative"],["greater","smaller"],["faster","slower"],["best","worst"],["validates","challenges"],["supports","contradicts"],["confirms","refutes"]];
function tok(t){{return((t||'').toLowerCase().match(/[a-z][a-z0-9\-]{{2,}}/g)||[]).filter(w=>!SW.has(w));}}
const _bc={{}};
function battle(ia,ib){{
  const k=ia<ib?ia+'_'+ib:ib+'_'+ia;
  if(_bc[k])return _bc[k];
  const p1=PAPERS[ia],p2=PAPERS[ib];
  const t1=((p1.title||'')+' '+(p1.abstract||'')).toLowerCase();
  const t2=((p2.title||'')+' '+(p2.abstract||'')).toLowerCase();
  const s1=new Set(tok(t1)),s2=new Set(tok(t2));
  const sh=[...s1].filter(w=>s2.has(w)&&!SW.has(w)).sort();
  const ps1=POS.filter(w=>t1.includes(w)),ng1=NEG.filter(w=>t1.includes(w));
  const ps2=POS.filter(w=>t2.includes(w)),ng2=NEG.filter(w=>t2.includes(w));
  const ct=[],cs=new Set();
  for(const[a,b]of CP){{
    const k2=a+'|'+b;
    if(cs.has(k2))continue;
    if(ps1.includes(a)&&ng2.includes(b)){{ct.push({{a,b}});cs.add(k2);}}
    else if(ng1.includes(b)&&ps2.includes(a)){{ct.push({{a:b,b:a}});cs.add(k2);}}
  }}
  const ss=Math.min(sh.length*3,30),cs2=Math.min(ct.length*18,54);
  const yr1=parseInt(p1.year)||0,yr2=parseInt(p2.year)||0;
  const ts=Math.min(Math.abs(yr1-yr2),16);
  const sc=Math.min(100,ss+cs2+ts);
  function exClaims(txt){{
    const ss2=(txt||'').split(/[.!?]\s+/).filter(s=>s.length>20);
    return ss2.map(s=>{{const sl=s.toLowerCase();const sc=[...POS,...NEG].filter(w=>sl.includes(w)).length;return{{s,sc}};}}).sort((a,b)=>b.sc-a.sc).slice(0,3).map(x=>x.s);
  }}
  const r={{score:sc,shared:sh.slice(0,10),ps1:ps1.slice(0,6),ng1:ng1.slice(0,6),ps2:ps2.slice(0,6),ng2:ng2.slice(0,6),ct:ct.slice(0,6),cl1:exClaims(p1.abstract),cl2:exClaims(p2.abstract),bd:{{sh:ss,sig:cs2,tm:ts}},vl:sc>=65?'high':sc>=35?'medium':'low',vt:sc>=65?'Paper ini menunjukkan KONTRADIKSI SIGNIFIKAN. Keduanya membahas topik yang sama ('+sh.length+' keyword bersama) namun menggunakan sinyal yang berlawanan \u2014 kemungkinan perbedaan metodologi, dataset, atau populasi studi.':sc>=35?'Terdapat POTENSI PERBEDAAN antara kedua paper. Keduanya berbagi '+sh.length+' keyword namun beberapa klaim mungkin bertentangan. Disarankan membaca kedua abstrak secara menyeluruh.':'Kedua paper relatif SEJALAN. Mereka berbagi '+sh.length+' keyword dan tidak menunjukkan sinyal yang secara eksplisit berlawanan. Kemungkinan besar saling melengkapi.'}};
  _bc[k]=r;return r;
}}
function esc(s){{return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function sclr(s){{return s>=65?'#ff4d6a':s>=35?'#ffb830':'#00ffaa';}}
function slbl(s){{return s>=65?'\u26a1 KONFLIK TINGGI':s>=35?'\u26a0\ufe0f BERPOTENSI BEDA':'\u2705 RELATIF SEJALAN';}}
const _hist=[];
function addHist(ia,ib,sc){{
  if(_hist.find(h=>(h.ia===ia&&h.ib===ib)||(h.ia===ib&&h.ib===ia)))return;
  _hist.unshift({{ia,ib,sc}});
  const hc=document.getElementById('hist-count');
  hc.textContent=_hist.length;
  const hl=document.getElementById('hist-list');
  hl.innerHTML=_hist.map(h=>{{
    const pa=PAPERS[h.ia],pb=PAPERS[h.ib];const clr=sclr(h.sc);
    return `<div class="hcard" onclick="loadHist(${{h.ia}},${{h.ib}})"><div class="hcard-score" style="color:${{clr}};text-shadow:0 0 10px ${{clr}}55">${{h.sc}}</div><div class="hcard-titles">${{esc(pa.short.substring(0,28))}}\u2026<br><span style="color:var(--tl)">vs</span> ${{esc(pb.short.substring(0,28))}}\u2026</div></div>`;
  }}).join('');
}}
function loadHist(ia,ib){{document.getElementById('sel-a').value=ia;document.getElementById('sel-b').value=ib;onSelect();}}
function toggleHistory(){{document.getElementById('hist-panel').classList.toggle('open');}}
function renderInfo(elId,paper,side,bt){{
  const el=document.getElementById(elId);
  const clr=side==='a'?'var(--green)':'var(--red)';
  const pos=side==='a'?(bt?.ps1||[]):(bt?.ps2||[]);
  const neg=side==='a'?(bt?.ng1||[]):(bt?.ng2||[]);
  const cls=side==='a'?(bt?.cl1||[]):(bt?.cl2||[]);
  const cite=Number(paper.citations).toLocaleString();
  el.innerHTML=`<div class="pi-title">${{esc(paper.title)}}</div><div class="pi-chips"><span class="chip yr">\ud83d\udcc5 ${{paper.year||'?'}}</span><span class="chip ct">\u2191 ${{cite}} sitasi</span><span class="chip">${{esc(paper.source)}}</span></div><div class="pi-sec">Penulis</div><div style="font-family:var(--mono);font-size:10px;color:var(--tm);margin-bottom:8px;line-height:1.4">${{esc(paper.authors)}}</div><div class="pi-sec">Abstrak</div><div class="pi-abs" style="margin-bottom:10px">${{esc(paper.abstract)}}</div>${{pos.length||neg.length?`<div class="pi-sec">Sinyal</div><div class="sig-wrap" style="margin-bottom:9px">${{pos.map(w=>`<span class="sig sig-p">+ ${{w}}</span>`).join('')}}${{neg.map(w=>`<span class="sig sig-n">\u2212 ${{w}}</span>`).join('')}}</div>`:''}}<div class="pi-sec">Klaim Utama</div>${{cls.map(c=>`<div class="claim-item"><div class="claim-dot" style="background:${{clr}}"></div><div class="claim-txt">${{esc(c)}}</div></div>`).join('')}}<a href="${{esc(paper.link)}}" target="_blank" class="pi-link" style="color:${{clr}}">\u2197 BUKA PAPER LENGKAP</a>`;
}}
function renderArena(ia,ib){{
  const bt=battle(ia,ib);const sc=bt.score;const clr=sclr(sc);const lbl=slbl(sc);
  const vbg=bt.vl==='high'?'rgba(255,77,106,.07)':bt.vl==='medium'?'rgba(255,184,48,.07)':'rgba(0,255,170,.07)';
  const vbd=bt.vl==='high'?'rgba(255,77,106,.3)':bt.vl==='medium'?'rgba(255,184,48,.3)':'rgba(0,255,170,.3)';
  const sh=bt.shared.length?bt.shared.map(k=>`<span class="kw-stag">${{esc(k)}}</span>`).join(''):`<span style="font-family:var(--mono);font-size:10px;color:var(--tl)">Tidak ada keyword bersama</span>`;
  const ct=bt.ct.length?bt.ct.map(c=>`<div class="kw-crow"><div class="kw-a">${{esc(c.a)}}</div><div class="kw-vs">\u2194</div><div class="kw-b">${{esc(c.b)}}</div></div>`).join(''):`<div style="text-align:center;font-family:var(--mono);font-size:10px;color:var(--tl);padding:10px">Tidak ada sinyal eksplisit yang berlawanan</div>`;
  document.getElementById('arena-body').innerHTML=`
    <div style="width:100%;display:flex;flex-direction:column;align-items:center;gap:7px">
      <div class="meter-lbl">Contradiction Meter</div>
      <div class="meter-score" style="color:${{clr}}">${{sc}}</div>
      <div class="meter-sub">/ 100</div>
      <div class="meter-track"><div class="meter-fill" style="width:${{sc}}%;background:linear-gradient(90deg,${{clr}},${{sc>=65?'#ff1744':sc>=35?'#ff8f00':'#00c87a'}});box-shadow:0 0 16px ${{clr}}44"></div></div>
      <div style="width:100%;display:flex;justify-content:space-between"><span class="mtick">0 SEJALAN</span><span class="mtick">50</span><span class="mtick">BERTENTANGAN 100</span></div>
    </div>
    <div style="width:100%">
      <div class="conf-title">\u2b21 Breakdown Skor</div>
      <div class="conf-row"><div class="conf-key">Keyword bersama</div><div class="conf-bg"><div class="conf-fill" style="width:${{Math.round(bt.bd.sh/30*100)}}%;background:#b39dfa;box-shadow:0 0 6px #b39dfa44"></div></div><div class="conf-val" style="color:#b39dfa">+${{bt.bd.sh}}</div></div>
      <div class="conf-row"><div class="conf-key">Sinyal berlawanan</div><div class="conf-bg"><div class="conf-fill" style="width:${{Math.round(bt.bd.sig/54*100)}}%;background:#ff4d6a;box-shadow:0 0 6px #ff4d6a44"></div></div><div class="conf-val" style="color:#ff4d6a">+${{bt.bd.sig}}</div></div>
      <div class="conf-row"><div class="conf-key">Gap waktu</div><div class="conf-bg"><div class="conf-fill" style="width:${{Math.round(bt.bd.tm/16*100)}}%;background:#ffb830;box-shadow:0 0 6px #ffb83044"></div></div><div class="conf-val" style="color:#ffb830">+${{bt.bd.tm}}</div></div>
    </div>
    <div class="verdict-wrap" style="border-color:${{vbd}};background:${{vbg}}"><div class="verdict-level" style="color:${{clr}}">${{lbl}}</div><div class="verdict-text">${{esc(bt.vt)}}</div></div>
    <div style="width:100%">
      <div class="kw-title">\ud83d\udd11 Keyword Bersama (${{bt.shared.length}})</div>
      <div class="kw-shared">${{sh}}</div>
      ${{bt.ct.length?`<div class="kw-title" style="margin-top:8px">\u2694 Sinyal Berlawanan (${{bt.ct.length}})</div><div style="display:flex;margin-bottom:5px"><div style="flex:1;text-align:right;font-family:var(--mono);font-size:8.5px;color:var(--green);letter-spacing:1px;padding-right:9px">PAPER A</div><div style="width:30px"></div><div style="flex:1;font-family:var(--mono);font-size:8.5px;color:var(--red);letter-spacing:1px;padding-left:9px">PAPER B</div></div>${{ct}}`:`<div>${{ct}}</div>`}}
    </div>
    <button class="btn-export" onclick="exportRep(${{ia}},${{ib}})">\u2b07 EXPORT LAPORAN LITERATURE REVIEW</button>
  `;
  addHist(ia,ib,sc);
}}
function exportRep(ia,ib){{
  const bt=battle(ia,ib),pa=PAPERS[ia],pb=PAPERS[ib];
  const sl=bt.score>=65?'KONTRADIKTIF':bt.score>=35?'BERPOTENSI BERBEDA':'SEJALAN';
  const sh=bt.shared.join(', ')||'\u2014';
  const ct=bt.ct.map(c=>'"'+c.a+'" vs "'+c.b+'"').join('; ')||'\u2014';
  const SEP='------------------------------------------------------------';
  const rep='LAPORAN PERBANDINGAN LITERATUR\n'+SEP+'\nPaper A: '+pa.title+'\n  Tahun: '+pa.year+' | Sitasi: '+pa.citations+'\n  Penulis: '+pa.authors+'\n\nPaper B: '+pb.title+'\n  Tahun: '+pb.year+' | Sitasi: '+pb.citations+'\n  Penulis: '+pb.authors+'\n\n'+SEP+'\nHASIL: '+sl+' (Score: '+bt.score+'/100)\nKeyword Bersama: '+sh+'\nSinyal Berlawanan: '+ct+'\nBreakdown: Keyword +'+bt.bd.sh+' | Sinyal +'+bt.bd.sig+' | Waktu +'+bt.bd.tm+'\n\n'+SEP+'\nKALIMAT LITERATURE REVIEW:\n\n\"'+pa.title+' ('+pa.year+') '+(bt.score>=65?'bertentangan secara signifikan dengan':bt.score>=35?'menunjukkan perbedaan pandangan dengan':'sejalan dengan')+' '+pb.title+' ('+pb.year+'). Kedua paper membahas topik yang berkaitan ('+sh+')'+(bt.ct.length?', namun terdapat perbedaan sinyal pada aspek: '+ct+'.':'.')+'\"';
  const blob=new Blob([rep],{{type:'text/plain;charset=utf-8'}});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=`battle_${{pa.year}}_vs_${{pb.year}}.txt`;a.click();URL.revokeObjectURL(url);
}}
function onSelect(){{
  const ia=parseInt(document.getElementById('sel-a').value);
  const ib=parseInt(document.getElementById('sel-b').value);
  const bt=(ia>=0&&ib>=0&&ia!==ib)?battle(ia,ib):null;
  if(ia>=0&&PAPERS[ia])renderInfo('info-a',PAPERS[ia],'a',bt);
  if(ib>=0&&PAPERS[ib])renderInfo('info-b',PAPERS[ib],'b',bt);
  if(ia>=0&&ib>=0&&ia!==ib)renderArena(ia,ib);
  else if(ia===ib&&ia>=0)document.getElementById('arena-body').innerHTML=`<div class="empty-state"><div class="es-icon">\u26a0\ufe0f</div><div class="es-txt">Paper A dan B tidak boleh sama</div></div>`;
}}
function swapPapers(){{const sa=document.getElementById('sel-a'),sb=document.getElementById('sel-b');[sa.value,sb.value]=[sb.value,sa.value];onSelect();}}
function renderRoyale(){{
  const N=PAPERS.length;
  let html='<thead><tr><th class="rt-corner"></th>';
  PAPERS.forEach(p=>{{html+=`<th class="rt-ch" title="${{esc(p.title)}}">${{esc(p.short.substring(0,18))}}</th>`;}}); 
  html+='</tr></thead><tbody>';
  PAPERS.forEach((pa,ia)=>{{
    html+=`<tr><td class="rt-rh" title="${{esc(pa.title)}}">${{esc(pa.short.substring(0,22))}}</td>`;
    PAPERS.forEach((pb,ib)=>{{
      if(ia===ib){{html+=`<td class="rt-cell rt-diag"></td>`;}}
      else{{const bt=battle(ia,ib);const clr=sclr(bt.score);const bg=bt.score>=65?`rgba(255,77,106,${{.06+bt.score/600}})`:bt.score>=35?`rgba(255,184,48,${{.05+bt.score/700}})`:`rgba(0,255,170,${{.03+bt.score/900}})`;html+=`<td class="rt-cell" style="background:${{bg}}" title="${{esc(pa.short)}} vs ${{esc(pb.short)}}: ${{bt.score}}" onclick="openRoyale(${{ia}},${{ib}})"><span style="color:${{clr}}">${{bt.score}}</span></td>`;}}
    }});
    html+='</tr>';
  }});
  html+='</tbody>';
  document.getElementById('royale-table').innerHTML=html;
}}
function openRoyale(ia,ib){{setMode('duel');document.getElementById('sel-a').value=ia;document.getElementById('sel-b').value=ib;onSelect();}}
function setMode(m){{
  document.getElementById('v-duel').classList.toggle('on',m==='duel');
  document.getElementById('v-royale').classList.toggle('on',m==='royale');
  document.getElementById('btn-duel').classList.toggle('on',m==='duel');
  document.getElementById('btn-royale').classList.toggle('on',m==='royale');
  if(m==='royale')renderRoyale();
}}
function init(){{
  const sa=document.getElementById('sel-a'),sb=document.getElementById('sel-b');
  const ph='<option value="-1">\u2014 Pilih paper \u2014</option>';
  const opts=PAPERS.map(p=>`<option value="${{p.id}}">${{esc(p.year)}} \xb7 ${{esc(p.short)}}</option>`).join('');
  sa.innerHTML=ph+opts;sb.innerHTML=ph+opts;
  document.getElementById('paper-count').textContent=PAPERS.length+' PAPER';
  if(PAPERS.length>=2){{sa.value='0';sb.value='1';onSelect();}}
}}
init();
</script>
</body>
</html>"""
