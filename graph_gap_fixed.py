"""
graph_gap.py
============
Research Gap Detector — Fitur 3 dari Research Intelligence Center

Menganalisis korpus paper dan menemukan celah pengetahuan yang belum
terjamah — memberikan output yang langsung actionable untuk proposal riset.

4 sub-view dalam satu komponen:

  ① VENN DIAGRAM — dua lingkaran interaktif:
       Kiri (teal)  = topik yang SUDAH terlindungi dalam paper hasil pencarian
       Kanan (amber)= topik yang MUNCUL di literatur tapi BELUM terwakili
       Irisan       = topik yang terlindungi cukup baik
       Klik tiap region → daftar keyword + jumlah paper

  ② HEATMAP — grid topic × paper:
       Sumbu X = paper (kolom), Sumbu Y = keyword/topik (baris)
       Warna sel = intensitas keterwakilan topik di paper tersebut
       Merah = sangat relevan, Putih = tidak dibahas
       Kolom kanan = Gap Bar (merah = peluang riset besar)
       Klik baris  → highlight seluruh topik itu di semua paper
       Klik kolom  → highlight seluruh kontribusi paper itu
       Sort toggle → urutkan by gap score / coverage / alphabetical

  ③ GAP SCORE — analisis multidimensional:
       Radar chart 5 dimensi: Temporal · Topical · Methodological · Citation · Venue
       Tabel prioritas: Keyword | Coverage | Gap Score | Rekomendasi
       Badge rekomendasi: CRITICAL (merah) · EXPLORE (amber) · SKIP (abu)
       Filter real-time berdasarkan kategori rekomendasi

  ④ HIDDEN FINDINGS — "paper yang tidak kamu tahu harus kamu baca":
       Konsep yang sering muncul di abstrak sebagai referensi implisit
       tapi belum jadi paper utama dalam hasil pencarian.
       Gap Statement Generator: teks siap-pakai untuk bab Research Gap
       di proposal/skripsi, digenerate dari data nyata.

Algoritma utama:
  · TF-IDF modifikasi untuk ekstraksi keyword dari title + abstract
  · Gap Score = weighted(1-coverage, citation_importance, recency)
  · Venn partitioning berdasarkan threshold coverage
  · Radar normalisasi per dimensi dari distribusi aktual

Fungsi publik:
  render_gap(papers, height)    → str   HTML siap embed di Streamlit
  gap_stats(papers)             → dict  statistik untuk metric cards Streamlit
  build_gap_data(papers)        → dict  data mentah (berguna untuk testing)

Kontrak interface untuk graph_layer.py:
  from graph_gap import render_gap, gap_stats, build_gap_data
"""

from __future__ import annotations  # PEP 563 — lazy annotation eval; safe on Python ≥3.7

import re
import math
import json
import collections


# ─────────────────────────────────────────────────────────────────
# 0. STOPWORDS — comprehensive English + Indonesian + academic filler
# ─────────────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    # English function words
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","as","is","was","are","were","be","been","being","have",
    "has","had","do","does","did","will","would","could","should","may",
    "might","must","shall","can","not","no","nor","so","yet","both",
    "either","neither","each","few","more","most","other","some","such",
    "than","then","too","very","just","also","only","even","much","many",
    "own","same","s","t","don","now","i","we","you","he","she","they","it",
    "this","that","these","those","what","which","who","when","where","why","how",
    # Academic filler
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
    # Indonesian
    "yang","dengan","untuk","dari","dalam","pada","ini","itu","atau",
    "dan","di","ke","oleh","adalah","sebagai","dapat","akan","telah",
    "tidak","lebih","juga","serta","kami","kita","ada","bahwa","karena",
    "sebuah","suatu","sangat","sudah","sedang","hanya","namun","maka",
    # Short/noise tokens
    "al","et","vs","ie","eg","cf","fig","eq","tab","sec","ref","refs",
    # Common but non-informative academic terms
    "work","works","system","systems","model","problem","problems","data",
    "information","process","following","given","general","specific","related",
    "framework","overall","main","key","important","useful",
})

# Domain-specific high-value terms to BOOST (multiply TF by this factor)
_DOMAIN_BOOST = {
    # ML/AI core
    "transformer":3.0,"attention":2.5,"bert":2.5,"gpt":2.5,"llm":3.0,
    "neural":2.0,"deep":1.8,"learning":1.5,"embedding":2.5,"pretrain":2.5,
    "finetune":2.5,"finetuning":2.5,"pretrained":2.5,"language":1.8,
    "generative":2.5,"diffusion":3.0,"reinforcement":2.5,"federated":3.0,
    "contrastive":2.8,"self-supervised":3.0,"zero-shot":3.0,"few-shot":3.0,
    "multimodal":3.0,"vision":2.0,"graph":2.0,"knowledge":1.8,
    # Science/Bio
    "genomics":3.0,"proteomics":3.0,"crispr":3.0,"clinical":2.5,
    "biomarker":3.0,"immunotherapy":3.0,"cancer":2.0,"diagnosis":2.5,
    # General research value terms
    "efficiency":2.0,"scalability":2.5,"robustness":2.0,"interpretability":3.0,
    "explainability":3.0,"fairness":2.5,"alignment":3.0,"safety":2.5,
    "reasoning":2.5,"inference":2.0,"generation":2.0,"detection":2.0,
    "classification":2.0,"segmentation":2.5,"retrieval":2.5,"summarization":2.5,
}

_GAP_THRESHOLD_CRITICAL = 62
_GAP_THRESHOLD_EXPLORE  = 38
_TOP_KEYWORDS           = 24   # max keywords shown in heatmap


# ─────────────────────────────────────────────────────────────────
# 1. HELPERS
# ─────────────────────────────────────────────────────────────────

def _parse_year(val) -> int:
    try:
        y = int(str(val).strip())
        return y if 1900 < y <= 2030 else 2020
    except (ValueError, TypeError):
        return 2020


def _normalize_paper(p: dict, idx: int) -> dict:
    """Normalisasi satu paper dict menjadi format bersih & konsisten."""
    link  = p.get("link",     "") or ""
    title = (p.get("title",   "") or "Untitled").strip()
    abstr = (p.get("abstract","") or "").strip()
    year  = _parse_year(p.get("year", ""))
    cites = max(0, int(p.get("citations", 0) or 0))

    # Paper ID
    if "semanticscholar.org/paper/" in link:
        pid = link.split("/paper/")[-1].strip("/")
    else:
        pid = f"p{idx}_{re.sub(r'[^a-z0-9]', '_', title[:18].lower())}"

    short = (title[:52] + "…") if len(title) > 52 else title
    return {
        "id":          pid,
        "title":       title,
        "title_short": short,
        "authors":     (p.get("authors", "") or "N/A").strip(),
        "year":        year,
        "citations":   cites,
        "venue":       (p.get("venue",   "") or "Unknown").strip() or "Unknown",
        "abstract":    abstr,
        "link":        link,
        "source":      p.get("source", "unknown"),
    }


# ─────────────────────────────────────────────────────────────────
# 2. KEYWORD EXTRACTION
# ─────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, filter stopwords & noise."""
    text   = text.lower()
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", text)
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 3]


def _extract_bigrams(tokens: list[str]) -> list[str]:
    """Extract adjacent-token bigrams as compound terms."""
    return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens)-1)]


def _extract_keywords_for_paper(paper: dict) -> dict[str, float]:
    """
    Ekstrak keyword dengan bobot TF dari satu paper.

    Title diberi bobot 3× karena lebih representatif.
    Bigram dari title diberi bobot 2× untuk frasa penting.

    Returns dict: {keyword: weighted_frequency}
    """
    title_tok  = _tokenize(paper["title"])
    abstr_tok  = _tokenize(paper["abstract"])

    # Title bigrams
    title_bi   = _extract_bigrams(title_tok)

    freq: dict[str, float] = collections.defaultdict(float)

    for t in title_tok:
        freq[t] += 3.0 * _DOMAIN_BOOST.get(t, 1.0)
    for t in abstr_tok:
        freq[t] += 1.0 * _DOMAIN_BOOST.get(t, 1.0)
    for b in title_bi:
        freq[b] += 2.0  # bigrams always get moderate boost

    # Normalise by paper length to prevent long-abstract domination
    total = sum(freq.values()) or 1.0
    return {k: v / total for k, v in freq.items()}


# ─────────────────────────────────────────────────────────────────
# 3. TOPIC MATRIX (keyword × paper)
# ─────────────────────────────────────────────────────────────────

