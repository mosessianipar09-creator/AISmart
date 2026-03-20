"""
graph_gap.py  (v2 — refactored & extended)
==========================================
Research Gap Detector — Fitur 3 dari Research Intelligence Center

CHANGELOG v2
------------
BUG FIXES
  #1  sortHeat() — ID mismatch 'pc-coverage-sort' / 'pc-alpha-sort' (TypeError fatal)
  #2  renderHeatmap() dipanggil saat clientWidth=0 (heatmap lebar salah)
  #3  closeVennPopup() — klik dalam popup langsung menutup popup
  #4  gap_stats() membangun data dua kali (double TF-IDF, tambah cache)
  #5  renderHidden() — variable shadowing  hf.map(hf => ...)
  #6  Tab lazy-render tidak di-cache → re-render setiap switch

INOVASI
  #1  Tab Timeline — Year × Topic Coverage Matrix (tab ke-5)
  #2  Research Opportunity Score (ROS) + trend direction per keyword
  #3  Smart Search Query Generator (3 varian per hidden finding)
  #4  Multi-variant Gap Statement (Formal / Ringkas / Eksploratif)
  #5  Coverage Velocity — trend arrow (↑↓→★) di heatmap & gap rows

Fungsi publik (sama seperti v1, backward-compatible):
  render_gap(papers, height)  → str   HTML siap embed
  gap_stats(papers)           → dict  statistik untuk metric cards
  build_gap_data(papers)      → dict  data mentah (berguna untuk testing)
"""

from __future__ import annotations

import re
import math
import json
import collections


# ─────────────────────────────────────────────────────────────────
# 0. STOPWORDS
# ─────────────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","as","is","was","are","were","be","been","being","have",
    "has","had","do","does","did","will","would","could","should","may",
    "might","must","shall","can","not","no","nor","so","yet","both",
    "either","neither","each","few","more","most","other","some","such",
    "than","then","too","very","just","also","only","even","much","many",
    "own","same","s","t","don","now","i","we","you","he","she","they","it",
    "this","that","these","those","what","which","who","when","where","why","how",
    "paper","study","research","propose","proposed","present","presented",
    "show","shows","shown","demonstrate","demonstrates","demonstrated",
    "result","results","approach","method","methods","technique","techniques",
    "using","used","use","based","novel","new","existing","previous",
    "however","although","while","thus","therefore","hence","furthermore",
    "moreover","additionally","finally","first","second","third",
    "well","often","different","various","large","small","high","low",
    "number","set","value","values","type","types","two","three","one",
    "multiple","several","recent","current","state","art","task","tasks",
    "significant","significantly","improve","improves","improved","performance",
    "achieve","achieves","achieved","outperform","evaluate","evaluated",
    "experiment","experiments","experimental","dataset","datasets","benchmark",
    "yang","dengan","untuk","dari","dalam","pada","ini","itu","atau",
    "dan","di","ke","oleh","adalah","sebagai","dapat","akan","telah",
    "tidak","lebih","juga","serta","kami","kita","ada","bahwa","karena",
    "sebuah","suatu","sangat","sudah","sedang","hanya","namun","maka",
    "al","et","vs","ie","eg","cf","fig","eq","tab","sec","ref","refs",
    "work","works","system","systems","model","problem","problems","data",
    "information","process","following","given","general","specific","related",
    "framework","overall","main","key","important","useful",
})

_DOMAIN_BOOST = {
    "transformer":3.0,"attention":2.5,"bert":2.5,"gpt":2.5,"llm":3.0,
    "neural":2.0,"deep":1.8,"learning":1.5,"embedding":2.5,"pretrain":2.5,
    "finetune":2.5,"finetuning":2.5,"pretrained":2.5,"language":1.8,
    "generative":2.5,"diffusion":3.0,"reinforcement":2.5,"federated":3.0,
    "contrastive":2.8,"self-supervised":3.0,"zero-shot":3.0,"few-shot":3.0,
    "multimodal":3.0,"vision":2.0,"graph":2.0,"knowledge":1.8,
    "genomics":3.0,"proteomics":3.0,"crispr":3.0,"clinical":2.5,
    "biomarker":3.0,"immunotherapy":3.0,"cancer":2.0,"diagnosis":2.5,
    "efficiency":2.0,"scalability":2.5,"robustness":2.0,"interpretability":3.0,
    "explainability":3.0,"fairness":2.5,"alignment":3.0,"safety":2.5,
    "reasoning":2.5,"inference":2.0,"generation":2.0,"detection":2.0,
    "classification":2.0,"segmentation":2.5,"retrieval":2.5,"summarization":2.5,
}

_GAP_THRESHOLD_CRITICAL = 62
_GAP_THRESHOLD_EXPLORE  = 38
_TOP_KEYWORDS           = 24
_CURRENT_YEAR           = 2025


# ─────────────────────────────────────────────────────────────────
# 1. CACHE (BUG FIX #4 — mencegah double-compute antara render_gap + gap_stats)
# ─────────────────────────────────────────────────────────────────

_cache_key: tuple | None = None
_cache_val: dict | None  = None


def _make_cache_key(papers: list[dict]) -> tuple:
    return tuple(sorted(p.get("title", "") for p in papers))


# ─────────────────────────────────────────────────────────────────
# 2. HELPERS
# ─────────────────────────────────────────────────────────────────

def _parse_year(val) -> int:
    try:
        y = int(str(val).strip())
        return y if 1900 < y <= 2030 else 2020
    except (ValueError, TypeError):
        return 2020


def _normalize_paper(p: dict, idx: int) -> dict:
    link  = p.get("link",     "") or ""
    title = (p.get("title",   "") or "Untitled").strip()
    abstr = (p.get("abstract","") or "").strip()
    year  = _parse_year(p.get("year", ""))
    cites = max(0, int(p.get("citations", 0) or 0))

    if "semanticscholar.org/paper/" in link:
        pid = link.split("/paper/")[-1].strip("/")
    else:
        pid = f"p{idx}_{re.sub(r'[^a-z0-9]', '_', title[:18].lower())}"

    short = (title[:52] + "…") if len(title) > 52 else title
    return {
        "id": pid, "title": title, "title_short": short,
        "authors":   (p.get("authors", "") or "N/A").strip(),
        "year":      year,
        "citations": cites,
        "venue":     (p.get("venue",   "") or "Unknown").strip() or "Unknown",
        "abstract":  abstr,
        "link":      link,
        "source":    p.get("source", "unknown"),
    }


# ─────────────────────────────────────────────────────────────────
# 3. KEYWORD EXTRACTION
# ─────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    text   = text.lower()
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", text)
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 3]


def _extract_bigrams(tokens: list[str]) -> list[str]:
    return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens)-1)]


def _extract_keywords_for_paper(paper: dict) -> dict[str, float]:
    title_tok = _tokenize(paper["title"])
    abstr_tok = _tokenize(paper["abstract"])
    title_bi  = _extract_bigrams(title_tok)

    freq: dict[str, float] = collections.defaultdict(float)
    for t in title_tok:
        freq[t] += 3.0 * _DOMAIN_BOOST.get(t, 1.0)
    for t in abstr_tok:
        freq[t] += 1.0 * _DOMAIN_BOOST.get(t, 1.0)
    for b in title_bi:
        freq[b] += 2.0

    total = sum(freq.values()) or 1.0
    return {k: v / total for k, v in freq.items()}


# ─────────────────────────────────────────────────────────────────
# 4. TOPIC MATRIX
# ─────────────────────────────────────────────────────────────────

def _build_topic_matrix(papers: list[dict]) -> dict:
    N = len(papers)
    if N == 0:
        return {"keywords":[],"paper_shorts":[],"scores":[],"row_coverage":[],"col_breadth":[]}

    tf_dicts = [_extract_keywords_for_paper(p) for p in papers]

    df: dict[str, int] = collections.defaultdict(int)
    for tf in tf_dicts:
        for kw in tf:
            df[kw] += 1

    tfidf: dict[str, list[float]] = {}
    for kw, doc_count in df.items():
        if doc_count < 1:
            continue
        idf = math.log(N / doc_count + 1)
        tfidf[kw] = [tf.get(kw, 0.0) * idf for tf in tf_dicts]

    ranked = sorted(tfidf.items(), key=lambda x: max(x[1]), reverse=True)

    unigram_count = sum(1 for kw, _ in ranked if "_" not in kw)
    top_keywords  = []
    for kw, _ in ranked:
        if len(top_keywords) >= _TOP_KEYWORDS:
            break
        if "_" in kw and unigram_count >= _TOP_KEYWORDS * 0.75:
            continue
        top_keywords.append(kw)

    if not top_keywords:
        return {"keywords":[],"paper_shorts":[],"scores":[],"row_coverage":[],"col_breadth":[]}

    score_matrix = []
    row_coverage = []
    for kw in top_keywords:
        raw = tfidf[kw]
        mx  = max(raw) or 1.0
        norm = [round(v / mx, 4) for v in raw]
        score_matrix.append(norm)
        row_coverage.append(round(sum(1 for v in raw if v > 0) / N, 4))

    col_breadth = []
    for pi in range(N):
        vals = [score_matrix[ki][pi] for ki in range(len(top_keywords))]
        col_breadth.append(round(sum(vals) / len(vals), 4) if vals else 0.0)

    kw_display = [kw.replace("_", " ") for kw in top_keywords]

    return {
        "keywords":     kw_display,
        "paper_shorts": [p["title_short"] for p in papers],
        "scores":       score_matrix,
        "row_coverage": row_coverage,
        "col_breadth":  col_breadth,
    }


# ─────────────────────────────────────────────────────────────────
# 5. GAP SCORING
# ─────────────────────────────────────────────────────────────────