def _build_topic_matrix(papers: list[dict]) -> dict:
    """
    Bangun matrix TF-IDF penuh: keyword × paper.

    TF  = normalised term frequency dalam paper tersebut
    IDF = log(N / df + 1)   —  N = total papers, df = papers containing term

    Returns:
    {
      "keywords":     list[str],          top _TOP_KEYWORDS keywords
      "paper_shorts": list[str],          title_short per paper
      "scores":       list[list[float]],  [kw_idx][paper_idx] → 0..1
      "row_coverage": list[float],        fraction of papers mentioning kw
      "col_breadth":  list[float],        avg score per paper (breadth)
    }
    """
    N      = len(papers)
    if N == 0:
        return {"keywords":[],"paper_shorts":[],"scores":[],"row_coverage":[],"col_breadth":[]}

    # Per-paper TF dicts
    tf_dicts = [_extract_keywords_for_paper(p) for p in papers]

    # Document frequency
    df: dict[str, int] = collections.defaultdict(int)
    for tf in tf_dicts:
        for kw in tf:
            df[kw] += 1

    # TF-IDF for every keyword in every paper
    tfidf: dict[str, list[float]] = {}
    for kw, doc_count in df.items():
        if doc_count < 1:
            continue
        idf = math.log(N / doc_count + 1)
        scores_per_paper = [tf.get(kw, 0.0) * idf for tf in tf_dicts]
        tfidf[kw] = scores_per_paper

    # Rank keywords by max-across-papers (most distinctive first)
    ranked = sorted(tfidf.items(),
                    key=lambda x: max(x[1]),
                    reverse=True)

    # Take top _TOP_KEYWORDS; exclude pure bigrams if we have enough unigrams
    unigram_count = sum(1 for kw, _ in ranked if "_" not in kw)
    top_keywords  = []
    for kw, _ in ranked:
        if len(top_keywords) >= _TOP_KEYWORDS:
            break
        # Include bigrams only if we don't have enough unigrams
        if "_" in kw and unigram_count >= _TOP_KEYWORDS * 0.75:
            continue
        top_keywords.append(kw)

    if not top_keywords:
        return {"keywords":[],"paper_shorts":[],"scores":[],"row_coverage":[],"col_breadth":[]}

    # Build final score matrix — normalised to 0..1 per keyword
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

    # Display version of keyword (replace underscore bigrams with space)
    kw_display = [kw.replace("_", " ") for kw in top_keywords]

    return {
        "keywords":     kw_display,
        "paper_shorts": [p["title_short"] for p in papers],
        "scores":       score_matrix,
        "row_coverage": row_coverage,
        "col_breadth":  col_breadth,
    }


# ─────────────────────────────────────────────────────────────────
# 4. GAP SCORING
# ─────────────────────────────────────────────────────────────────

def _compute_gap_scores(
    papers:       list[dict],
    topic_matrix: dict,
) -> list[dict]:
    """
    Hitung Gap Score 0–100 untuk setiap keyword.

    Formula:
        gap = w1*(1−coverage) + w2*citation_importance + w3*recency_factor

        coverage           = frac of papers mentioning keyword  (0..1)
        citation_importance= log(avg_cite+1)/log(max_cite+1)    (0..1)
        recency_factor     = presence in newest 30% of papers   (0..1)

    Weights: w1=0.45  w2=0.35  w3=0.20

    Returns list of dicts sorted by gap_score descending.
    """
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
    yr_cutoff = years[max(0, int(N * 0.70))]   # newest 30% threshold

    results = []
    for ki, kw in enumerate(keywords):
        if ki >= len(row_coverage) or ki >= len(scores):
            continue

        coverage = row_coverage[ki]
        kw_scores = scores[ki]

        # Papers mentioning this keyword (score > 0)
        mentioning_idx = [pi for pi, v in enumerate(kw_scores) if v > 0]

        if not mentioning_idx:
            continue

        # Citation importance — avg citations of papers that mention this kw
        avg_cite = sum(papers[pi]["citations"] for pi in mentioning_idx) / len(mentioning_idx)
        cite_imp = math.log(avg_cite + 1) / math.log(max_cites + 1)

        # Recency — fraction of mentioning papers that are in newest 30%
        recent_count = sum(1 for pi in mentioning_idx
                           if papers[pi]["year"] >= yr_cutoff)
        recency = recent_count / len(mentioning_idx) if mentioning_idx else 0.0

        # Combined gap score
        raw_gap = (0.45 * (1 - coverage) +
                   0.35 * cite_imp        +
                   0.20 * recency)
        gap_score = round(min(100, max(0, raw_gap * 100)))

        # Recommendation badge
        if gap_score >= _GAP_THRESHOLD_CRITICAL and cite_imp >= 0.45:
            rec = "critical"
        elif gap_score >= _GAP_THRESHOLD_EXPLORE:
            rec = "explore"
        else:
            rec = "skip"

        # Which papers cover this keyword
        covering_titles = [papers[pi]["title_short"] for pi in mentioning_idx]

        results.append({
            "keyword":          kw,
            "coverage":         round(coverage, 3),
            "coverage_pct":     round(coverage * 100),
            "citation_imp":     round(cite_imp, 3),
            "recency":          round(recency, 3),
            "gap_score":        gap_score,
            "recommendation":   rec,
            "covering_papers":  covering_titles,
            "covering_count":   len(mentioning_idx),
        })

    return sorted(results, key=lambda x: x["gap_score"], reverse=True)


# ─────────────────────────────────────────────────────────────────
# 5. VENN DATA
# ─────────────────────────────────────────────────────────────────

def _build_venn_data(gap_scores: list[dict], papers: list[dict]) -> dict:
    """
    Partisi keyword menjadi 3 region Venn:

      covered   = gap_score < 35  (topik sudah terwakili cukup baik)
      overlap   = 35 ≤ gap_score < 62  (terwakili sebagian, bisa diperdalam)
      gap_only  = gap_score ≥ 62  (topik kritis yang belum terlindungi)

    Returns Venn config dict dengan ukuran, label, dan keyword per region.
    """
    covered  = [g for g in gap_scores if g["gap_score"] <  35]
    overlap  = [g for g in gap_scores if 35 <= g["gap_score"] < 62]
    gap_only = [g for g in gap_scores if g["gap_score"] >= 62]

    def top_kws(group, n=8):
        return [g["keyword"] for g in group[:n]]

    # Ukuran lingkaran proporsional terhadap jumlah keyword di region tersebut
    total = max(len(gap_scores), 1)
    return {
        "covered":  {
            "label":    "Topik Terlindungi",
            "count":    len(covered),
            "pct":      round(len(covered)  / total * 100),
            "keywords": top_kws(covered),
            "color":    "#2dd4bf",
        },
        "overlap":  {
            "label":    "Terlindungi Sebagian",
            "count":    len(overlap),
            "pct":      round(len(overlap)  / total * 100),
            "keywords": top_kws(overlap),
            "color":    "#a78bfa",
        },
        "gap":      {
            "label":    "Celah Kritis",
            "count":    len(gap_only),
            "pct":      round(len(gap_only) / total * 100),
            "keywords": top_kws(gap_only),
            "color":    "#f59e0b",
        },
        "total_keywords": total,
        "summary": {
            "well_covered_pct":   round(len(covered)  / total * 100),
            "gap_pct":            round(len(gap_only) / total * 100),
        }
    }


# ─────────────────────────────────────────────────────────────────
# 6. RADAR DATA
# ─────────────────────────────────────────────────────────────────

def _build_radar_data(papers: list[dict], gap_scores: list[dict]) -> dict:
    """
    Hitung 5 dimensi radar chart yang menggambarkan kondisi coverage riset.

    Dimensi:
      Temporal      = seberapa merata paper tersebar sepanjang waktu
      Topical       = kedalaman topik inti (coverage score rata-rata)
      Methodological= variasi metode/approach (diperkirakan dari keyword diversity)
      Citation      = kekuatan sitasi kolektif (log-scaled)
      Venue         = keragaman jurnal/konferensi tempat publish

    Setiap dimensi: score 0–100 (semakin tinggi = semakin baik coverage-nya)
    Gap dimension = 100 - coverage dimension

    Returns:
    {
      "dimensions": [str, ...],
      "coverage":   [float 0-100, ...],   # actual coverage per dim
      "gap":        [float 0-100, ...],   # 100 - coverage
    }
    """
    N = len(papers)
    if N == 0:
        zeros = [50, 50, 50, 50, 50]
        return {"dimensions":["Temporal","Topical","Methodological","Citation","Venue"],
                "coverage": zeros, "gap": [100-v for v in zeros]}

    # ── Temporal: std-dev of years (low std = clustered = low temporal coverage)
    years = [p["year"] for p in papers]
    yr_mean = sum(years) / N
    yr_std  = math.sqrt(sum((y - yr_mean)**2 for y in years) / N) if N > 1 else 0
    # Map std_dev 0→10 to score 20→100 (wider spread = better coverage)
    temporal = min(100, max(20, yr_std * 8 + 20))

    # ── Topical: average coverage across all gap_scores
    if gap_scores:
        avg_coverage = sum(g["coverage"] for g in gap_scores) / len(gap_scores)
        topical = round(avg_coverage * 100)
    else:
        topical = 40

    # ── Methodological: diversity of unique tokens across all titles
    all_title_tokens = set()
    for p in papers:
        all_title_tokens.update(_tokenize(p["title"]))
    method_score = min(100, len(all_title_tokens) * 3)

    # ── Citation: collective citation strength
    total_cites  = sum(p["citations"] for p in papers)
    max_one      = max((p["citations"] for p in papers), default=1)
    max_possible = N * max(max_one, 1)   # guard: never zero
    log_denom    = math.log(max_possible + 1)
    citation_score = round(math.log(total_cites + 1) / log_denom * 100) if log_denom > 0 else 0

    # ── Venue: unique venues / total papers (more diverse = better)
    unique_venues = len(set(p["venue"] for p in papers if p["venue"] != "Unknown"))
    venue_score   = min(100, round(unique_venues / N * 120))

    dims = ["Temporal", "Topical", "Methodological", "Citation", "Venue"]
    cov  = [round(temporal), round(topical), round(method_score),
            round(citation_score), round(venue_score)]
    gap  = [max(0, 100 - c) for c in cov]

    return {"dimensions": dims, "coverage": cov, "gap": gap}


# ─────────────────────────────────────────────────────────────────
# 7. HIDDEN FINDINGS
# ─────────────────────────────────────────────────────────────────

def _find_hidden_findings(
    papers:     list[dict],
    gap_scores: list[dict],
) -> list[dict]:
    """
    Temukan "hidden findings": konsep yang sering muncul secara implisit
    dalam abstrak (sebagai referensi, konteks, perbandingan) tetapi tidak
    jadi topik utama dari paper manapun dalam hasil pencarian.

    Pendekatan:
      1. Kumpulkan semua keyword dari gap_scores
      2. Cari pola implisit dalam abstrak:
         frasa setelah "unlike", "compared to", "building on", "following",
         "inspired by", "as in", "similar to", "extending", "based on"
      3. Keyword yang gap_score tinggi DAN muncul dalam pola implisit
         = kandidat "hidden finding"
      4. Tambah gap_type berdasarkan karakteristik keyword:
         temporal     = keyword yang mengandung angka tahun atau "recent"/"emerging"
         methodological = keyword yang berhubungan dengan metode
         topical      = keyword tematik / domain

    Returns list of dicts sorted by prominence descending.
    """
    if not papers or not gap_scores:
        return []

    # Build implicit mention counter from abstract patterns
    implicit_re = re.compile(
        r"(?:unlike|compared to|building on|following|inspired by|"
        r"as in|similar to|extending|based on|motivated by|"
        r"in contrast to|previously)\s+([a-z][a-z\s]{3,30})",
        re.IGNORECASE
    )

    implicit_counts: dict[str, int] = collections.defaultdict(int)
    for p in papers:
        for m in implicit_re.finditer(p.get("abstract", "")):
            phrase = m.group(1).lower().strip()
            tokens = [t for t in phrase.split() if t not in _STOPWORDS and len(t) >= 3]
            for t in tokens:
                implicit_counts[t] += 1

    # Cross-reference with high-gap keywords
    results = []
    for g in gap_scores:
        if g["gap_score"] < _GAP_THRESHOLD_EXPLORE:
            continue
        kw    = g["keyword"]
        kw_t  = kw.replace(" ", "_").split("_")

        implicit_score = sum(implicit_counts.get(t, 0) for t in kw_t)

        # Gap type classification
        temporal_markers = {"recent","emerging","new","latest","modern",
                             "contemporary","current","2020","2021","2022",
                             "2023","2024","2025","generation","evolution"}
        method_markers   = {"architecture","framework","algorithm","approach",
                             "mechanism","technique","strategy","pipeline",
                             "training","inference","optimization","loss",
                             "layer","encoder","decoder","head"}
        is_temporal      = any(t in temporal_markers for t in kw_t)
        is_method        = any(t in method_markers   for t in kw_t)
        gap_type         = "temporal" if is_temporal else "methodological" if is_method else "topical"

        # Recommended search query — use venue of the first covering paper
        # FIXED: previously always used papers[0]["venue"] regardless of context
        covering_titles = g.get("covering_papers", [])
        if covering_titles:
            title_to_venue = {p["title_short"]: p["venue"] for p in papers}
            relevant_venue = title_to_venue.get(covering_titles[0],
                                                  papers[0]["venue"] if papers else "")
        elif papers:
            relevant_venue = papers[0]["venue"]
        else:
            relevant_venue = ""
        search_q = (kw + " " + relevant_venue).strip()

        results.append({
            "concept":           kw,
            "gap_score":         g["gap_score"],
            "covering_count":    g["covering_count"],
            "recommendation":    g["recommendation"],
            "gap_type":          gap_type,
            "implicit_score":    implicit_score,
            "recommended_search": search_q,
            "covering_papers":   g["covering_papers"][:3],
        })

    # Sort: critical first, then by gap_score
    results.sort(key=lambda x: (x["recommendation"]!="critical", -x["gap_score"]))
    return results[:12]  # max 12 hidden findings


# ─────────────────────────────────────────────────────────────────
# 8. MAIN DATA BUILDER
# ─────────────────────────────────────────────────────────────────

def build_gap_data(papers: list[dict]) -> dict:
    """
    Titik masuk utama — bangun seluruh data Gap Detector dari list paper.

    Pipeline:
      normalize → topic_matrix → gap_scores → venn → radar → hidden_findings
      → gap_statement_template

    Input:
        papers — list of dict dari search_papers() / data_layer.py

    Output:
    {
      "papers":            [NormalizedPaperDict, ...]
      "topic_matrix":      TopicMatrixDict
      "gap_scores":        [GapScoreDict, ...]
      "venn":              VennDict
      "radar":             RadarDict
      "hidden_findings":   [HiddenFindingDict, ...]
      "gap_statement":     str   (template teks siap-pakai)
      "summary":           dict  (quick stats)
    }
    """
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
            "hidden_findings":[], "gap_statement":"",
            "summary":{"total_papers":0,"critical_gaps":0,"total_gaps":0,
            "top_gap":"—","top_covered":"—","coverage_score":0}
        }
        return empty

    # ── Normalize ──
    norm     = [_normalize_paper(p, i) for i, p in enumerate(papers)]

    # ── Pipeline ──
    matrix   = _build_topic_matrix(norm)
    gaps     = _compute_gap_scores(norm, matrix)
    venn     = _build_venn_data(gaps, norm)
    radar    = _build_radar_data(norm, gaps)
    hidden   = _find_hidden_findings(norm, gaps)

    # ── Summary quick stats ──
    critical = [g for g in gaps if g["recommendation"] == "critical"]
    covered  = [g for g in gaps if g["recommendation"] == "skip"]
    top_gap   = gaps[0]["keyword"]  if gaps    else "—"
    top_cov   = covered[-1]["keyword"] if covered else "—"
    cov_score = round(sum(g["coverage"] for g in gaps) / len(gaps) * 100) if gaps else 0

    # ── Gap Statement template ──
    topic_name = _infer_topic_name(norm)
    gap_kws    = [g["keyword"] for g in critical[:4]]
    cov_kws    = [g["keyword"] for g in covered[-3:] if covered]
    statement  = _generate_gap_statement(topic_name, gap_kws, cov_kws, norm, gaps)

    return {
        "papers":          norm,
        "topic_matrix":    matrix,
        "gap_scores":      gaps,
        "venn":            venn,
        "radar":           radar,
        "hidden_findings": hidden,
        "gap_statement":   statement,
        "summary": {
            "total_papers":   len(norm),
            "critical_gaps":  len(critical),
            "total_gaps":     len(gaps),
            "top_gap":        top_gap,
            "top_covered":    top_cov,
            "coverage_score": cov_score,
        },
    }


def _infer_topic_name(papers: list[dict]) -> str:
    """Inferensikan nama topik dari judul paper yang paling umum."""
    if not papers:
        return "bidang ini"
    all_tokens = []
    for p in papers:
        all_tokens.extend(_tokenize(p["title"]))
    if not all_tokens:
        return "bidang ini"
    freq = collections.Counter(all_tokens)
    top  = freq.most_common(3)
    return " ".join(t for t, _ in top)


def _generate_gap_statement(
    topic:    str,
    gap_kws:  list[str],
    cov_kws:  list[str],
    papers:   list[dict],
    gaps:     list[dict],
) -> str:
    """
    Generate template teks Gap Statement berbahasa Indonesia
    yang siap digunakan di bab Research Gap proposal/skripsi.
    """
    N       = len(papers)
    yr_min  = min(p["year"] for p in papers) if papers else 2018
    yr_max  = max(p["year"] for p in papers) if papers else 2024
    gap_list = ", ".join(f'"{k}"' for k in gap_kws) if gap_kws else '"topik terkait"'
    cov_list = ", ".join(f'"{k}"' for k in cov_kws) if cov_kws else '"area utama"'
    n_crit   = len([g for g in gaps if g["recommendation"] == "critical"])

    return (
        f"Berdasarkan analisis terhadap {N} paper ilmiah dalam rentang tahun "
        f"{yr_min}–{yr_max} pada bidang {topic}, ditemukan bahwa penelitian "
        f"yang ada telah cukup mendalam membahas aspek {cov_list}. "
        f"Namun demikian, terdapat {n_crit} celah penelitian yang signifikan, "
        f"terutama pada area {gap_list}. "
        f"Topik-topik ini menunjukkan tingkat keterwakilan rendah dalam literatur "
        f"yang ada, meskipun memiliki potensi dampak ilmiah yang tinggi berdasarkan "
        f"jumlah sitasi pada paper-paper yang menyentuh topik tersebut secara marginal. "
        f"Oleh karena itu, penelitian ini diposisikan untuk mengisi celah tersebut "
        f"dengan menawarkan kontribusi baru yang belum dieksplorasi secara menyeluruh "
        f"dalam literatur sebelumnya."
    )