def _compute_gap_scores(papers: list[dict], topic_matrix: dict) -> list[dict]:
    keywords     = topic_matrix.get("keywords", [])
    row_coverage = topic_matrix.get("row_coverage", [])
    scores       = topic_matrix.get("scores", [])

    if not keywords or not papers:
        return []

    N         = len(papers)
    max_cites = max((p["citations"] for p in papers), default=1)
    if max_cites <= 0:
        max_cites = 1

    years     = sorted(p["year"] for p in papers)
    yr_cutoff = years[max(0, int(N * 0.70))]

    results = []
    for ki, kw in enumerate(keywords):
        if ki >= len(row_coverage) or ki >= len(scores):
            continue

        coverage  = row_coverage[ki]
        kw_scores = scores[ki]

        mentioning_idx = [pi for pi, v in enumerate(kw_scores) if v > 0]
        if not mentioning_idx:
            continue

        avg_cite = sum(papers[pi]["citations"] for pi in mentioning_idx) / len(mentioning_idx)
        cite_imp = math.log(avg_cite + 1) / math.log(max_cites + 1)

        recent_count = sum(1 for pi in mentioning_idx if papers[pi]["year"] >= yr_cutoff)
        recency = recent_count / len(mentioning_idx) if mentioning_idx else 0.0

        raw_gap   = (0.45 * (1 - coverage) + 0.35 * cite_imp + 0.20 * recency)
        gap_score = round(min(100, max(0, raw_gap * 100)))

        if gap_score >= _GAP_THRESHOLD_CRITICAL and cite_imp >= 0.45:
            rec = "critical"
        elif gap_score >= _GAP_THRESHOLD_EXPLORE:
            rec = "explore"
        else:
            rec = "skip"

        covering_titles = [papers[pi]["title_short"] for pi in mentioning_idx]

        results.append({
            "keyword":         kw,
            "coverage":        round(coverage, 3),
            "coverage_pct":    round(coverage * 100),
            "citation_imp":    round(cite_imp, 3),
            "recency":         round(recency, 3),
            "gap_score":       gap_score,
            "recommendation":  rec,
            "covering_papers": covering_titles,
            "covering_count":  len(mentioning_idx),
            # Fields below filled in by _compute_ros_and_velocity()
            "ros":               0,
            "citation_velocity": 0.0,
            "venue_diversity":   0,
            "trend":             "stable",
        })

    return sorted(results, key=lambda x: x["gap_score"], reverse=True)


# ─────────────────────────────────────────────────────────────────
# 6. INOVASI #2 — Research Opportunity Score (ROS) + Trend Velocity
# ─────────────────────────────────────────────────────────────────