# ─────────────────────────────────────────────────────────────────
# 9. STATISTICS
# ─────────────────────────────────────────────────────────────────

def gap_stats(papers: list[dict]) -> dict:
    """
    Statistik ringkas untuk ditampilkan sebagai Streamlit metric cards.

    Returns dict:
        total_papers, total_keywords, critical_gaps, coverage_score_pct,
        top_gap_keyword, top_covered_keyword, gap_pct, covered_pct
    """
    if not papers:
        return {}

    data = build_gap_data(papers)
    s    = data.get("summary", {})
    venn = data.get("venn",    {})

    return {
        "total_papers":       s.get("total_papers",   0),
        "total_keywords":     s.get("total_gaps",      0),
        "critical_gaps":      s.get("critical_gaps",   0),
        "coverage_score_pct": s.get("coverage_score",  0),
        "top_gap_keyword":    s.get("top_gap",         "—"),
        "top_covered_keyword":s.get("top_covered",     "—"),
        "gap_pct":            venn.get("summary", {}).get("gap_pct",           0),
        "covered_pct":        venn.get("summary", {}).get("well_covered_pct",  0),
    }


# ─────────────────────────────────────────────────────────────────
# 10. HTML RENDERER
# ─────────────────────────────────────────────────────────────────

def render_gap(papers: list[dict], height: int = 720) -> str:
    """
    Render Research Gap Detector sebagai HTML interaktif penuh (4 sub-tab).

    Gunakan di Streamlit:
        import streamlit.components.v1 as components
        components.html(render_gap(papers), height=740, scrolling=False)

    Returns:
        str — ~55KB HTML lengkap siap embed
    """
    data      = build_gap_data(papers)
    data_json = json.dumps(data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Research Gap Detector</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:{height}px;overflow:hidden;
  background:#040d0d;color:#b8d4cc;
  font-family:'Sora',sans-serif;user-select:none;
}}

/* ── Tokens ── */
:root{{
  --bg:        #040d0d;
  --bg2:       #071414;
  --bg3:       #0b1f1f;
  --panel:     rgba(7,20,20,0.97);
  --border:    rgba(45,212,191,0.13);
  --border-hi: rgba(45,212,191,0.42);

  --teal:   #2dd4bf;
  --amber:  #f59e0b;
  --purple: #a78bfa;
  --red:    #f87171;
  --green:  #4ade80;
  --slate:  #94a3b8;

  --critical-bg:  rgba(248,113,113,.12);
  --explore-bg:   rgba(245,158,11,.10);
  --skip-bg:      rgba(148,163,184,.08);

  --text-hi:  #e8faf6;
  --text-mid: #7ab8ac;
  --text-lo:  #2e6058;

  --mono:  'Space Mono',monospace;
  --code:  'JetBrains Mono',monospace;
  --body:  'Sora',sans-serif;
}}

/* ── Root ── */
#gw{{
  width:100%;height:{height}px;
  background:radial-gradient(ellipse 90% 80% at 50% 20%,
    rgba(10,40,36,.5) 0%,rgba(4,13,13,1) 60%);
  position:relative;overflow:hidden;
  display:flex;flex-direction:column;
}}

/* Grain overlay */
#gw::before{{
  content:'';position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(
    0deg,transparent,transparent 3px,rgba(0,30,25,.05) 3px,rgba(0,30,25,.05) 4px
  );
}}

/* ── Tab bar ── */
#tabbar{{
  display:flex;align-items:stretch;
  background:rgba(4,13,13,.98);
  border-bottom:1px solid var(--border);
  z-index:30;position:relative;flex-shrink:0;
}}
.tab-btn{{
  flex:1;padding:9px 6px;cursor:pointer;
  border:none;background:transparent;outline:none;
  font-family:var(--mono);font-size:8.5px;letter-spacing:1.5px;
  color:var(--text-lo);text-transform:uppercase;
  transition:all .22s;position:relative;
  display:flex;flex-direction:column;align-items:center;gap:2px;
}}
.tab-btn:hover{{color:var(--text-mid);}}
.tab-btn.active{{color:var(--teal);}}
.tab-btn.active::after{{
  content:'';position:absolute;bottom:-1px;left:10%;right:10%;
  height:2px;background:var(--teal);border-radius:2px;
  box-shadow:0 0 8px var(--teal);
}}
.tab-icon{{font-size:13px;}}
.tab-num{{
  font-family:var(--mono);font-size:7px;color:var(--amber);
  background:rgba(245,158,11,.12);padding:1px 5px;border-radius:3px;
  border:1px solid rgba(245,158,11,.2);
}}

/* ── Content area ── */
#content{{flex:1;position:relative;overflow:hidden;}}
.tab-pane{{
  position:absolute;inset:0;
  display:none;opacity:0;
  transition:opacity .28s ease;overflow:hidden;
}}
.tab-pane.active{{display:flex;flex-direction:column;opacity:1;}}

/* ── Shared sub-controls ── */
.pane-ctrl{{
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:7px 14px;background:rgba(4,13,13,.8);
  border-bottom:1px solid var(--border);flex-shrink:0;
}}
.pc-lbl{{font-family:var(--mono);font-size:8px;letter-spacing:2px;color:var(--text-lo);text-transform:uppercase;}}
.pc-btn{{
  padding:3px 10px;border-radius:3px;cursor:pointer;
  border:1px solid var(--border);background:transparent;
  font-family:var(--code);font-size:8.5px;color:var(--text-mid);
  transition:all .18s;
}}
.pc-btn:hover{{border-color:var(--border-hi);color:var(--text-hi);}}
.pc-btn.on{{border-color:var(--teal);color:var(--teal);background:rgba(45,212,191,.07);}}
.pc-btn.on-amber{{border-color:var(--amber);color:var(--amber);background:rgba(245,158,11,.07);}}
.pc-btn.on-purple{{border-color:var(--purple);color:var(--purple);background:rgba(167,139,250,.07);}}

/* ════════════════════════════════════════
   TAB 1 — VENN
════════════════════════════════════════ */
#pane-venn{{flex:1;}}
#venn-svg{{width:100%;height:100%;display:block;}}
.venn-lbl{{
  font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.8px;
  text-transform:uppercase;text-anchor:middle;dominant-baseline:central;
  pointer-events:none;
}}
.venn-count{{
  font-family:var(--mono);font-size:22px;font-weight:700;
  text-anchor:middle;dominant-baseline:central;pointer-events:none;
}}
.venn-sub{{
  font-family:var(--body);font-size:9px;
  text-anchor:middle;dominant-baseline:central;pointer-events:none;
}}
.venn-region{{cursor:pointer;transition:opacity .2s;}}
.venn-region:hover{{opacity:.82;}}

/* Venn keyword popup */
#venn-popup{{
  position:absolute;pointer-events:none;
  background:rgba(4,13,13,.97);border:1px solid var(--border-hi);
  border-radius:8px;padding:12px 14px;max-width:240px;
  box-shadow:0 10px 35px rgba(0,0,0,.75);backdrop-filter:blur(14px);
  z-index:60;display:none;
}}
.vp-title{{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;}}
.vp-kw{{
  display:inline-block;margin:2px 2px;
  padding:2px 7px;border-radius:3px;
  font-family:var(--code);font-size:8px;
  border:1px solid currentColor;
}}

/* ════════════════════════════════════════
   TAB 2 — HEATMAP
════════════════════════════════════════ */
#pane-heat{{flex:1;overflow:hidden;display:flex;flex-direction:column;}}
#heat-wrap{{flex:1;overflow:auto;position:relative;}}
#heat-svg{{display:block;}}
.hm-cell{{cursor:pointer;transition:opacity .15s;rx:2;}}
.hm-cell:hover{{opacity:.75;stroke:#fff;stroke-width:.5;}}
.hm-cell.dim{{opacity:.08;}}
.hm-cell.hi{{stroke:#fff;stroke-width:1;filter:drop-shadow(0 0 3px #fff4);}}
.hm-rlbl{{
  font-family:var(--code);font-size:8.5px;fill:var(--text-mid);
  text-anchor:end;dominant-baseline:central;cursor:pointer;
}}
.hm-rlbl:hover{{fill:var(--teal);}}
.hm-clbl{{
  font-family:var(--code);font-size:7.5px;fill:var(--text-lo);
  text-anchor:start;dominant-baseline:central;
}}
.hm-gap-bar{{cursor:default;}}
.hm-gap-lbl{{font-family:var(--mono);font-size:7px;fill:var(--text-lo);text-anchor:middle;}}

/* ════════════════════════════════════════
   TAB 3 — GAP SCORE
════════════════════════════════════════ */
#pane-gap{{display:flex;flex:1;overflow:hidden;}}
#gap-left{{
  flex:0 0 260px;padding:14px;
  border-right:1px solid var(--border);overflow:hidden;
  display:flex;flex-direction:column;gap:8px;
}}
#radar-svg{{width:100%;flex-shrink:0;}}
#gap-right{{flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:6px;}}

/* Radar labels */
.rad-lbl{{
  font-family:var(--code);font-size:8.5px;fill:var(--text-mid);
  text-anchor:middle;dominant-baseline:central;pointer-events:none;
}}
.rad-val{{
  font-family:var(--mono);font-size:8px;fill:var(--teal);
  text-anchor:middle;dominant-baseline:central;pointer-events:none;
}}

/* Filter bar */
#gap-filter{{
  display:flex;gap:5px;flex-shrink:0;margin-bottom:6px;
}}
.gf-btn{{
  padding:3px 10px;border-radius:3px;cursor:pointer;
  border:1px solid var(--border);background:transparent;
  font-family:var(--mono);font-size:8px;color:var(--text-lo);
  transition:all .18s;
}}
.gf-btn.on{{background:var(--critical-bg);border-color:var(--red);color:var(--red);}}
.gf-btn.on-ex{{background:var(--explore-bg);border-color:var(--amber);color:var(--amber);}}
.gf-btn.on-sk{{background:var(--skip-bg);border-color:var(--slate);color:var(--slate);}}

/* Gap score rows */
.gap-row{{
  border:1px solid var(--border);border-radius:6px;
  padding:9px 11px;background:rgba(7,20,20,.6);
  transition:opacity .2s,border-color .2s;
  cursor:default;
}}
.gap-row:hover{{border-color:rgba(45,212,191,.28);}}
.gap-row.dim{{opacity:.2;}}
.gr-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px;}}
.gr-kw{{font-family:var(--body);font-size:10.5px;font-weight:600;color:var(--text-hi);}}
.gr-score{{
  font-family:var(--mono);font-size:11px;font-weight:700;
  min-width:36px;text-align:right;
}}
.badge{{
  padding:2px 8px;border-radius:3px;
  font-family:var(--mono);font-size:7.5px;letter-spacing:1px;
  font-weight:700;text-transform:uppercase;
}}
.badge-critical{{background:var(--critical-bg);color:var(--red);border:1px solid rgba(248,113,113,.25);}}
.badge-explore {{background:var(--explore-bg);color:var(--amber);border:1px solid rgba(245,158,11,.22);}}
.badge-skip    {{background:var(--skip-bg);color:var(--slate);border:1px solid rgba(148,163,184,.15);}}

.gr-meta{{display:flex;align-items:center;gap:10px;margin-bottom:4px;}}
.gr-cov{{font-family:var(--code);font-size:8px;color:var(--text-lo);}}
.gr-bar{{flex:1;height:3px;background:rgba(45,212,191,.1);border-radius:2px;overflow:hidden;}}
.gr-fill{{height:100%;border-radius:2px;transition:width .5s ease;}}
.gr-papers{{font-family:var(--code);font-size:7.5px;color:var(--text-lo);line-height:1.4;}}

/* Radar legend */
.rad-legend{{display:flex;gap:12px;justify-content:center;}}
.rl-item{{display:flex;align-items:center;gap:5px;font-family:var(--code);font-size:8px;color:var(--text-lo);}}
.rl-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}

/* ════════════════════════════════════════
   TAB 4 — HIDDEN FINDINGS
════════════════════════════════════════ */
#pane-hidden{{flex:1;display:flex;flex-direction:column;overflow:hidden;}}
#hidden-scroll{{flex:1;overflow-y:auto;padding:12px;display:flex;flex-wrap:wrap;gap:10px;align-content:flex-start;}}

.hf-card{{
  width:calc(50% - 5px);border:1px solid var(--border);border-radius:8px;
  padding:11px 13px;background:rgba(7,20,20,.7);
  transition:border-color .2s;
  display:flex;flex-direction:column;gap:6px;
}}
.hf-card:hover{{border-color:rgba(45,212,191,.3);}}
.hf-card.critical{{border-left:3px solid var(--red);}}
.hf-card.explore {{border-left:3px solid var(--amber);}}
.hf-card.skip    {{border-left:3px solid var(--slate);}}
.hf-concept{{font-family:var(--body);font-size:11px;font-weight:700;color:var(--text-hi);}}
.hf-meta{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;}}
.hf-type{{
  padding:2px 7px;border-radius:3px;
  font-family:var(--mono);font-size:7px;letter-spacing:1px;text-transform:uppercase;
}}
.hf-type-temporal       {{background:rgba(96,165,250,.1);color:#60a5fa;border:1px solid rgba(96,165,250,.2);}}
.hf-type-methodological {{background:rgba(167,139,250,.1);color:var(--purple);border:1px solid rgba(167,139,250,.2);}}
.hf-type-topical        {{background:rgba(45,212,191,.08);color:var(--teal);border:1px solid rgba(45,212,191,.15);}}
.hf-score{{font-family:var(--mono);font-size:9px;color:var(--text-lo);}}
.hf-papers{{font-family:var(--code);font-size:8px;color:var(--text-lo);line-height:1.4;}}
.hf-search{{
  font-family:var(--code);font-size:8px;color:var(--teal);
  background:rgba(45,212,191,.06);border:1px solid rgba(45,212,191,.15);
  border-radius:3px;padding:3px 8px;cursor:pointer;transition:background .15s;
  display:flex;align-items:center;gap:4px;width:fit-content;
}}
.hf-search:hover{{background:rgba(45,212,191,.14);}}

/* Gap statement panel */
#stmt-panel{{
  border-top:1px solid var(--border);padding:12px 14px;
  background:rgba(4,13,13,.95);flex-shrink:0;
}}
.stmt-title{{
  font-family:var(--mono);font-size:8px;letter-spacing:2px;
  color:var(--text-lo);text-transform:uppercase;margin-bottom:6px;
}}
#stmt-text{{
  font-family:var(--body);font-size:9.5px;color:var(--text-mid);
  line-height:1.6;max-height:68px;overflow-y:auto;
  background:rgba(7,20,20,.8);border:1px solid var(--border);
  border-radius:5px;padding:8px 10px;
}}
#stmt-copy{{
  margin-top:7px;padding:6px 16px;cursor:pointer;
  background:rgba(45,212,191,.07);
  border:1px solid rgba(45,212,191,.22);border-radius:4px;
  color:var(--teal);font-family:var(--mono);font-size:8px;
  letter-spacing:1.5px;text-transform:uppercase;transition:background .18s;
}}
#stmt-copy:hover{{background:rgba(45,212,191,.18);}}
#stmt-copy.copied{{color:var(--green);border-color:var(--green);}}

/* ── Tooltip general ── */
#tooltip{{
  position:absolute;display:none;pointer-events:none;z-index:100;
  background:rgba(4,13,13,.97);border:1px solid var(--border-hi);
  border-radius:7px;padding:9px 12px;max-width:220px;
  box-shadow:0 8px 28px rgba(0,0,0,.7);backdrop-filter:blur(12px);
  font-size:10px;line-height:1.5;
}}

/* ── Scrollbar styling ── */
::-webkit-scrollbar{{width:4px;height:4px;}}
::-webkit-scrollbar-track{{background:rgba(45,212,191,.03);}}
::-webkit-scrollbar-thumb{{background:rgba(45,212,191,.18);border-radius:2px;}}
</style>
</head>
<body>
<div id="gw">

  <!-- ── Tab bar ── -->
  <div id="tabbar">
    <button class="tab-btn active" id="tb-venn"   onclick="switchTab('venn')">
      <span class="tab-icon">⬤</span>VENN
      <span class="tab-num" id="tn-venn">—</span>
    </button>
    <button class="tab-btn"        id="tb-heat"   onclick="switchTab('heat')">
      <span class="tab-icon">▦</span>HEATMAP
      <span class="tab-num" id="tn-heat">—</span>
    </button>
    <button class="tab-btn"        id="tb-gap"    onclick="switchTab('gap')">
      <span class="tab-icon">◎</span>GAP SCORE
      <span class="tab-num" id="tn-gap">—</span>
    </button>
    <button class="tab-btn"        id="tb-hidden" onclick="switchTab('hidden')">
      <span class="tab-icon">◈</span>HIDDEN
      <span class="tab-num" id="tn-hidden">—</span>
    </button>
  </div>

  <!-- ── Content ── -->
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
        <span class="pc-lbl" style="margin-left:8px">Klik baris/kolom untuk highlight</span>
      </div>
      <div id="heat-wrap">
        <svg id="heat-svg" xmlns="http://www.w3.org/2000/svg"></svg>
      </div>
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
          <button class="gf-btn on"    id="gf-all"  onclick="filterGap('all')">ALL</button>
          <button class="gf-btn"       id="gf-crit" onclick="filterGap('critical')">CRITICAL</button>
          <button class="gf-btn"       id="gf-expl" onclick="filterGap('explore')">EXPLORE</button>
          <button class="gf-btn"       id="gf-skip" onclick="filterGap('skip')">SKIP</button>
        </div>
        <div id="gap-rows"></div>
      </div>
    </div>

    <!-- ════ TAB 4: HIDDEN FINDINGS ════ -->
    <div class="tab-pane" id="pane-hidden">
      <div id="hidden-scroll"></div>
      <div id="stmt-panel">
        <div class="stmt-title">◈ Research Gap Statement — Siap Pakai</div>
        <div id="stmt-text">—</div>
        <button id="stmt-copy" onclick="copyStatement()">⎘ SALIN KE CLIPBOARD</button>
      </div>
    </div>

  </div><!-- #content -->

  <!-- Tooltip -->
  <div id="tooltip"></div>