def _compute_ros_and_velocity(
    papers:       list[dict],
    gap_scores:   list[dict],
    topic_matrix: dict,
) -> list[dict]:
    """
    Augment each gap_score entry with:
      ros              = Research Opportunity Score (0–100)
                         = 0.40*(1-coverage) + 0.35*velocity_norm + 0.25*venue_norm
      citation_velocity= avg citations per year of paper age (recency-weighted impact)
      venue_diversity  = unique venues in covering papers
      trend            = 'rising' | 'declining' | 'stable' | 'new'
                         berdasarkan distribusi coverage di paruh awal vs akhir waktu
    """
    if not papers or not gap_scores:
        return gap_scores

    title_map = {p["title_short"]: p for p in papers}

    # Max velocity across entire corpus (for normalization)
    max_vel = max(
        p["citations"] / max(1, _CURRENT_YEAR - p["year"])
        for p in papers
    ) or 1.0

    # Mid-year for trend computation (INOVASI #5)
    all_years = sorted(p["year"] for p in papers)
    mid_year  = all_years[len(all_years) // 2] if all_years else _CURRENT_YEAR

    keywords  = topic_matrix.get("keywords", [])
    tm_scores = topic_matrix.get("scores",   [])

    for g in gap_scores:
        covering = [title_map[t] for t in g.get("covering_papers", []) if t in title_map]

        # ── Citation velocity ──
        if covering:
            velocities = [
                p["citations"] / max(1, _CURRENT_YEAR - p["year"])
                for p in covering
            ]
            avg_vel  = sum(velocities) / len(velocities)
            vel_norm = math.log(avg_vel + 1) / math.log(max_vel + 1)
        else:
            avg_vel  = 0.0
            vel_norm = 0.0

        # ── Venue diversity ──
        venues     = {p["venue"] for p in covering if p["venue"] != "Unknown"}
        venue_norm = min(1.0, len(venues) / max(1, len(covering) or 1))

        # ── ROS composite ──
        ros_raw = (
            0.40 * (1 - g["coverage"]) +
            0.35 * vel_norm            +
            0.25 * venue_norm
        )

        # ── Trend direction (INOVASI #5) ──
        kw = g["keyword"]
        try:
            ki  = keywords.index(kw)
            row = tm_scores[ki] if ki < len(tm_scores) else []
        except ValueError:
            ki, row = -1, []

        if row:
            recent_vals = [row[pi] for pi, p in enumerate(papers)
                           if p["year"] >= mid_year and pi < len(row)]
            older_vals  = [row[pi] for pi, p in enumerate(papers)
                           if p["year"] <  mid_year and pi < len(row)]
            avg_recent = sum(recent_vals) / len(recent_vals) if recent_vals else 0.0
            avg_older  = sum(older_vals)  / len(older_vals)  if older_vals  else 0.0

            if not older_vals or avg_older < 1e-6:
                trend = "new"
            elif avg_recent > avg_older * 1.30:
                trend = "rising"
            elif avg_recent < avg_older * 0.70:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"

        g["ros"]               = round(min(100, ros_raw * 100))
        g["citation_velocity"] = round(avg_vel, 2)
        g["venue_diversity"]   = len(venues)
        g["trend"]             = trend

    return gap_scores


# ─────────────────────────────────────────────────────────────────
# 7. INOVASI #1 — Timeline Data (Year × Topic)
# ─────────────────────────────────────────────────────────────────

def _build_timeline_data(papers: list[dict], topic_matrix: dict) -> dict:
    """
    Bangun matrix Year × Keyword untuk Tab Timeline.

    Sumbu X = tahun unik (sorted ascending)
    Sumbu Y = keyword dari topic_matrix
    Sel     = rata-rata TF-IDF score paper dari tahun tersebut, dinormalisasi 0..1

    Digunakan oleh JS renderTimeline() untuk menampilkan kapan tiap topik
    ramai (terang) atau sepi (gelap) — identifikasi "emerging" vs "declining".
    """
    keywords = topic_matrix.get("keywords", [])
    scores   = topic_matrix.get("scores",   [])

    if not papers or not keywords:
        return {"years": [], "keywords": [], "scores": [], "paper_counts": {}}

    years_set = sorted(set(p["year"] for p in papers))

    timeline_scores: list[list[float]] = []
    for ki, _ in enumerate(keywords):
        if ki >= len(scores):
            continue
        row_scores = []
        for yr in years_set:
            paper_idxs = [pi for pi, p in enumerate(papers) if p["year"] == yr]
            if paper_idxs:
                vals = [scores[ki][pi] for pi in paper_idxs if pi < len(scores[ki])]
                row_scores.append(round(sum(vals) / len(vals), 4) if vals else 0.0)
            else:
                row_scores.append(0.0)
        timeline_scores.append(row_scores)

    # Normalize per-keyword to 0..1
    norm_scores = []
    for row in timeline_scores:
        mx = max(row) or 1.0
        norm_scores.append([round(v / mx, 4) for v in row])

    paper_counts = {yr: sum(1 for p in papers if p["year"] == yr) for yr in years_set}

    return {
        "years":        years_set,
        "keywords":     keywords,
        "scores":       norm_scores,
        "paper_counts": paper_counts,
    }


# ─────────────────────────────────────────────────────────────────
# 8. VENN DATA
# ─────────────────────────────────────────────────────────────────

def _build_venn_data(gap_scores: list[dict], papers: list[dict]) -> dict:
    covered  = [g for g in gap_scores if g["gap_score"] <  35]
    overlap  = [g for g in gap_scores if 35 <= g["gap_score"] < 62]
    gap_only = [g for g in gap_scores if g["gap_score"] >= 62]

    def top_kws(group, n=8):
        return [g["keyword"] for g in group[:n]]

    total = max(len(gap_scores), 1)
    return {
        "covered": {
            "label":    "Topik Terlindungi",
            "count":    len(covered),
            "pct":      round(len(covered)  / total * 100),
            "keywords": top_kws(covered),
            "color":    "#2dd4bf",
        },
        "overlap": {
            "label":    "Terlindungi Sebagian",
            "count":    len(overlap),
            "pct":      round(len(overlap)  / total * 100),
            "keywords": top_kws(overlap),
            "color":    "#a78bfa",
        },
        "gap": {
            "label":    "Celah Kritis",
            "count":    len(gap_only),
            "pct":      round(len(gap_only) / total * 100),
            "keywords": top_kws(gap_only),
            "color":    "#f59e0b",
        },
        "total_keywords": total,
        "summary": {
            "well_covered_pct": round(len(covered)  / total * 100),
            "gap_pct":          round(len(gap_only) / total * 100),
        },
    }


# ─────────────────────────────────────────────────────────────────
# 9. RADAR DATA
# ─────────────────────────────────────────────────────────────────

def _build_radar_data(papers: list[dict], gap_scores: list[dict]) -> dict:
    N = len(papers)
    if N == 0:
        zeros = [50, 50, 50, 50, 50]
        return {"dimensions":["Temporal","Topical","Methodological","Citation","Venue"],
                "coverage": zeros, "gap": [100-v for v in zeros]}

    years   = [p["year"] for p in papers]
    yr_mean = sum(years) / N
    yr_std  = math.sqrt(sum((y - yr_mean)**2 for y in years) / N) if N > 1 else 0
    temporal = min(100, max(20, yr_std * 8 + 20))

    topical = round(sum(g["coverage"] for g in gap_scores) / len(gap_scores) * 100) if gap_scores else 40

    all_title_tokens = set()
    for p in papers:
        all_title_tokens.update(_tokenize(p["title"]))
    # FIX: más realista scaling (no longer caps at 34 tokens)
    method_score = min(100, max(0, int(len(all_title_tokens) / max(N, 1) * 25)))

    total_cites  = sum(p["citations"] for p in papers)
    max_one      = max((p["citations"] for p in papers), default=1)
    max_possible = N * max(max_one, 1)
    log_denom    = math.log(max_possible + 1)
    citation_score = round(math.log(total_cites + 1) / log_denom * 100) if log_denom > 0 else 0

    unique_venues = len(set(p["venue"] for p in papers if p["venue"] != "Unknown"))
    venue_score   = min(100, round(unique_venues / N * 120))

    dims = ["Temporal", "Topical", "Methodological", "Citation", "Venue"]
    cov  = [round(temporal), round(topical), round(method_score),
            round(citation_score), round(venue_score)]
    gap  = [max(0, 100 - c) for c in cov]

    return {"dimensions": dims, "coverage": cov, "gap": gap}


# ─────────────────────────────────────────────────────────────────
# 10. HIDDEN FINDINGS + INOVASI #3 (Smart Search Queries)
# ─────────────────────────────────────────────────────────────────

def _find_hidden_findings(papers: list[dict], gap_scores: list[dict]) -> list[dict]:
    if not papers or not gap_scores:
        return []

    implicit_re = re.compile(
        r"(?:unlike|compared to|building on|following|inspired by|"
        r"as in|similar to|extending|based on|motivated by|"
        r"in contrast to|previously)\s+([a-z][a-z\s]{3,30})",
        re.IGNORECASE
    )

    implicit_counts: dict[str, int] = collections.defaultdict(int)
    for p in papers:
        for m in implicit_re.finditer(p.get("abstract", "")):
            phrase  = m.group(1).lower().strip()
            tokens  = [t for t in phrase.split() if t not in _STOPWORDS and len(t) >= 3]
            for t in tokens:
                implicit_counts[t] += 1

    yr_max = max((p["year"] for p in papers), default=_CURRENT_YEAR)

    results = []
    for g in gap_scores:
        if g["gap_score"] < _GAP_THRESHOLD_EXPLORE:
            continue
        kw   = g["keyword"]
        kw_t = kw.replace(" ", "_").split("_")

        implicit_score = sum(implicit_counts.get(t, 0) for t in kw_t)

        temporal_markers = {"recent","emerging","new","latest","modern","contemporary",
                             "current","2020","2021","2022","2023","2024","2025",
                             "generation","evolution"}
        method_markers   = {"architecture","framework","algorithm","approach",
                             "mechanism","technique","strategy","pipeline",
                             "training","inference","optimization","loss",
                             "layer","encoder","decoder","head"}
        is_temporal = any(t in temporal_markers for t in kw_t)
        is_method   = any(t in method_markers   for t in kw_t)
        gap_type    = "temporal" if is_temporal else "methodological" if is_method else "topical"

        covering_titles = g.get("covering_papers", [])
        if covering_titles:
            title_to_venue = {p["title_short"]: p["venue"] for p in papers}
            relevant_venue = title_to_venue.get(covering_titles[0],
                                                papers[0]["venue"] if papers else "")
        elif papers:
            relevant_venue = papers[0]["venue"]
        else:
            relevant_venue = ""

        # INOVASI #3 — 3 varian query siap salin
        search_queries = [
            {
                "label": "Exact",
                "query": f'"{kw}"',
                "tip":   "Phrase exact di Google Scholar",
            },
            {
                "label": "Survey",
                "query": f'"{kw}" survey OR review OR meta-analysis',
                "tip":   "Paper review / systematic review",
            },
            {
                "label": "Terkini",
                "query": f'{kw} {yr_max - 3}..{yr_max}',
                "tip":   f"Paper terbaru ({yr_max-3}–{yr_max})",
            },
        ]

        results.append({
            "concept":            kw,
            "gap_score":          g["gap_score"],
            "ros":                g.get("ros", 0),
            "covering_count":     g["covering_count"],
            "recommendation":     g["recommendation"],
            "gap_type":           gap_type,
            "trend":              g.get("trend", "stable"),
            "implicit_score":     implicit_score,
            "search_queries":     search_queries,
            "recommended_search": (kw + " " + relevant_venue).strip(),
            "covering_papers":    g["covering_papers"][:3],
        })

    results.sort(key=lambda x: (x["recommendation"] != "critical", -x["gap_score"]))
    return results[:12]


# ─────────────────────────────────────────────────────────────────
# 11. INOVASI #4 — Multi-variant Gap Statement
# ─────────────────────────────────────────────────────────────────

def _generate_gap_statement_variants(
    topic:   str,
    gap_kws: list[str],
    cov_kws: list[str],
    papers:  list[dict],
    gaps:    list[dict],
) -> dict[str, str]:
    """
    Tiga gaya statement siap pakai untuk berbagai konteks penulisan:
      formal      — English, jurnal internasional
      concise     — Indonesia, proposal singkat / abstrak
      exploratory — Indonesia, berbasis hipotesis
    """
    N       = len(papers)
    yr_min  = min(p["year"] for p in papers) if papers else 2018
    yr_max  = max(p["year"] for p in papers) if papers else 2024
    n_crit  = len([g for g in gaps if g["recommendation"] == "critical"])

    gap_list_en = ", ".join(f'"{k}"' for k in gap_kws) or '"related areas"'
    cov_list_en = ", ".join(f'"{k}"' for k in cov_kws) or '"core concepts"'
    gap_list_id = ", ".join(f'"{k}"' for k in gap_kws) or '"topik terkait"'
    cov_list_id = ", ".join(f'"{k}"' for k in cov_kws) or '"area utama"'
    top_gap     = gap_kws[0] if gap_kws else "area yang teridentifikasi"

    formal = (
        f"A systematic review of {N} peer-reviewed publications spanning "
        f"{yr_min}–{yr_max} reveals that while the literature has developed "
        f"substantial coverage of {cov_list_en}, critical knowledge gaps persist "
        f"in {gap_list_en}. These {n_crit} underexplored areas — identified via "
        f"TF-IDF analysis weighted by citation impact and recency — represent "
        f"high-opportunity research directions in {topic}. The proposed study "
        f"directly addresses this gap by contributing novel, empirically grounded "
        f"insights not systematically explored in prior work."
    )

    concise = (
        f"Analisis {N} paper ({yr_min}–{yr_max}) menunjukkan celah kritis pada "
        f"{gap_list_id}, sementara {cov_list_id} sudah terlindungi dengan baik. "
        f"Penelitian ini mengisi {n_crit} gap utama dengan kontribusi baru yang "
        f"belum dieksplorasi secara sistematis dalam literatur sebelumnya."
    )

    exploratory = (
        f"Dari {N} publikasi ilmiah ({yr_min}–{yr_max}) dalam bidang {topic}, "
        f"muncul pertanyaan yang belum terjawab secara memadai: sejauh mana "
        f"{gap_list_id} dapat memperkuat dan memperluas pemahaman yang ada tentang "
        f"{cov_list_id}? Kami berhipotesis bahwa integrasi perspektif {top_gap} "
        f"ke dalam kerangka konseptual yang ada akan menghasilkan kontribusi ilmiah "
        f"yang signifikan dan membuka arah penelitian baru yang selama ini belum "
        f"tereksplorasi dalam komunitas riset terkait."
    )

    return {"formal": formal, "concise": concise, "exploratory": exploratory}


def _infer_topic_name(papers: list[dict]) -> str:
    if not papers:
        return "bidang ini"
    freq = collections.Counter()
    for p in papers:
        freq.update(_tokenize(p["title"]))
    top = freq.most_common(3)
    return " ".join(t for t, _ in top) if top else "bidang ini"


# ─────────────────────────────────────────────────────────────────
# 12. MAIN DATA BUILDER
# ─────────────────────────────────────────────────────────────────

def build_gap_data(papers: list[dict]) -> dict:
    """
    Entry point utama — pipeline lengkap dari list paper ke data siap-render.

    Dilengkapi in-memory cache (BUG FIX #4) sehingga render_gap() + gap_stats()
    tidak membangun data dua kali jika dipanggil dengan papers yang sama.
    """
    global _cache_key, _cache_val

    # Cache lookup
    key = _make_cache_key(papers)
    if key == _cache_key and _cache_val is not None:
        return _cache_val

    if not papers:
        empty = {
            "papers":[], "topic_matrix":{"keywords":[],"paper_shorts":[],
            "scores":[],"row_coverage":[],"col_breadth":[]},
            "gap_scores":[], "venn":{"covered":{"label":"","count":0,"pct":0,
            "keywords":[],"color":"#2dd4bf"},"overlap":{"label":"","count":0,
            "pct":0,"keywords":[],"color":"#a78bfa"},"gap":{"label":"","count":0,
            "pct":0,"keywords":[],"color":"#f59e0b"},"total_keywords":0,
            "summary":{"well_covered_pct":0,"gap_pct":0}},
            "radar":{"dimensions":["Temporal","Topical","Methodological",
            "Citation","Venue"],"coverage":[50,50,50,50,50],"gap":[50,50,50,50,50]},
            "timeline":{"years":[],"keywords":[],"scores":[],"paper_counts":{}},
            "hidden_findings":[], "gap_statement":"",
            "gap_statement_variants":{"formal":"","concise":"","exploratory":""},
            "summary":{"total_papers":0,"critical_gaps":0,"total_gaps":0,
            "top_gap":"—","top_covered":"—","coverage_score":0}
        }
        _cache_key = key
        _cache_val = empty
        return empty

    # ── Pipeline ──
    norm   = [_normalize_paper(p, i) for i, p in enumerate(papers)]
    matrix = _build_topic_matrix(norm)
    gaps   = _compute_gap_scores(norm, matrix)

    # INOVASI #2: ROS + Velocity (mutates gaps in-place)
    gaps   = _compute_ros_and_velocity(norm, gaps, matrix)

    venn   = _build_venn_data(gaps, norm)
    radar  = _build_radar_data(norm, gaps)

    # INOVASI #1: Timeline
    tline  = _build_timeline_data(norm, matrix)

    # INOVASI #3: Hidden findings with search queries
    hidden = _find_hidden_findings(norm, gaps)

    # INOVASI #4: Multi-variant statement
    topic_name = _infer_topic_name(norm)
    critical   = [g for g in gaps if g["recommendation"] == "critical"]
    covered_gs = [g for g in gaps if g["recommendation"] == "skip"]
    gap_kws    = [g["keyword"] for g in critical[:4]]
    cov_kws    = [g["keyword"] for g in covered_gs[-3:] if covered_gs]
    stmt_vars  = _generate_gap_statement_variants(topic_name, gap_kws, cov_kws, norm, gaps)

    top_gap = gaps[0]["keyword"]        if gaps       else "—"
    top_cov = covered_gs[-1]["keyword"] if covered_gs else "—"
    cov_scr = round(sum(g["coverage"] for g in gaps) / len(gaps) * 100) if gaps else 0

    result = {
        "papers":                norm,
        "topic_matrix":          matrix,
        "gap_scores":            gaps,
        "venn":                  venn,
        "radar":                 radar,
        "timeline":              tline,
        "hidden_findings":       hidden,
        "gap_statement":         stmt_vars["concise"],   # backward compat
        "gap_statement_variants": stmt_vars,
        "summary": {
            "total_papers":   len(norm),
            "critical_gaps":  len(critical),
            "total_gaps":     len(gaps),
            "top_gap":        top_gap,
            "top_covered":    top_cov,
            "coverage_score": cov_scr,
        },
    }

    _cache_key = key
    _cache_val = result
    return result


# ─────────────────────────────────────────────────────────────────
# 13. STATISTICS
# ─────────────────────────────────────────────────────────────────

def gap_stats(papers: list[dict]) -> dict:
    """
    Statistik ringkas untuk metric cards Streamlit.
    Memanfaatkan cache agar tidak membangun data dua kali (BUG FIX #4).
    """
    if not papers:
        return {}

    data = build_gap_data(papers)   # uses cache if available
    s    = data.get("summary", {})
    venn = data.get("venn",    {})
    gs   = data.get("gap_scores", [])

    top_ros = sorted(gs, key=lambda x: x.get("ros", 0), reverse=True)
    rising  = [g for g in gs if g.get("trend") == "rising"]

    return {
        "total_papers":        s.get("total_papers",   0),
        "total_keywords":      s.get("total_gaps",      0),
        "critical_gaps":       s.get("critical_gaps",   0),
        "coverage_score_pct":  s.get("coverage_score",  0),
        "top_gap_keyword":     s.get("top_gap",         "—"),
        "top_covered_keyword": s.get("top_covered",     "—"),
        "gap_pct":             venn.get("summary", {}).get("gap_pct",          0),
        "covered_pct":         venn.get("summary", {}).get("well_covered_pct", 0),
        "top_ros_keyword":     top_ros[0]["keyword"] if top_ros else "—",
        "rising_topics":       len(rising),
    }


# ─────────────────────────────────────────────────────────────────
# 14. HTML RENDERER
# ─────────────────────────────────────────────────────────────────

def render_gap(papers: list[dict], height: int = 720) -> str:
    data      = build_gap_data(papers)
    data_json = json.dumps(data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Research Gap Detector v2</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:100%;height:{height}px;overflow:hidden;background:#040d0d;color:#b8d4cc;font-family:'Sora',sans-serif;user-select:none;}}
:root{{
  --bg:#040d0d;--bg2:#071414;--bg3:#0b1f1f;--panel:rgba(7,20,20,0.97);
  --border:rgba(45,212,191,0.13);--border-hi:rgba(45,212,191,0.42);
  --teal:#2dd4bf;--amber:#f59e0b;--purple:#a78bfa;--red:#f87171;
  --green:#4ade80;--slate:#94a3b8;
  --critical-bg:rgba(248,113,113,.12);--explore-bg:rgba(245,158,11,.10);--skip-bg:rgba(148,163,184,.08);
  --text-hi:#e8faf6;--text-mid:#7ab8ac;--text-lo:#2e6058;
  --mono:'Space Mono',monospace;--code:'JetBrains Mono',monospace;--body:'Sora',sans-serif;
}}
#gw{{width:100%;height:{height}px;background:radial-gradient(ellipse 90% 80% at 50% 20%,rgba(10,40,36,.5) 0%,rgba(4,13,13,1) 60%);position:relative;overflow:hidden;display:flex;flex-direction:column;}}
#gw::before{{content:'';position:absolute;inset:0;pointer-events:none;z-index:1;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,30,25,.05) 3px,rgba(0,30,25,.05) 4px);}}

/* Tab bar */
#tabbar{{display:flex;align-items:stretch;background:rgba(4,13,13,.98);border-bottom:1px solid var(--border);z-index:30;position:relative;flex-shrink:0;}}
.tab-btn{{flex:1;padding:9px 6px;cursor:pointer;border:none;background:transparent;outline:none;font-family:var(--mono);font-size:8px;letter-spacing:1.5px;color:var(--text-lo);text-transform:uppercase;transition:all .22s;position:relative;display:flex;flex-direction:column;align-items:center;gap:2px;}}
.tab-btn:hover{{color:var(--text-mid);}}
.tab-btn.active{{color:var(--teal);}}
.tab-btn.active::after{{content:'';position:absolute;bottom:-1px;left:10%;right:10%;height:2px;background:var(--teal);border-radius:2px;box-shadow:0 0 8px var(--teal);}}
.tab-icon{{font-size:13px;}}.tab-num{{font-family:var(--mono);font-size:7px;color:var(--amber);background:rgba(245,158,11,.12);padding:1px 5px;border-radius:3px;border:1px solid rgba(245,158,11,.2);}}

/* Content */
#content{{flex:1;position:relative;overflow:hidden;}}
.tab-pane{{position:absolute;inset:0;display:none;opacity:0;transition:opacity .28s ease;overflow:hidden;}}
.tab-pane.active{{display:flex;flex-direction:column;opacity:1;}}

/* Controls */
.pane-ctrl{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:7px 14px;background:rgba(4,13,13,.8);border-bottom:1px solid var(--border);flex-shrink:0;}}
.pc-lbl{{font-family:var(--mono);font-size:8px;letter-spacing:2px;color:var(--text-lo);text-transform:uppercase;}}
.pc-btn{{padding:3px 10px;border-radius:3px;cursor:pointer;border:1px solid var(--border);background:transparent;font-family:var(--code);font-size:8.5px;color:var(--text-mid);transition:all .18s;}}
.pc-btn:hover{{border-color:var(--border-hi);color:var(--text-hi);}}.pc-btn.on{{border-color:var(--teal);color:var(--teal);background:rgba(45,212,191,.07);}}

/* ══ TAB 1: VENN ══ */
#pane-venn{{flex:1;}}
#venn-svg{{width:100%;height:100%;display:block;}}
.venn-lbl{{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;text-anchor:middle;dominant-baseline:central;pointer-events:none;}}
.venn-count{{font-family:var(--mono);font-size:22px;font-weight:700;text-anchor:middle;dominant-baseline:central;pointer-events:none;}}
.venn-sub{{font-family:var(--body);font-size:9px;text-anchor:middle;dominant-baseline:central;pointer-events:none;}}
.venn-region{{cursor:pointer;transition:opacity .2s;}}.venn-region:hover{{opacity:.82;}}
#venn-popup{{position:absolute;pointer-events:none;background:rgba(4,13,13,.97);border:1px solid var(--border-hi);border-radius:8px;padding:12px 14px;max-width:240px;box-shadow:0 10px 35px rgba(0,0,0,.75);backdrop-filter:blur(14px);z-index:60;display:none;}}
.vp-title{{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;}}
.vp-kw{{display:inline-block;margin:2px 2px;padding:2px 7px;border-radius:3px;font-family:var(--code);font-size:8px;border:1px solid currentColor;}}

/* ══ TAB 2: HEATMAP ══ */
#pane-heat{{flex:1;overflow:hidden;display:flex;flex-direction:column;}}
#heat-wrap{{flex:1;overflow:auto;position:relative;}}
#heat-svg{{display:block;}}
.hm-cell{{cursor:pointer;transition:opacity .15s;rx:2;}}.hm-cell:hover{{opacity:.75;stroke:#fff;stroke-width:.5;}}
.hm-cell.dim{{opacity:.08;}}.hm-cell.hi{{stroke:#fff;stroke-width:1;}}
.hm-rlbl{{font-family:var(--code);font-size:8.5px;fill:var(--text-mid);text-anchor:end;dominant-baseline:central;cursor:pointer;}}
.hm-rlbl:hover{{fill:var(--teal);}}.hm-clbl{{font-family:var(--code);font-size:7.5px;fill:var(--text-lo);text-anchor:start;dominant-baseline:central;}}
.hm-gap-lbl{{font-family:var(--mono);font-size:7px;fill:var(--text-lo);text-anchor:middle;}}

/* ══ TAB 3: GAP SCORE ══ */
#pane-gap{{display:flex;flex:1;overflow:hidden;}}
#gap-left{{flex:0 0 260px;padding:14px;border-right:1px solid var(--border);overflow:hidden;display:flex;flex-direction:column;gap:8px;}}
#radar-svg{{width:100%;flex-shrink:0;}}
#gap-right{{flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:6px;}}
.rad-lbl{{font-family:var(--code);font-size:8.5px;fill:var(--text-mid);text-anchor:middle;dominant-baseline:central;pointer-events:none;}}
.rad-val{{font-family:var(--mono);font-size:8px;fill:var(--teal);text-anchor:middle;dominant-baseline:central;pointer-events:none;}}
#gap-filter{{display:flex;gap:5px;flex-shrink:0;margin-bottom:6px;flex-wrap:wrap;}}
.gf-btn{{padding:3px 10px;border-radius:3px;cursor:pointer;border:1px solid var(--border);background:transparent;font-family:var(--mono);font-size:8px;color:var(--text-lo);transition:all .18s;}}
.gf-btn.on{{background:var(--critical-bg);border-color:var(--red);color:var(--red);}}.gf-btn.on-ex{{background:var(--explore-bg);border-color:var(--amber);color:var(--amber);}}.gf-btn.on-sk{{background:var(--skip-bg);border-color:var(--slate);color:var(--slate);}}
.gap-row{{border:1px solid var(--border);border-radius:6px;padding:9px 11px;background:rgba(7,20,20,.6);transition:opacity .2s,border-color .2s;cursor:default;}}
.gap-row:hover{{border-color:rgba(45,212,191,.28);}}.gap-row.dim{{opacity:.2;}}
.gr-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px;}}
.gr-kw{{font-family:var(--body);font-size:10.5px;font-weight:600;color:var(--text-hi);}}
.gr-score{{font-family:var(--mono);font-size:11px;font-weight:700;min-width:36px;text-align:right;}}
.badge{{padding:2px 8px;border-radius:3px;font-family:var(--mono);font-size:7.5px;letter-spacing:1px;font-weight:700;text-transform:uppercase;}}
.badge-critical{{background:var(--critical-bg);color:var(--red);border:1px solid rgba(248,113,113,.25);}}
.badge-explore{{background:var(--explore-bg);color:var(--amber);border:1px solid rgba(245,158,11,.22);}}
.badge-skip{{background:var(--skip-bg);color:var(--slate);border:1px solid rgba(148,163,184,.15);}}
.gr-meta{{display:flex;align-items:center;gap:10px;margin-bottom:4px;}}
.gr-cov{{font-family:var(--code);font-size:8px;color:var(--text-lo);}}
.gr-bar{{flex:1;height:3px;background:rgba(45,212,191,.1);border-radius:2px;overflow:hidden;}}
.gr-fill{{height:100%;border-radius:2px;transition:width .5s ease;}}
.gr-papers{{font-family:var(--code);font-size:7.5px;color:var(--text-lo);line-height:1.4;}}
/* ROS badge (INOVASI #2) */
.ros-badge{{padding:2px 7px;border-radius:3px;font-family:var(--mono);font-size:7px;letter-spacing:1px;text-transform:uppercase;background:rgba(45,212,191,.08);color:var(--teal);border:1px solid rgba(45,212,191,.18);}}
.trend-arrow{{font-size:10px;}}
.rad-legend{{display:flex;gap:12px;justify-content:center;}}
.rl-item{{display:flex;align-items:center;gap:5px;font-family:var(--code);font-size:8px;color:var(--text-lo);}}
.rl-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}

/* ══ TAB 4: HIDDEN FINDINGS ══ */
#pane-hidden{{flex:1;display:flex;flex-direction:column;overflow:hidden;}}
#hidden-scroll{{flex:1;overflow-y:auto;padding:12px;display:flex;flex-wrap:wrap;gap:10px;align-content:flex-start;}}
.hf-card{{width:calc(50% - 5px);border:1px solid var(--border);border-radius:8px;padding:11px 13px;background:rgba(7,20,20,.7);transition:border-color .2s;display:flex;flex-direction:column;gap:6px;}}
.hf-card:hover{{border-color:rgba(45,212,191,.3);}}.hf-card.critical{{border-left:3px solid var(--red);}}.hf-card.explore{{border-left:3px solid var(--amber);}}.hf-card.skip{{border-left:3px solid var(--slate);}}
.hf-concept{{font-family:var(--body);font-size:11px;font-weight:700;color:var(--text-hi);}}
.hf-meta{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;}}
.hf-type{{padding:2px 7px;border-radius:3px;font-family:var(--mono);font-size:7px;letter-spacing:1px;text-transform:uppercase;}}
.hf-type-temporal{{background:rgba(96,165,250,.1);color:#60a5fa;border:1px solid rgba(96,165,250,.2);}}.hf-type-methodological{{background:rgba(167,139,250,.1);color:var(--purple);border:1px solid rgba(167,139,250,.2);}}.hf-type-topical{{background:rgba(45,212,191,.08);color:var(--teal);border:1px solid rgba(45,212,191,.15);}}
.hf-score{{font-family:var(--mono);font-size:9px;color:var(--text-lo);}}
.hf-papers{{font-family:var(--code);font-size:8px;color:var(--text-lo);line-height:1.4;}}
/* INOVASI #3: Search query buttons */
.sq-wrap{{display:flex;gap:5px;flex-wrap:wrap;}}
.sq-btn{{font-family:var(--code);font-size:8px;color:var(--teal);background:rgba(45,212,191,.05);border:1px solid rgba(45,212,191,.15);border-radius:3px;padding:3px 8px;cursor:pointer;transition:background .15s;display:flex;align-items:center;gap:4px;white-space:nowrap;}}
.sq-btn:hover{{background:rgba(45,212,191,.14);}}

/* INOVASI #4: Statement variants */
#stmt-panel{{border-top:1px solid var(--border);padding:10px 14px;background:rgba(4,13,13,.95);flex-shrink:0;}}
.stmt-tabs{{display:flex;gap:4px;margin-bottom:7px;}}
.stmt-tab{{padding:3px 10px;border-radius:3px;cursor:pointer;border:1px solid var(--border);background:transparent;font-family:var(--mono);font-size:8px;color:var(--text-lo);transition:all .18s;}}
.stmt-tab.active{{border-color:var(--teal);color:var(--teal);background:rgba(45,212,191,.07);}}
#stmt-text{{font-family:var(--body);font-size:9.5px;color:var(--text-mid);line-height:1.6;max-height:72px;overflow-y:auto;background:rgba(7,20,20,.8);border:1px solid var(--border);border-radius:5px;padding:8px 10px;}}
.stmt-actions{{display:flex;gap:8px;margin-top:7px;}}
#stmt-copy{{padding:5px 14px;cursor:pointer;background:rgba(45,212,191,.07);border:1px solid rgba(45,212,191,.22);border-radius:4px;color:var(--teal);font-family:var(--mono);font-size:8px;letter-spacing:1.5px;text-transform:uppercase;transition:background .18s;}}
#stmt-copy:hover{{background:rgba(45,212,191,.18);}}.copied{{color:var(--green)!important;border-color:var(--green)!important;}}

/* ══ TAB 5: TIMELINE (INOVASI #1) ══ */
#pane-timeline{{flex:1;overflow:hidden;display:flex;flex-direction:column;}}
.tl-legend{{padding:6px 14px;border-bottom:1px solid var(--border);flex-shrink:0;display:flex;align-items:center;gap:16px;}}
.tl-grad{{height:10px;width:100px;border-radius:2px;background:linear-gradient(to right,rgba(4,13,13,1),rgba(45,212,191,.8));border:1px solid var(--border);}}
.tl-lbl{{font-family:var(--mono);font-size:8px;color:var(--text-lo);letter-spacing:1px;}}
#tl-wrap{{flex:1;overflow:auto;}}
#tl-svg{{display:block;}}

/* Tooltip */
#tooltip{{position:absolute;display:none;pointer-events:none;z-index:100;background:rgba(4,13,13,.97);border:1px solid var(--border-hi);border-radius:7px;padding:9px 12px;max-width:220px;box-shadow:0 8px 28px rgba(0,0,0,.7);backdrop-filter:blur(12px);font-size:10px;line-height:1.5;}}
::-webkit-scrollbar{{width:4px;height:4px;}}::-webkit-scrollbar-track{{background:rgba(45,212,191,.03);}}::-webkit-scrollbar-thumb{{background:rgba(45,212,191,.18);border-radius:2px;}}
</style>
</head>
<body>
<div id="gw">

  <div id="tabbar">
    <button class="tab-btn active" id="tb-venn"     onclick="switchTab('venn')">
      <span class="tab-icon">⬤</span>VENN<span class="tab-num" id="tn-venn">—</span>
    </button>
    <button class="tab-btn"        id="tb-heat"     onclick="switchTab('heat')">
      <span class="tab-icon">▦</span>HEATMAP<span class="tab-num" id="tn-heat">—</span>
    </button>
    <button class="tab-btn"        id="tb-gap"      onclick="switchTab('gap')">
      <span class="tab-icon">◎</span>GAP SCORE<span class="tab-num" id="tn-gap">—</span>
    </button>
    <button class="tab-btn"        id="tb-hidden"   onclick="switchTab('hidden')">
      <span class="tab-icon">◈</span>HIDDEN<span class="tab-num" id="tn-hidden">—</span>
    </button>
    <button class="tab-btn"        id="tb-timeline" onclick="switchTab('timeline')">
      <span class="tab-icon">◷</span>TIMELINE<span class="tab-num" id="tn-timeline">—</span>
    </button>
  </div>

  <div id="content">

    <!-- ════ TAB 1: VENN ════ -->
    <div class="tab-pane active" id="pane-venn">
      <svg id="venn-svg" xmlns="http://www.w3.org/2000/svg"></svg>
      <div id="venn-popup"></div>
    </div>

    <!-- ════ TAB 2: HEATMAP ════ -->
    <div class="tab-pane" id="pane-heat">
      <div class="pane-ctrl">
        <span class="pc-lbl">Sort :</span>
        <button class="pc-btn on" id="pc-gap-sort"  onclick="sortHeat('gap')">Gap Score</button>
        <button class="pc-btn"    id="pc-cov-sort"  onclick="sortHeat('coverage')">Coverage</button>
        <button class="pc-btn"    id="pc-az-sort"   onclick="sortHeat('alpha')">A–Z</button>
        <span class="pc-lbl" style="margin-left:8px">▲▼ = tren topik · klik baris/kolom untuk highlight</span>
      </div>
      <div id="heat-wrap"><svg id="heat-svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
    </div>

    <!-- ════ TAB 3: GAP SCORE ════ -->
    <div class="tab-pane" id="pane-gap">
      <div id="gap-left">
        <div style="font-family:var(--mono);font-size:8px;letter-spacing:2px;color:var(--text-lo);text-transform:uppercase;margin-bottom:4px">Coverage Radar</div>
        <svg id="radar-svg" viewBox="0 0 230 200" xmlns="http://www.w3.org/2000/svg"></svg>
        <div class="rad-legend">
          <span class="rl-item"><span class="rl-dot" style="background:var(--teal)"></span>Covered</span>
          <span class="rl-item"><span class="rl-dot" style="background:var(--amber)"></span>Gap</span>
        </div>
      </div>
      <div id="gap-right">
        <div id="gap-filter">
          <span style="font-family:var(--mono);font-size:8px;color:var(--text-lo);letter-spacing:1px;align-self:center">FILTER:</span>
          <button class="gf-btn on" id="gf-all"  onclick="filterGap('all')">ALL</button>
          <button class="gf-btn"    id="gf-crit" onclick="filterGap('critical')">CRITICAL</button>
          <button class="gf-btn"    id="gf-expl" onclick="filterGap('explore')">EXPLORE</button>
          <button class="gf-btn"    id="gf-skip" onclick="filterGap('skip')">SKIP</button>
          <button class="gf-btn"    id="gf-rise" onclick="filterGap('rising')" style="margin-left:4px">▲ RISING</button>
        </div>
        <div id="gap-rows"></div>
      </div>
    </div>

    <!-- ════ TAB 4: HIDDEN FINDINGS ════ -->
    <div class="tab-pane" id="pane-hidden">
      <div id="hidden-scroll"></div>
      <div id="stmt-panel">
        <div class="stmt-tabs">
          <button class="stmt-tab active" id="st-ringkas"  onclick="switchStmt('concise')">Ringkas</button>
          <button class="stmt-tab"        id="st-formal"   onclick="switchStmt('formal')">Formal (EN)</button>
          <button class="stmt-tab"        id="st-explor"   onclick="switchStmt('exploratory')">Eksploratif</button>
        </div>
        <div id="stmt-text">—</div>
        <div class="stmt-actions">
          <button id="stmt-copy" onclick="copyStatement()">⎘ SALIN</button>
        </div>
      </div>
    </div>

    <!-- ════ TAB 5: TIMELINE (INOVASI #1) ════ -->
    <div class="tab-pane" id="pane-timeline">
      <div class="tl-legend">
        <span class="tl-lbl">Intensitas cakupan topik per tahun</span>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="tl-lbl">rendah</span>
          <div class="tl-grad"></div>
          <span class="tl-lbl">tinggi</span>
        </div>
        <span class="tl-lbl" style="margin-left:auto">Bar bawah = jumlah paper/tahun</span>
      </div>
      <div id="tl-wrap"><svg id="tl-svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
    </div>

  </div><!-- #content -->

  <div id="tooltip"></div>
</div><!-- #gw -->

<script>
/* ════════════════
   DATA
════════════════ */
const D = {data_json};

/* ════════════════
   HELPERS
════════════════ */
const ns = (tag, a={{}}) => {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(a).forEach(([k,v]) => el.setAttribute(k,v));
  return el;
}};
const $ = id => document.getElementById(id);

function elW(el) {{
  if (!el) return 600;
  const r = el.getBoundingClientRect();
  return r.width > 0 ? r.width : (el.clientWidth || 600);
}}
function elH(el) {{
  if (!el) return 400;
  const r = el.getBoundingClientRect();
  return r.height > 0 ? r.height : (el.clientHeight || 400);
}}

function recColor(rec) {{ return rec==='critical'?'#f87171':rec==='explore'?'#f59e0b':'#94a3b8'; }}
function badgeClass(rec) {{ return rec==='critical'?'badge-critical':rec==='explore'?'badge-explore':'badge-skip'; }}

function trendArrow(trend) {{
  const map = {{rising:'<span class="trend-arrow" style="color:#4ade80">↑</span>',
                declining:'<span class="trend-arrow" style="color:#f87171">↓</span>',
                new:'<span class="trend-arrow" style="color:#f59e0b">★</span>',
                stable:'<span class="trend-arrow" style="color:#94a3b8">→</span>'}};
  return map[trend] || '';
}}

function showTT(ev, html) {{
  const tt = $('tooltip');
  tt.innerHTML = html;
  tt.style.display = 'block';
  const cw = elW($('gw')), ch = elH($('gw'));
  let tx = ev.clientX + 12, ty = ev.clientY - 8;
  if (tx + 230 > cw) tx = ev.clientX - 235;
  if (ty + 120 > ch) ty = ev.clientY - 120;
  tt.style.left = tx + 'px'; tt.style.top = ty + 'px';
}}
function hideTT() {{ $('tooltip').style.display = 'none'; }}

/* ════════════════
   TAB SWITCHING  (BUG FIX #2 #6)
════════════════ */
let _currentTab = 'venn';
// BUG FIX #6: render-once cache
const _rendered = {{heat:false, gap:false, hidden:false, timeline:false}};

function switchTab(name) {{
  if (_currentTab === name) return;
  _currentTab = name;

  document.querySelectorAll('.tab-pane').forEach(p => {{
    p.classList.remove('active');
    p.style.display = 'none';
  }});
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

  const pane = $('pane-' + name);
  pane.style.display = 'flex';
  requestAnimationFrame(() => pane.classList.add('active'));
  $('tb-' + name).classList.add('active');

  // BUG FIX #2: semua lazy render dipindah ke dalam rAF agar layout selesai
  if (name === 'heat') {{
    requestAnimationFrame(() => {{ if (!_rendered.heat) {{ _rendered.heat=true; renderHeatmap(); }} }});
  }} else if (name === 'gap') {{
    requestAnimationFrame(() => {{ if (!_rendered.gap) {{ _rendered.gap=true; renderRadar(); renderGapRows(); }} }});
  }} else if (name === 'hidden') {{
    requestAnimationFrame(() => {{ if (!_rendered.hidden) {{ _rendered.hidden=true; renderHidden(); }} }});
  }} else if (name === 'timeline') {{
    requestAnimationFrame(() => {{ if (!_rendered.timeline) {{ _rendered.timeline=true; renderTimeline(); }} }});
  }}
}}

/* ════════════════
   TAB 1 — VENN
════════════════ */
function renderVenn() {{
  const svg = $('venn-svg');
  svg.innerHTML = '';
  const vd = D.venn;
  if (!vd || !vd.covered) return;

  const w = elW(svg.parentElement||$('pane-venn'));
  const h = elH($('pane-venn')) - 4;
  svg.setAttribute('viewBox',`0 0 ${{w}} ${{h}}`);

  const cx=w/2, cy=h/2, R=Math.min(w,h)*0.28, overlap=R*0.38;
  const cxL=cx-R+overlap*.55, cxR=cx+R-overlap*.55;

  const defs = ns('defs');
  [['vg-teal','#2dd4bf','#0d9488'],['vg-amber','#f59e0b','#b45309'],['vg-purple','#a78bfa','#7c3aed']].forEach(([id,c1,c2]) => {{
    const rg = ns('radialGradient',{{id,cx:'50%',cy:'40%',r:'60%'}});
    rg.appendChild(ns('stop',{{'offset':'0%','stop-color':c1,'stop-opacity':'.55'}}));
    rg.appendChild(ns('stop',{{'offset':'100%','stop-color':c2,'stop-opacity':'.2'}}));
    defs.appendChild(rg);
  }});
  svg.appendChild(defs);
  svg.appendChild(ns('rect',{{width:w,height:h,fill:'transparent'}}));

  const gL=ns('g',{{class:'venn-region'}});
  gL.appendChild(ns('circle',{{cx:cxL,cy,r:R,fill:'url(#vg-teal)',stroke:'#2dd4bf','stroke-width':'1.2',opacity:'.85'}}));
  gL.addEventListener('click',()=>showVennPopup(vd.covered,'left',cxL,cy-R));
  gL.addEventListener('mousemove',ev=>showTT(ev,`<b style="color:#2dd4bf">Terlindungi</b><br>${{vd.covered.count}} topik (${{vd.covered.pct}}%)`));
  gL.addEventListener('mouseleave',hideTT);
  svg.appendChild(gL);

  const gR=ns('g',{{class:'venn-region'}});
  gR.appendChild(ns('circle',{{cx:cxR,cy,r:R,fill:'url(#vg-amber)',stroke:'#f59e0b','stroke-width':'1.2',opacity:'.85'}}));
  gR.addEventListener('click',()=>showVennPopup(vd.gap,'right',cxR,cy-R));
  gR.addEventListener('mousemove',ev=>showTT(ev,`<b style="color:#f59e0b">Celah Kritis</b><br>${{vd.gap.count}} topik (${{vd.gap.pct}}%)`));
  gR.addEventListener('mouseleave',hideTT);
  svg.appendChild(gR);

  const overlapX=(cxL+cxR)/2;
  svg.appendChild(ns('circle',{{cx:overlapX,cy,r:overlap*1.1,fill:'url(#vg-purple)',opacity:'.65','pointer-events':'none'}}));

  const gOv=ns('g',{{class:'venn-region'}});
  gOv.appendChild(ns('circle',{{cx:overlapX,cy,r:overlap*.9,fill:'transparent','pointer-events':'all'}}));
  gOv.addEventListener('click',()=>showVennPopup(vd.overlap,'center',overlapX,cy-overlap*.9));
  gOv.addEventListener('mousemove',ev=>showTT(ev,`<b style="color:#a78bfa">Sebagian</b><br>${{vd.overlap.count}} topik (${{vd.overlap.pct}}%)`));
  gOv.addEventListener('mouseleave',hideTT);
  svg.appendChild(gOv);

  function addLbl(cx2,cy2,data,clr){{
    const t1=ns('text',{{x:cx2,y:cy2-10,class:'venn-count',fill:clr}}); t1.textContent=data.count; svg.appendChild(t1);
    const t2=ns('text',{{x:cx2,y:cy2+18,class:'venn-sub',fill:'rgba(255,255,255,.45)'}}); t2.textContent=data.label; svg.appendChild(t2);
    const t3=ns('text',{{x:cx2,y:cy2+30,class:'venn-sub',fill:clr,opacity:'.65'}}); t3.textContent=data.pct+'% topik'; svg.appendChild(t3);
  }}
  addLbl(cxL-R*.38,cy,vd.covered,'#2dd4bf');
  addLbl(cxR+R*.38,cy,vd.gap,'#f59e0b');
  addLbl(overlapX,cy-8,vd.overlap,'#a78bfa');

  [[cxL,'← SUDAH DIPELAJARI','#2dd4bf'],[cx,'TRANSISI','#a78bfa'],[cxR,'PERLU DIEKSPLORASI →','#f59e0b']].forEach(([x,lbl,clr])=>{{
    const t=ns('text',{{x,y:h-22,class:'venn-lbl',fill:clr,opacity:'.55'}}); t.textContent=lbl; svg.appendChild(t);
  }});

  const sm=D.summary||{{}};
  const st=ns('text',{{x:cx,y:18,'font-family':'Space Mono,monospace','font-size':'9','fill':'rgba(45,212,191,.45)','text-anchor':'middle','dominant-baseline':'central'}});
  st.textContent=`${{sm.total_papers||0}} paper · ${{sm.total_gaps||0}} topik · ${{sm.critical_gaps||0}} celah kritis`;
  svg.appendChild(st);
}}

function showVennPopup(region,side,x,y) {{
  const p=$('venn-popup');
  const kws=region.keywords||[], clr=region.color||'#2dd4bf';
  p.innerHTML=`<div class="vp-title" style="color:${{clr}}">${{region.label||''}} (${{region.count||0}})</div>
    ${{kws.map(k=>`<span class="vp-kw" style="color:${{clr}};border-color:${{clr}}40">${{k}}</span>`).join('')}}
    ${{kws.length===0?'<span style="font-size:9px;color:#4a6588">Tidak ada topik</span>':''}}`;
  const pw=$('pane-venn'), ww=elW(pw), hh=elH(pw);
  let tx=x-120, ty=y-10;
  if(tx<8) tx=8; if(tx+248>ww) tx=ww-252; if(ty<8) ty=y+20; if(ty+150>hh) ty=hh-155;
  p.style.cssText=`display:block;left:${{tx}}px;top:${{ty}}px`;
  // BUG FIX #3: cek apakah klik di luar popup sebelum tutup
  setTimeout(()=> document.addEventListener('click', e => {{
    if (!$('venn-popup').contains(e.target)) closeVennPopup();
  }}, {{once:true}}), 50);
}}
function closeVennPopup() {{ $('venn-popup').style.display='none'; }}

/* ════════════════
   TAB 2 — HEATMAP  (BUG FIX #1 untuk sortHeat)
════════════════ */
const HEAT_STATE={{sort:'gap',highlightRow:-1,highlightCol:-1}};
const CELL_H=20, CELL_W_MAX=55, LABEL_W=138, GAP_BAR_W=40, PAD=8;

function heatColor(v) {{
  const a=0.07+v*0.85, r=Math.round(4+v*18), g2=Math.round(13+v*120), b=Math.round(13+v*100);
  return `rgba(${{r}},${{g2}},${{b}},${{a.toFixed(2)}})`;
}}
function gapBarColor(s) {{ return s>=62?'#f87171':s>=38?'#f59e0b':'#94a3b8'; }}

function sortHeat(mode) {{
  HEAT_STATE.sort = mode;
  // BUG FIX #1: mapping mode → DOM ID yang benar
  const idMap = {{gap:'gap', coverage:'cov', alpha:'az'}};
  Object.entries(idMap).forEach(([m, idKey]) => {{
    $('pc-'+idKey+'-sort').classList.toggle('on', m===mode);
  }});
  renderHeatmap();
}}

function renderHeatmap() {{
  const tm=D.topic_matrix, gs=D.gap_scores;
  if(!tm||!tm.keywords||!tm.keywords.length) return;

  const svg=$('heat-svg'), wrap=$('heat-wrap');
  const wrapW = elW(wrap);  // BUG FIX #2: pakai elW() yang fallback ke 600

  const trendMap={{}};
  gs.forEach(g=>{{ trendMap[g.keyword]=g.trend||'stable'; }});

  let kwIdxs=tm.keywords.map((_,i)=>i);
  if(HEAT_STATE.sort==='gap') {{
    const sm={{}};
    gs.forEach(g=>sm[g.keyword]=g.gap_score);
    kwIdxs.sort((a,b)=>(sm[tm.keywords[b]]||0)-(sm[tm.keywords[a]]||0));
  }} else if(HEAT_STATE.sort==='coverage') {{
    kwIdxs.sort((a,b)=>(tm.row_coverage[b]||0)-(tm.row_coverage[a]||0));
  }} else {{
    kwIdxs.sort((a,b)=>tm.keywords[a].localeCompare(tm.keywords[b]));
  }}

  const nRows=kwIdxs.length, nCols=tm.paper_shorts.length;
  const avail=Math.max(100,wrapW-LABEL_W-GAP_BAR_W-PAD*3);
  const cellW=Math.min(CELL_W_MAX,Math.floor(avail/nCols));
  const svgW=LABEL_W+nCols*cellW+GAP_BAR_W+PAD*3;
  const svgH=PAD*3+55+nRows*CELL_H+8;

  svg.setAttribute('viewBox',`0 0 ${{svgW}} ${{svgH}}`);
  svg.setAttribute('width',Math.max(svgW,wrapW));
  svg.setAttribute('height',svgH);
  svg.innerHTML='';
  svg.appendChild(ns('defs'));
  svg.appendChild(ns('rect',{{width:svgW,height:svgH,fill:'rgba(4,13,13,.6)'}}));

  const colLblX=LABEL_W+PAD;
  tm.paper_shorts.forEach((title,ci)=>{{
    const x=colLblX+ci*cellW+cellW/2;
    const g=ns('g',{{transform:`translate(${{x}},${{PAD+50}}) rotate(-55)`,cursor:'pointer'}});
    const t=ns('text',{{x:0,y:0,class:'hm-clbl','text-anchor':'end','dominant-baseline':'central'}});
    t.textContent=(title||'').substring(0,22);
    g.appendChild(t);
    g.addEventListener('click',()=>highlightCol(ci));
    svg.appendChild(g);
  }});

  const gapX=colLblX+nCols*cellW+PAD;
  const ghdr=ns('text',{{x:gapX+GAP_BAR_W/2,y:PAD+10,class:'hm-gap-lbl','text-anchor':'middle','dominant-baseline':'central'}});
  ghdr.textContent='GAP'; svg.appendChild(ghdr);

  const topY=PAD*2+55;
  kwIdxs.forEach((ki,rowIdx)=>{{
    const kw=tm.keywords[ki];
    const rowY=topY+rowIdx*CELL_H;
    const trend=trendMap[kw]||'stable';
    const trendChar={{rising:'▲',declining:'▽',new:'★',stable:''}};
    const trendClr={{rising:'#4ade80',declining:'#f87171',new:'#f59e0b',stable:'transparent'}};

    if(HEAT_STATE.highlightRow===ki) {{
      svg.appendChild(ns('rect',{{x:0,y:rowY,width:svgW,height:CELL_H,fill:'rgba(45,212,191,.07)','pointer-events':'none'}}));
    }}

    // INOVASI #5: trend symbol before label
    if(trendChar[trend]) {{
      const ts2=ns('text',{{x:LABEL_W-130,y:rowY+CELL_H/2,'font-family':'Space Mono,monospace','font-size':'8',fill:trendClr[trend],'dominant-baseline':'central'}});
      ts2.textContent=trendChar[trend]; svg.appendChild(ts2);
    }}

    const rl=ns('text',{{x:LABEL_W-6,y:rowY+CELL_H/2,class:'hm-rlbl'}});
    rl.textContent=kw.substring(0,18);
    rl.addEventListener('click',()=>highlightRow(ki));
    rl.addEventListener('mousemove',ev=>showTT(ev,`<b style="color:#2dd4bf">${{kw}}</b><br>Coverage: ${{Math.round((tm.row_coverage[ki]||0)*100)}}%<br>Tren: ${{trend}}`));
    rl.addEventListener('mouseleave',hideTT);
    svg.appendChild(rl);

    for(let ci=0;ci<nCols;ci++){{
      const val=(tm.scores[ki]||[])[ci]||0;
      const cx2=colLblX+ci*cellW;
      const isDimRow=HEAT_STATE.highlightRow!==-1&&HEAT_STATE.highlightRow!==ki;
      const isDimCol=HEAT_STATE.highlightCol!==-1&&HEAT_STATE.highlightCol!==ci;
      const cell=ns('rect',{{x:cx2+1,y:rowY+1,width:cellW-2,height:CELL_H-2,rx:2,fill:val>0?heatColor(val):'rgba(255,255,255,.02)',class:'hm-cell'+(isDimRow||isDimCol?' dim':'')+(val>0.5?' hi':'')}});
      cell.addEventListener('mousemove',ev=>showTT(ev,`<b style="color:#2dd4bf">${{kw}}</b><br>Paper: ${{(tm.paper_shorts[ci]||'').substring(0,30)}}<br>Score: ${{(val*100).toFixed(0)}}%`));
      cell.addEventListener('mouseleave',hideTT);
      svg.appendChild(cell);
    }}

    const gapEntry=D.gap_scores.find(g=>g.keyword===kw);
    const gapScore=gapEntry?gapEntry.gap_score:0;
    const barW=Math.max(2,(gapScore/100)*(GAP_BAR_W-6));
    const barClr=gapBarColor(gapScore);
    const barX=colLblX+nCols*cellW+PAD;
    svg.appendChild(ns('rect',{{x:barX,y:rowY+3,width:GAP_BAR_W-4,height:CELL_H-6,rx:2,fill:'rgba(255,255,255,.03)'}}));
    if(barW>0) svg.appendChild(ns('rect',{{x:barX,y:rowY+3,width:barW,height:CELL_H-6,rx:2,fill:barClr,opacity:'.75'}}));
    const gt=ns('text',{{x:barX+GAP_BAR_W-6,y:rowY+CELL_H/2,class:'hm-gap-lbl',fill:barClr,'text-anchor':'end','dominant-baseline':'central'}});
    gt.textContent=gapScore; svg.appendChild(gt);
  }});

  const botY=topY+nRows*CELL_H+4;
  for(let ci=0;ci<nCols;ci++){{
    const bv=tm.col_breadth[ci]||0, bW=Math.max(1,cellW*bv*0.9);
    const bX=colLblX+ci*cellW+(cellW-bW)/2;
    svg.appendChild(ns('rect',{{x:bX,y:botY,width:bW,height:4,rx:2,fill:'rgba(45,212,191,.35)'}}));
  }}
}}

function highlightRow(ki) {{ HEAT_STATE.highlightRow=HEAT_STATE.highlightRow===ki?-1:ki; HEAT_STATE.highlightCol=-1; renderHeatmap(); }}
function highlightCol(ci) {{ HEAT_STATE.highlightCol=HEAT_STATE.highlightCol===ci?-1:ci; HEAT_STATE.highlightRow=-1; renderHeatmap(); }}

/* ════════════════
   TAB 3 — RADAR
════════════════ */
function renderRadar() {{
  const svg=$('radar-svg'); svg.innerHTML='';
  const rd=D.radar; if(!rd||!rd.dimensions) return;
  const W2=115,H2=100,R=72,cx=W2,cy=H2,N=rd.dimensions.length;
  [0.25,0.5,0.75,1].forEach(f=>{{
    const pts=rd.dimensions.map((_,i)=>{{const a=(2*Math.PI*i/N)-Math.PI/2;return `${{cx+R*f*Math.cos(a)}},${{cy+R*f*Math.sin(a)}}`;}}).join(' ');
    svg.appendChild(ns('polygon',{{points:pts,fill:'none',stroke:'rgba(45,212,191,.1)','stroke-width':'1'}}));
  }});
  rd.dimensions.forEach((_,i)=>{{const a=(2*Math.PI*i/N)-Math.PI/2;svg.appendChild(ns('line',{{x1:cx,y1:cy,x2:cx+R*Math.cos(a),y2:cy+R*Math.sin(a),stroke:'rgba(45,212,191,.12)','stroke-width':'1'}}));}});

  function poly(vals,clr,op){{
    const pts=vals.map((v,i)=>{{const a=(2*Math.PI*i/N)-Math.PI/2,r=R*(v/100);return `${{cx+r*Math.cos(a)}},${{cy+r*Math.sin(a)}}`;  }}).join(' ');
    return ns('polygon',{{points:pts,fill:clr+'33',stroke:clr,'stroke-width':'1.8',opacity:op,'stroke-linejoin':'round'}});
  }}
  svg.appendChild(poly(rd.gap,'#f59e0b','.75'));
  svg.appendChild(poly(rd.coverage,'#2dd4bf','.85'));
  rd.dimensions.forEach((dim,i)=>{{
    const a=(2*Math.PI*i/N)-Math.PI/2,lx=cx+(R+16)*Math.cos(a),ly=cy+(R+16)*Math.sin(a);
    const lt=ns('text',{{x:lx,y:ly-5,class:'rad-lbl'}}); lt.textContent=dim; svg.appendChild(lt);
    const vt=ns('text',{{x:lx,y:ly+6,class:'rad-val'}}); vt.textContent=rd.coverage[i]+'%'; svg.appendChild(vt);
  }});
}}

/* ════════════════
   TAB 3 — GAP ROWS  (INOVASI #2: ROS + trend)
════════════════ */
let _gapFilter='all';
function filterGap(f) {{
  _gapFilter=f;
  ['all','crit','expl','skip','rise'].forEach(k=>$('gf-'+k)&&($('gf-'+k).className='gf-btn'));
  if(f==='all') $('gf-all').classList.add('on');
  else if(f==='critical') $('gf-crit').classList.add('on');
  else if(f==='explore')  $('gf-expl').classList.add('on-ex');
  else if(f==='skip')     $('gf-skip').classList.add('on-sk');
  else if(f==='rising')   $('gf-rise').classList.add('on');
  renderGapRows();
}}

function renderGapRows() {{
  const cont=$('gap-rows'), gs=D.gap_scores;
  if(!gs||!gs.length) {{ cont.innerHTML='<div style="font-family:var(--code);font-size:9px;color:var(--text-lo);padding:20px">Tidak ada data.</div>'; return; }}

  const filtered = _gapFilter==='all'    ? gs
                 : _gapFilter==='rising'  ? gs.filter(g=>g.trend==='rising')
                 : gs.filter(g=>g.recommendation===_gapFilter);

  cont.innerHTML = filtered.map(g => {{
    const clr=recColor(g.recommendation);
    const covW=Math.round(g.coverage*100);
    const covC=g.coverage>0.6?'#4ade80':g.coverage>0.3?'#f59e0b':'#f87171';
    const pps=(g.covering_papers||[]).slice(0,2).join('; ');
    const ros=g.ros||0;
    const vel=g.citation_velocity||0;
    const venu=g.venue_diversity||0;
    const tarr=trendArrow(g.trend||'stable');
    return `
    <div class="gap-row">
      <div class="gr-header">
        <span class="gr-kw">${{tarr}} ${{g.keyword}}</span>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="ros-badge">ROS ${{ros}}</span>
          <span class="gr-score" style="color:${{clr}}">${{g.gap_score}}</span>
          <span class="badge ${{badgeClass(g.recommendation)}}">${{g.recommendation.toUpperCase()}}</span>
        </div>
      </div>
      <div class="gr-meta">
        <span class="gr-cov">Cov: ${{covW}}%</span>
        <div class="gr-bar"><div class="gr-fill" style="width:${{covW}}%;background:${{covC}}"></div></div>
        <span class="gr-cov">${{g.covering_count||0}} paper · vel ${{vel}}/yr · ${{venu}} venue</span>
      </div>
      ${{pps?`<div class="gr-papers">📄 ${{pps}}</div>`:''}}
    </div>`;
  }}).join('');
}}

/* ════════════════
   TAB 4 — HIDDEN FINDINGS  (BUG FIX #5 + INOVASI #3 #4)
════════════════ */
let _stmtVariant = 'concise';

function switchStmt(v) {{
  _stmtVariant = v;
  document.querySelectorAll('.stmt-tab').forEach(b=>b.classList.remove('active'));
  const idMap={{concise:'st-ringkas',formal:'st-formal',exploratory:'st-explor'}};
  $(idMap[v]).classList.add('active');
  const vars=D.gap_statement_variants||{{}};
  $('stmt-text').textContent = vars[v] || D.gap_statement || '—';
}}

function renderHidden() {{
  const scr=$('hidden-scroll');
  // BUG FIX #5: ganti nama variabel untuk hindari shadowing
  const findings=D.hidden_findings;

  if(!findings||!findings.length) {{
    scr.innerHTML=`<div style="font-family:var(--code);font-size:9px;color:var(--text-lo);padding:20px">Tidak ada hidden findings terdeteksi.<br>Tambahkan paper dengan abstrak yang lebih kaya konteks.</div>`;
  }} else {{
    scr.innerHTML=findings.map(f=>{{
      const sqHtml=(f.search_queries||[]).map(q=>
        `<button class="sq-btn" title="${{q.tip}}" onclick="copyQuery('${{q.query.replace(/'/g,"").replace(/"/g,"")}}',${{JSON.stringify(q.label)}},this)">
          ${{q.label}}
        </button>`
      ).join('');
      return `
      <div class="hf-card ${{f.recommendation}}">
        <div class="hf-concept">${{trendArrow(f.trend||'stable')}} ${{f.concept}}</div>
        <div class="hf-meta">
          <span class="hf-type hf-type-${{f.gap_type}}">${{f.gap_type}}</span>
          <span class="badge ${{badgeClass(f.recommendation)}}">${{f.recommendation.toUpperCase()}}</span>
          <span class="hf-score">Gap ${{f.gap_score}} · ROS ${{f.ros||0}}</span>
        </div>
        ${{f.covering_papers&&f.covering_papers.length?`<div class="hf-papers">📄 ${{f.covering_papers.join(' · ')}}</div>`:''}}
        <div class="sq-wrap">${{sqHtml}}</div>
      </div>`;
    }}).join('');
  }}

  // INOVASI #4: statement variants
  const vars=D.gap_statement_variants||{{}};
  $('stmt-text').textContent = vars[_stmtVariant] || D.gap_statement || '—';
}}

function copyQuery(q, label, btn) {{
  navigator.clipboard.writeText(q)
    .then(()=>{{ btn.textContent='✅ '+label; setTimeout(()=>btn.textContent=label,1800); }})
    .catch(()=>{{ btn.textContent='⚠'; }});
}}

function copyStatement() {{
  const txt=$('stmt-text').textContent;
  const btn=$('stmt-copy');
  navigator.clipboard.writeText(txt)
    .then(()=>{{ btn.textContent='✅ TERSALIN!'; btn.classList.add('copied'); setTimeout(()=>{{btn.textContent='⎘ SALIN';btn.classList.remove('copied');}},2200); }})
    .catch(()=>{{ btn.textContent='⚠ Salin manual'; }});
}}

/* ════════════════
   TAB 5 — TIMELINE  (INOVASI #1)
════════════════ */
function renderTimeline() {{
  const svg=$('tl-svg'), wrap=$('tl-wrap');
  const td=D.timeline;
  if(!td||!td.years||!td.years.length) {{
    svg.innerHTML='<text x="20" y="30" font-family="Space Mono" font-size="10" fill="rgba(45,212,191,.3)">Tidak cukup variasi tahun untuk timeline.</text>';
    return;
  }}

  const wrapW = elW(wrap);
  const TL_LABEL_W=138, TL_CELL_H=22, PAD_TL=8;
  const nYears=td.years.length, nKws=td.keywords.length;
  const avail=Math.max(80,wrapW-TL_LABEL_W-PAD_TL*2);
  const cellW=Math.min(72,Math.max(18,Math.floor(avail/nYears)));

  const svgW=TL_LABEL_W+nYears*cellW+PAD_TL*2;
  const BAR_H=24, svgH=PAD_TL*2+28+nKws*TL_CELL_H+BAR_H+20;

  svg.setAttribute('viewBox',`0 0 ${{svgW}} ${{svgH}}`);
  svg.setAttribute('width',Math.max(svgW,wrapW));
  svg.setAttribute('height',svgH);
  svg.innerHTML='';
  svg.appendChild(ns('rect',{{width:svgW,height:svgH,fill:'rgba(4,13,13,.6)'}}));

  const colX=TL_LABEL_W+PAD_TL;
  const topY=PAD_TL+28;
  const botY=topY+nKws*TL_CELL_H+4;

  const maxCnt=Math.max(...Object.values(td.paper_counts),1);

  // Year headers + paper count bars
  td.years.forEach((yr,yi)=>{{
    const x=colX+yi*cellW+cellW/2;
    const ht=ns('text',{{x,y:PAD_TL+12,'font-family':'Space Mono,monospace','font-size':'8','fill':'rgba(45,212,191,.4)','text-anchor':'middle','dominant-baseline':'central'}});
    ht.textContent=yr; svg.appendChild(ht);

    const cnt=td.paper_counts[yr]||0;
    const bH=cnt>0?Math.max(3,(cnt/maxCnt)*BAR_H):0;
    if(bH>0) {{
      svg.appendChild(ns('rect',{{x:colX+yi*cellW+1,y:botY+BAR_H-bH,width:cellW-2,height:bH,rx:1,fill:'rgba(45,212,191,.22)'}}));
    }}
    const ct=ns('text',{{x,y:botY+BAR_H+8,'font-family':'Space Mono,monospace','font-size':'7','fill':'rgba(45,212,191,.3)','text-anchor':'middle','dominant-baseline':'central'}});
    ct.textContent=cnt||''; svg.appendChild(ct);
  }});

  // Keyword rows
  td.keywords.forEach((kw,ki)=>{{
    const rowY=topY+ki*TL_CELL_H;
    const rowScores=td.scores[ki]||[];

    // Row label
    const rl=ns('text',{{x:TL_LABEL_W-6,y:rowY+TL_CELL_H/2,'font-family':'JetBrains Mono,monospace','font-size':'8.5','fill':'rgba(122,184,172,.7)','text-anchor':'end','dominant-baseline':'central'}});
    rl.textContent=kw.substring(0,20); svg.appendChild(rl);

    // Cells
    td.years.forEach((yr,yi)=>{{
      const val=rowScores[yi]||0;
      const cx2=colX+yi*cellW;
      const cell=ns('rect',{{x:cx2+1,y:rowY+1,width:cellW-2,height:TL_CELL_H-2,rx:2,fill:val>0?heatColor(val):'rgba(255,255,255,.02)'}});
      cell.addEventListener('mousemove',ev=>showTT(ev,
        `<b style="color:#2dd4bf">${{kw}}</b><br>Tahun: ${{yr}}<br>Intensitas: ${{(val*100).toFixed(0)}}%<br>Paper/tahun: ${{td.paper_counts[yr]||0}}`
      ));
      cell.addEventListener('mouseleave',hideTT);
      svg.appendChild(cell);
    }});
  }});

  // Bar area label
  const bl=ns('text',{{x:TL_LABEL_W-6,y:botY+BAR_H/2,'font-family':'Space Mono,monospace','font-size':'7.5','fill':'rgba(45,212,191,.25)','text-anchor':'end','dominant-baseline':'central'}});
  bl.textContent='paper/yr'; svg.appendChild(bl);
}}

/* ════════════════
   BADGES + INIT
════════════════ */
function updateBadges() {{
  const sm=D.summary||{{}}, vn=D.venn||{{}};
  $('tn-venn').textContent    = (vn.gap||{{}}).count||'0';
  $('tn-heat').textContent    = (D.topic_matrix.keywords||[]).length||'0';
  $('tn-gap').textContent     = sm.critical_gaps||'0';
  $('tn-hidden').textContent  = (D.hidden_findings||[]).length||'0';
  $('tn-timeline').textContent= (D.timeline.years||[]).length||'0';
}}

function init() {{
  updateBadges();
  renderVenn();
}}

document.readyState==='loading'
  ? document.addEventListener('DOMContentLoaded',init)
  : setTimeout(init,60);
</script>
</body>
</html>"""