</div><!-- #gw -->

<script>
/* ════════════════════════════════════════
   DATA
════════════════════════════════════════ */
const D = {data_json};

/* ════════════════════════════════════════
   HELPERS
════════════════════════════════════════ */
const ns = (tag, a={{}}) => {{
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(a).forEach(([k,v]) => el.setAttribute(k,v));
  return el;
}};
const $ = id => document.getElementById(id);
function W(el) {{ return (el||document.getElementById('content')).clientWidth  || 600; }}
function H(el) {{ return (el||document.getElementById('content')).clientHeight || 400; }}

function recColor(rec) {{
  return rec==='critical'?'#f87171': rec==='explore'?'#f59e0b':'#94a3b8';
}}
function badgeClass(rec) {{
  return rec==='critical'?'badge-critical':rec==='explore'?'badge-explore':'badge-skip';
}}

function showTT(ev, html) {{
  const tt = $('tooltip');
  tt.innerHTML = html;
  tt.style.display = 'block';
  const cw = W($('gw')), ch = H($('gw'));
  let tx = ev.clientX + 12, ty = ev.clientY - 8;
  if (tx + 230 > cw) tx = ev.clientX - 235;
  if (ty + 120 > ch) ty = ev.clientY - 120;
  tt.style.left = tx + 'px';
  tt.style.top  = ty + 'px';
}}
function hideTT() {{ $('tooltip').style.display = 'none'; }}

/* ════════════════════════════════════════
   TAB SWITCHING
════════════════════════════════════════ */
let _currentTab = 'venn';
function switchTab(name) {{
  if (_currentTab === name) return;
  const old = _currentTab;
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

  // Lazy render on first visit
  if      (name === 'heat'  ) renderHeatmap();
  else if (name === 'gap'   ) {{ renderRadar(); renderGapRows(); }}
  else if (name === 'hidden') renderHidden();
}}

/* ════════════════════════════════════════
   TAB 1 — VENN DIAGRAM
════════════════════════════════════════ */
function renderVenn() {{
  const svg  = $('venn-svg');
  svg.innerHTML = '';
  const vd = D.venn;
  if (!vd || !vd.covered) return;

  const w = W(svg.parentElement||$('pane-venn'));
  const h = H($('pane-venn')) - 4;
  svg.setAttribute('viewBox', `0 0 ${{w}} ${{h}}`);

  const cx = w / 2, cy = h / 2;
  const R  = Math.min(w, h) * 0.28;
  const overlap = R * 0.38;

  // Centers
  const cxL = cx - R + overlap * .55;
  const cxR = cx + R - overlap * .55;

  // Gradient defs
  const defs = ns('defs');
  [
    ['vg-teal',  '#2dd4bf', '#0d9488'],
    ['vg-amber', '#f59e0b', '#b45309'],
    ['vg-purple','#a78bfa', '#7c3aed'],
  ].forEach(([id,c1,c2]) => {{
    const rg = ns('radialGradient',{{id, cx:'50%',cy:'40%',r:'60%'}});
    const s1 = ns('stop',{{'offset':'0%','stop-color':c1,'stop-opacity':'.55'}});
    const s2 = ns('stop',{{'offset':'100%','stop-color':c2,'stop-opacity':'.2'}});
    rg.appendChild(s1); rg.appendChild(s2);
    defs.appendChild(rg);
  }});
  svg.appendChild(defs);

  // Background
  svg.appendChild(ns('rect',{{width:w,height:h,fill:'transparent'}}));

  // ── Left circle (Covered) ──
  const gL = ns('g',{{class:'venn-region'}});
  gL.appendChild(ns('circle',{{cx:cxL, cy, r:R, fill:'url(#vg-teal)', stroke:'#2dd4bf','stroke-width':'1.2',opacity:'.85'}}));
  gL.addEventListener('click', ()=> showVennPopup(vd.covered, 'left', cxL, cy-R));
  gL.addEventListener('mousemove', ev => showTT(ev, `<b style="color:#2dd4bf">Terlindungi</b><br>${{vd.covered.count}} topik (${{vd.covered.pct}}%)`));
  gL.addEventListener('mouseleave', hideTT);
  svg.appendChild(gL);

  // ── Right circle (Gap) ──
  const gR = ns('g',{{class:'venn-region'}});
  gR.appendChild(ns('circle',{{cx:cxR, cy, r:R, fill:'url(#vg-amber)', stroke:'#f59e0b','stroke-width':'1.2',opacity:'.85'}}));
  gR.addEventListener('click', ()=> showVennPopup(vd.gap, 'right', cxR, cy-R));
  gR.addEventListener('mousemove', ev => showTT(ev, `<b style="color:#f59e0b">Celah Kritis</b><br>${{vd.gap.count}} topik (${{vd.gap.pct}}%)`));
  gR.addEventListener('mouseleave', hideTT);
  svg.appendChild(gR);

  // ── Overlap glow (intersection visual) ──
  const overlapX = (cxL + cxR) / 2;
  const oCircle  = ns('circle',{{cx:overlapX, cy, r:overlap*1.1,
    fill:'url(#vg-purple)', opacity:'.65', 'pointer-events':'none'}});
  svg.appendChild(oCircle);

  // Overlap click region
  const gOv = ns('g',{{class:'venn-region'}});
  gOv.appendChild(ns('circle',{{cx:overlapX, cy, r:overlap*.9,
    fill:'transparent','pointer-events':'all'}}));
  gOv.addEventListener('click', ()=> showVennPopup(vd.overlap,'center',overlapX,cy-overlap*.9));
  gOv.addEventListener('mousemove', ev => showTT(ev, `<b style="color:#a78bfa">Sebagian</b><br>${{vd.overlap.count}} topik (${{vd.overlap.pct}}%)`));
  gOv.addEventListener('mouseleave', hideTT);
  svg.appendChild(gOv);

  // ── Count labels ──
  function addCountLabel(cx2, cy2, data, primary_color) {{
    const t1 = ns('text',{{x:cx2,y:cy2-10,class:'venn-count',fill:primary_color}});
    t1.textContent = data.count;
    svg.appendChild(t1);
    const t2 = ns('text',{{x:cx2,y:cy2+18,class:'venn-sub',fill:'rgba(255,255,255,.45)'}});
    t2.textContent = data.label;
    svg.appendChild(t2);
    const t3 = ns('text',{{x:cx2,y:cy2+30,class:'venn-sub',fill:primary_color,opacity:'.65'}});
    t3.textContent = data.pct + '% topik';
    svg.appendChild(t3);
  }}

  addCountLabel(cxL - R*.38, cy,       vd.covered, '#2dd4bf');
  addCountLabel(cxR + R*.38, cy,       vd.gap,     '#f59e0b');
  addCountLabel(overlapX,    cy - 8,   vd.overlap, '#a78bfa');

  // ── Axis labels ──
  const lblY = h - 22;
  [
    [cxL, '← SUDAH DIPELAJARI',    '#2dd4bf'],
    [cx,  'TRANSISI',               '#a78bfa'],
    [cxR, 'PERLU DIEKSPLORASI →',  '#f59e0b'],
  ].forEach(([x, lbl, clr]) => {{
    const t = ns('text',{{x,y:lblY,class:'venn-lbl',fill:clr,opacity:'.55'}});
    t.textContent = lbl;
    svg.appendChild(t);
  }});

  // ── Summary strip at top ──
  const sumY = 18;
  const sm = D.summary||{{}};
  const smTxt = ns('text',{{
    x:cx, y:sumY,
    'font-family':'Space Mono,monospace',
    'font-size':'9','fill':'rgba(45,212,191,.45)',
    'text-anchor':'middle','dominant-baseline':'central'
  }});
  smTxt.textContent = `${{sm.total_papers||0}} paper · ${{sm.total_gaps||0}} topik teranalisis · ${{sm.critical_gaps||0}} celah kritis`;
  svg.appendChild(smTxt);
}}

function showVennPopup(region, side, x, y) {{
  const p  = $('venn-popup');
  const kws = region.keywords || [];
  const clr = region.color   || '#2dd4bf';
  p.innerHTML = `
    <div class="vp-title" style="color:${{clr}}">${{region.label||''}} (${{region.count||0}} topik)</div>
    ${{kws.map(k=>`<span class="vp-kw" style="color:${{clr}};border-color:${{clr}}40">${{k}}</span>`).join('')}}
    ${{kws.length===0?'<span style="font-size:9px;color:#4a6588">Tidak ada topik di region ini</span>':''}}
  `;
  const pw = $('pane-venn');
  const ww = W(pw), hh = H(pw);
  let tx = x - 120, ty = y - 10;
  if (tx < 8)       tx = 8;
  if (tx + 248 > ww) tx = ww - 252;
  if (ty < 8)       ty = y + 20;
  if (ty + 150 > hh) ty = hh - 155;
  p.style.cssText = `display:block;left:${{tx}}px;top:${{ty}}px`;
  setTimeout(()=> document.addEventListener('click', closeVennPopup, {{once:true}}), 50);
}}
function closeVennPopup() {{ $('venn-popup').style.display='none'; }}

/* ════════════════════════════════════════
   TAB 2 — HEATMAP
════════════════════════════════════════ */
const HEAT_STATE = {{ sort:'gap', highlightRow:-1, highlightCol:-1 }};
const CELL_H = 20, CELL_W_MAX = 55, LABEL_W = 130, GAP_BAR_W = 40, PAD = 8;

function heatColor(v) {{
  // 0 = near white/dark, 1 = deep teal
  const alpha = 0.07 + v * 0.85;
  const r = Math.round(4  + v * 18);
  const g = Math.round(13 + v * 120);
  const b = Math.round(13 + v * 100);
  return `rgba(${{r}},${{g}},${{b}},${{alpha.toFixed(2)}})`;
}}
function gapBarColor(score) {{
  if (score >= 62) return '#f87171';
  if (score >= 38) return '#f59e0b';
  return '#94a3b8';
}}

function sortHeat(mode) {{
  HEAT_STATE.sort = mode;
  ['gap','coverage','alpha'].forEach(m => {{
    $('pc-'+m+'-sort').classList.toggle('on', m===mode);
  }});
  renderHeatmap();
}}

function renderHeatmap() {{
  const tm  = D.topic_matrix;
  const gs  = D.gap_scores;
  if (!tm || !tm.keywords || !tm.keywords.length) return;

  const svg   = $('heat-svg');
  const wrap  = $('heat-wrap');
  const wrapW = W(wrap);

  // Sort keyword indices
  let kwIdxs = tm.keywords.map((_,i)=>i);
  if (HEAT_STATE.sort === 'gap') {{
    const scoreMap = {{}};
    gs.forEach(g => {{ scoreMap[g.keyword] = g.gap_score; }});
    kwIdxs.sort((a,b) => (scoreMap[tm.keywords[b]]||0)-(scoreMap[tm.keywords[a]]||0));
  }} else if (HEAT_STATE.sort === 'coverage') {{
    kwIdxs.sort((a,b) => (tm.row_coverage[b]||0)-(tm.row_coverage[a]||0));
  }} else {{
    kwIdxs.sort((a,b) => tm.keywords[a].localeCompare(tm.keywords[b]));
  }}

  const nRows = kwIdxs.length;
  const nCols = tm.paper_shorts.length;
  const avail  = Math.max(100, wrapW - LABEL_W - GAP_BAR_W - PAD*3);
  const cellW  = Math.min(CELL_W_MAX, Math.floor(avail / nCols));

  const svgW = LABEL_W + nCols*cellW + GAP_BAR_W + PAD*3;
  const svgH = PAD*3 + 55 + nRows*CELL_H + 8;  // col labels at top

  svg.setAttribute('viewBox',`0 0 ${{svgW}} ${{svgH}}`);
  svg.setAttribute('width',  Math.max(svgW, wrapW));
  svg.setAttribute('height', svgH);
  svg.innerHTML = '';

  const defs = ns('defs');
  svg.appendChild(defs);
  svg.appendChild(ns('rect',{{width:svgW,height:svgH,fill:'rgba(4,13,13,.6)'}}));

  // ── Column labels (paper shorts) ──
  const colLblX = LABEL_W + PAD;
  tm.paper_shorts.forEach((title,ci) => {{
    const x   = colLblX + ci*cellW + cellW/2;
    const g   = ns('g',{{
      transform:`translate(${{x}},${{PAD+50}}) rotate(-55)`,
      cursor:'pointer'
    }});
    const t   = ns('text',{{
      x:0,y:0,class:'hm-clbl',
      'text-anchor':'end','dominant-baseline':'central'
    }});
    t.textContent = (title||'').substring(0,22);
    g.appendChild(t);
    g.addEventListener('click', ()=> highlightCol(ci));
    svg.appendChild(g);
  }});

  // ── "GAP" column header ──
  const gapX = colLblX + nCols*cellW + PAD;
  const ghdr = ns('text',{{
    x: gapX + GAP_BAR_W/2, y: PAD+10,
    class:'hm-gap-lbl',
    'text-anchor':'middle','dominant-baseline':'central'
  }});
  ghdr.textContent = 'GAP';
  svg.appendChild(ghdr);

  const topY = PAD*2 + 55;

  // ── Row loop ──
  kwIdxs.forEach((ki, rowIdx) => {{
    const kw   = tm.keywords[ki];
    const rowY = topY + rowIdx * CELL_H;

    // Row background highlight
    if (HEAT_STATE.highlightRow === ki) {{
      svg.appendChild(ns('rect',{{
        x:0,y:rowY,width:svgW,height:CELL_H,
        fill:'rgba(45,212,191,.07)','pointer-events':'none'
      }}));
    }}

    // Row label
    const rl = ns('text',{{
      x: LABEL_W - 6,
      y: rowY + CELL_H/2,
      class:'hm-rlbl',
    }});
    rl.textContent = kw.substring(0,20);
    rl.addEventListener('click',  ()=> highlightRow(ki));
    rl.addEventListener('mousemove', ev => showTT(ev,
      `<b style="color:#2dd4bf">${{kw}}</b><br>Coverage: ${{Math.round((tm.row_coverage[ki]||0)*100)}}%`));
    rl.addEventListener('mouseleave', hideTT);
    svg.appendChild(rl);

    // ── Cells ──
    for (let ci=0; ci<nCols; ci++) {{
      const val = (tm.scores[ki]||[])[ci] || 0;
      const cx2 = colLblX + ci*cellW;
      const isDimRow = HEAT_STATE.highlightRow !== -1 && HEAT_STATE.highlightRow !== ki;
      const isDimCol = HEAT_STATE.highlightCol !== -1 && HEAT_STATE.highlightCol !== ci;
      const isDim    = isDimRow || isDimCol;

      const cell = ns('rect',{{
        x:cx2+1, y:rowY+1,
        width:cellW-2, height:CELL_H-2, rx:2,
        fill: val>0 ? heatColor(val) : 'rgba(255,255,255,.02)',
        class:'hm-cell' + (isDim?' dim':'') + (val>0.5?' hi':''),
      }});
      cell.addEventListener('mousemove', ev => showTT(ev,
        `<b style="color:#2dd4bf">${{kw}}</b><br>` +
        `Paper: ${{(tm.paper_shorts[ci]||'').substring(0,30)}}<br>` +
        `Score: ${{(val*100).toFixed(0)}}%`
      ));
      cell.addEventListener('mouseleave', hideTT);
      svg.appendChild(cell);
    }}

    // ── Gap bar ──
    const gapEntry = D.gap_scores.find(g=>g.keyword===kw);
    const gapScore = gapEntry ? gapEntry.gap_score : 0;
    const barW     = Math.max(2, (gapScore/100) * (GAP_BAR_W-6));
    const barClr   = gapBarColor(gapScore);
    const barX     = colLblX + nCols*cellW + PAD;

    svg.appendChild(ns('rect',{{
      x:barX, y:rowY+3, width:GAP_BAR_W-4, height:CELL_H-6, rx:2,
      fill:'rgba(255,255,255,.03)'
    }}));
    if (barW > 0) {{
      svg.appendChild(ns('rect',{{
        x:barX, y:rowY+3, width:barW, height:CELL_H-6, rx:2,
        fill:barClr, opacity:'.75', class:'hm-gap-bar'
      }}));
    }}
    // Gap score number
    const gt = ns('text',{{
      x: barX + GAP_BAR_W - 6,
      y: rowY + CELL_H/2,
      class:'hm-gap-lbl',
      fill:barClr,
      'text-anchor':'end','dominant-baseline':'central'
    }});
    gt.textContent = gapScore;
    svg.appendChild(gt);
  }});

  // ── Col breadth bar at bottom ──
  const botY = topY + nRows*CELL_H + 4;
  for (let ci=0; ci<nCols; ci++) {{
    const bv  = tm.col_breadth[ci] || 0;
    const bW  = Math.max(1, cellW * bv * 0.9);
    const bX  = colLblX + ci*cellW + (cellW - bW)/2;
    svg.appendChild(ns('rect',{{
      x:bX, y:botY, width:bW, height:4, rx:2,
      fill:'rgba(45,212,191,.35)'
    }}));
  }}
}}

function highlightRow(ki) {{
  HEAT_STATE.highlightRow = HEAT_STATE.highlightRow===ki ? -1 : ki;
  HEAT_STATE.highlightCol = -1;
  renderHeatmap();
}}
function highlightCol(ci) {{
  HEAT_STATE.highlightCol = HEAT_STATE.highlightCol===ci ? -1 : ci;
  HEAT_STATE.highlightRow = -1;
  renderHeatmap();
}}

/* ════════════════════════════════════════
   TAB 3 — RADAR CHART
════════════════════════════════════════ */
function renderRadar() {{
  const svg  = $('radar-svg');
  svg.innerHTML = '';
  const rd   = D.radar;
  if (!rd || !rd.dimensions) return;

  const W2=115, H2=100, R=72, cx=W2, cy=H2;
  const N = rd.dimensions.length;

  // Grid rings
  [0.25,0.5,0.75,1].forEach(f => {{
    const pts = rd.dimensions.map((_,i)=>{{
      const a = (2*Math.PI*i/N) - Math.PI/2;
      return `${{cx+R*f*Math.cos(a)}},${{cy+R*f*Math.sin(a)}}`;
    }}).join(' ');
    svg.appendChild(ns('polygon',{{points:pts,fill:'none',
      stroke:'rgba(45,212,191,.1)','stroke-width':'1'}}));
  }});

  // Spokes
  rd.dimensions.forEach((_,i)=>{{
    const a = (2*Math.PI*i/N) - Math.PI/2;
    svg.appendChild(ns('line',{{
      x1:cx,y1:cy,
      x2:cx+R*Math.cos(a), y2:cy+R*Math.sin(a),
      stroke:'rgba(45,212,191,.12)','stroke-width':'1'
    }}));
  }});

  function makePolygon(vals, clr, opacity) {{
    const pts = vals.map((v,i)=>{{
      const a = (2*Math.PI*i/N) - Math.PI/2;
      const r = R * (v/100);
      return `${{cx+r*Math.cos(a)}},${{cy+r*Math.sin(a)}}`;
    }}).join(' ');
    const poly = ns('polygon',{{points:pts,
      fill:clr+'33', stroke:clr,
      'stroke-width':'1.8', opacity:opacity,
      'stroke-linejoin':'round'
    }});
    return poly;
  }}

  // Gap polygon (amber, behind)
  svg.appendChild(makePolygon(rd.gap, '#f59e0b', '.75'));
  // Coverage polygon (teal, front)
  svg.appendChild(makePolygon(rd.coverage, '#2dd4bf', '.85'));

  // Axis labels
  rd.dimensions.forEach((dim,i)=>{{
    const a  = (2*Math.PI*i/N) - Math.PI/2;
    const lr = R + 16;
    const lx = cx + lr*Math.cos(a);
    const ly = cy + lr*Math.sin(a);
    const cv = rd.coverage[i];

    const lt = ns('text',{{x:lx, y:ly-5, class:'rad-lbl'}});
    lt.textContent = dim;
    svg.appendChild(lt);

    const vt = ns('text',{{x:lx, y:ly+6, class:'rad-val'}});
    vt.textContent = cv + '%';
    svg.appendChild(vt);
  }});
}}

/* ════════════════════════════════════════
   TAB 3 — GAP ROWS
════════════════════════════════════════ */
let _gapFilter = 'all';
function filterGap(f) {{
  _gapFilter = f;
  ['all','crit','expl','skip'].forEach(k=>$('gf-'+k).className='gf-btn');
  if (f==='all')      {{ $('gf-all').classList.add('on'); }}
  else if(f==='critical') {{ $('gf-crit').classList.add('on'); }}
  else if(f==='explore')  {{ $('gf-expl').classList.add('on-ex'); }}
  else if(f==='skip')     {{ $('gf-skip').classList.add('on-sk'); }}
  renderGapRows();
}}

function renderGapRows() {{
  const cont = $('gap-rows');
  const gs   = D.gap_scores;
  if (!gs || !gs.length) {{
    cont.innerHTML='<div style="font-family:var(--code);font-size:9px;color:var(--text-lo);padding:20px">Tidak ada data gap score.</div>';
    return;
  }}
  const filtered = _gapFilter==='all' ? gs : gs.filter(g=>g.recommendation===_gapFilter);
  cont.innerHTML = filtered.map(g => {{
    const clr  = recColor(g.recommendation);
    const covW = Math.round(g.coverage*100);
    const covC = g.coverage > 0.6 ? '#4ade80' : g.coverage > 0.3 ? '#f59e0b' : '#f87171';
    const papers = (g.covering_papers||[]).slice(0,2).join('; ');
    return `
    <div class="gap-row" data-rec="${{g.recommendation}}">
      <div class="gr-header">
        <span class="gr-kw">${{g.keyword}}</span>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="gr-score" style="color:${{clr}}">${{g.gap_score}}</span>
          <span class="badge ${{badgeClass(g.recommendation)}}">${{g.recommendation.toUpperCase()}}</span>
        </div>
      </div>
      <div class="gr-meta">
        <span class="gr-cov">Cov: ${{covW}}%</span>
        <div class="gr-bar"><div class="gr-fill" style="width:${{covW}}%;background:${{covC}}"></div></div>
        <span class="gr-cov">${{g.covering_count||0}} paper</span>
      </div>
      ${{papers ? `<div class="gr-papers">📄 ${{papers}}</div>` : ''}}
    </div>`;
  }}).join('');
}}

/* ════════════════════════════════════════
   TAB 4 — HIDDEN FINDINGS
════════════════════════════════════════ */
function renderHidden() {{
  const scr = $('hidden-scroll');
  const hf  = D.hidden_findings;

  if (!hf || !hf.length) {{
    scr.innerHTML=`<div style="font-family:var(--code);font-size:9px;color:var(--text-lo);padding:20px">
      Tidak ada hidden findings yang terdeteksi.<br>
      Coba tambahkan lebih banyak paper dengan abstrak yang kaya konteks.
    </div>`;
  }} else {{
    scr.innerHTML = hf.map(hf => `
    <div class="hf-card ${{hf.recommendation}}">
      <div class="hf-concept">${{hf.concept}}</div>
      <div class="hf-meta">
        <span class="hf-type hf-type-${{hf.gap_type}}">${{hf.gap_type}}</span>
        <span class="badge ${{badgeClass(hf.recommendation)}}">${{hf.recommendation.toUpperCase()}}</span>
        <span class="hf-score">Gap: ${{hf.gap_score}}</span>
      </div>
      ${{hf.covering_papers&&hf.covering_papers.length
        ? `<div class="hf-papers">📄 ${{hf.covering_papers.join(' · ')}}</div>` : ''}}
      <div class="hf-search"
           onclick="navigator.clipboard.writeText('${{hf.recommended_search.replace(/'/g,'')}}').then(()=>this.textContent='✅ Tersalin!').catch(()=>{{}})">
        🔍 ${{hf.recommended_search.substring(0,40)}}
      </div>
    </div>
    `).join('');
  }}

  // Statement
  $('stmt-text').textContent = D.gap_statement || '—';
}}

function copyStatement() {{
  const txt = $('stmt-text').textContent;
  const btn = $('stmt-copy');
  navigator.clipboard.writeText(txt)
    .then(()=>{{
      btn.textContent = '✅ TERSALIN!';
      btn.classList.add('copied');
      setTimeout(()=>{{
        btn.textContent='⎘ SALIN KE CLIPBOARD';
        btn.classList.remove('copied');
      }}, 2200);
    }})
    .catch(()=>{{
      btn.textContent='⚠ Salin manual (Ctrl+A, Ctrl+C)';
    }});
}}

/* ════════════════════════════════════════
   TAB BADGE NUMBERS
════════════════════════════════════════ */
function updateBadges() {{
  const sm = D.summary || {{}};
  const vn = D.venn    || {{}};
  $('tn-venn').textContent   = (vn.gap||{{}}).count||'0';
  $('tn-heat').textContent   = (D.topic_matrix.keywords||[]).length||'0';
  $('tn-gap').textContent    = sm.critical_gaps||'0';
  $('tn-hidden').textContent = (D.hidden_findings||[]).length||'0';
}}

/* ════════════════════════════════════════
   INIT
════════════════════════════════════════ */
function init() {{
  updateBadges();
  renderVenn();
  // Other tabs render lazily on first click
}}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', init)
  : setTimeout(init, 60);

// Close venn popup on outside click is handled inline per popup open
</script>
</body>
</html>"""
