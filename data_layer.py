"""
data_layer.py  —  v2 (multi-source)
=====================================
SUMBER DATA (urutan prioritas):
  1. arXiv          — gratis, tanpa key, Python library, sangat stabil
  2. Europe PMC     — gratis, REST API, terbaik untuk biomedis/life science
  3. Semantic Scholar — bagus tapi sering rate-limit tanpa key
  4. CrossRef       — last resort, data sitasi terbatas

ARSITEKTUR:
  - Tiap sumber punya fungsi fetch + parse sendiri
  - search_papers() mencoba sumber secara paralel (arXiv + EuropePMC)
    dan menggabungkan hasilnya, lalu fallback jika keduanya kosong
  - Semua sumber dinormalisasi ke format dict yang sama
  - Deduplikasi berdasarkan judul (fuzzy lowercase match)

FORMAT STANDAR OUTPUT:
  {
    "title":        str,
    "authors":      str,
    "year":         str,
    "citations":    int,
    "impact_level": "high" | "medium" | "low",
    "impact_label": str,
    "venue":        str,
    "link":         str,
    "abstract":     str,
    "source":       str,   # nama sumber data
    "doi":          str,   # opsional, "" jika tidak ada
  }

ATURAN:
  - Fungsi @st.cache_data TIDAK BOLEH memanggil st.error() / st.warning()
  - Semua error di-raise sebagai Exception — UI layer yang menangkap
"""

import re
import time
import threading
import requests
import streamlit as st

try:
    import arxiv as arxiv_lib
    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False


# ─────────────────────────────────────────────────────
# KONSTANTA
# ─────────────────────────────────────────────────────

REQUEST_HEADERS = {
    "User-Agent": "AIResearchAssistant/2.0 (educational; contact: research@example.com)",
    "Accept":     "application/json",
}

def _impact(citations: int) -> tuple[str, str]:
    """Return (impact_level, impact_label) dari jumlah sitasi."""
    if citations > 100:
        return "high",   "Sangat Berpengaruh"
    if citations > 20:
        return "medium", "Cukup Relevan"
    return "low",    "Baru / Niche"


# ─────────────────────────────────────────────────────
# HTTP HELPER
# ─────────────────────────────────────────────────────

def _raw_get(url: str, params: dict, max_retries: int = 3,
             extra_headers: dict | None = None) -> dict:
    """
    HTTP GET dengan retry + exponential backoff.
    RAISE exception — tidak pernah return None diam-diam.
    """
    headers = {**REQUEST_HEADERS, **(extra_headers or {})}
    last_error = None

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params,
                                headers=headers, timeout=15)

            if "last_api_status" in st.session_state:
                st.session_state.last_api_status = resp.status_code

            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                last_error = f"Rate limited (429), tunggu {wait}s, retry {attempt+1}"
                continue

            if resp.status_code == 403:
                raise PermissionError(f"403 Forbidden: {url}")

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.Timeout:
            last_error = f"Timeout attempt {attempt+1}"
            if attempt < max_retries - 1:
                time.sleep(1.5)
            continue

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Koneksi gagal: {e}")

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Request error: {e}")

    raise TimeoutError(f"Semua {max_retries} percobaan gagal. Terakhir: {last_error}")


# ─────────────────────────────────────────────────────
# SOURCE 1: arXiv  (via Python library)
# ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _search_arxiv(topic: str, limit: int) -> list[dict]:
    """
    Cari paper via arXiv Python library.
    arXiv tidak menyimpan citation count → default 0, tandai sebagai preprint.

    Keunggulan arXiv:
      - Sangat stabil, tidak ada rate limit ketat
      - Bagus untuk CS, ML, Fisika, Matematika, Quantitative Biology
      - Full text tersedia gratis

    RAISE exception jika library tidak tersedia atau query gagal.
    """
    if not ARXIV_AVAILABLE:
        raise ImportError(
            "Library 'arxiv' tidak ditemukan. "
            "Install dengan: pip install arxiv"
        )

    client = arxiv_lib.Client(
        page_size=limit,
        delay_seconds=1.0,
        num_retries=3,
    )

    search = arxiv_lib.Search(
        query=topic,
        max_results=limit,
        sort_by=arxiv_lib.SortCriterion.Relevance,
    )

    results = []
    for r in client.results(search):
        authors = r.authors
        if not authors:
            authors_str = "Unknown"
        elif len(authors) <= 3:
            authors_str = ", ".join(a.name for a in authors)
        else:
            authors_str = f"{authors[0].name} et al. (+{len(authors)-1})"

        year = str(r.published.year) if r.published else "?"

        # arXiv ID sebagai identifier unik
        arxiv_id = r.entry_id.split("/abs/")[-1]
        link = r.entry_id  # URL canonical arXiv

        # DOI jika tersedia
        doi = r.doi or ""

        # Venue = kategori arXiv primer
        venue = r.primary_category or "arXiv preprint"

        level, label = _impact(0)  # arXiv tidak punya citation count

        results.append({
            "title":        r.title or "No Title",
            "authors":      authors_str,
            "year":         year,
            "citations":    0,
            "impact_level": level,
            "impact_label": "Preprint (arXiv)",
            "venue":        venue,
            "link":         link,
            "abstract":     r.summary or "Abstrak tidak tersedia.",
            "source":       "arXiv",
            "doi":          doi,
            "_arxiv_id":    arxiv_id,
        })

    return results


# ─────────────────────────────────────────────────────
# SOURCE 2: Europe PMC  (via REST API)
# ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _search_europepmc(topic: str, limit: int) -> list[dict]:
    """
    Cari paper via Europe PMC REST API.
    Tidak perlu API key. Sangat bagus untuk:
      - Biomedis, Life Science, Farmasi, Kedokteran
      - Paper yang sudah peer-reviewed & terindeks PubMed/PMC

    Dokumentasi: https://europepmc.org/RestfulWebService
    """
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query":      topic,
        "format":     "json",
        "pageSize":   limit,
        "resultType": "core",          # 'core' = dengan abstract
        "sort":       "CITED desc",    # urutkan dari paling banyak dikutip
    }
    data = _raw_get(url, params)

    results_raw = (
        data.get("resultList", {}).get("result", [])
    )
    if not results_raw:
        return []

    results = []
    for item in results_raw:
        title = item.get("title", "").rstrip(".")
        if not title:
            continue

        # Authors
        author_list = item.get("authorList", {}).get("author", [])
        if not author_list:
            authors_str = "Unknown"
        elif len(author_list) <= 3:
            authors_str = ", ".join(
                f"{a.get('firstName','')} {a.get('lastName','')}".strip()
                for a in author_list
            )
        else:
            first = author_list[0]
            name0 = f"{first.get('firstName','')} {first.get('lastName','')}".strip()
            authors_str = f"{name0} et al. (+{len(author_list)-1})"

        year = str(item.get("pubYear", "?"))
        citations = int(item.get("citedByCount", 0) or 0)
        level, label = _impact(citations)

        journal = item.get("journalTitle", "") or item.get("bookOrReportDetails", {}).get("publisher", "")
        venue   = journal or "Europe PMC"

        # Link: utamakan DOI, fallback ke PMC/PubMed
        doi = item.get("doi", "")
        pmid = item.get("pmid", "")
        pmcid = item.get("pmcid", "")
        if doi:
            link = f"https://doi.org/{doi}"
        elif pmcid:
            link = f"https://europepmc.org/article/PMC/{pmcid}"
        elif pmid:
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
        else:
            link = f"https://europepmc.org/search?query={title[:50]}"

        abstract = item.get("abstractText", "Abstrak tidak tersedia.")
        abstract = re.sub(r"<[^>]+>", "", abstract)  # strip HTML tags

        results.append({
            "title":        title,
            "authors":      authors_str,
            "year":         year,
            "citations":    citations,
            "impact_level": level,
            "impact_label": label,
            "venue":        venue,
            "link":         link,
            "abstract":     abstract,
            "source":       "Europe PMC",
            "doi":          doi,
        })

    return sorted(results, key=lambda x: x["citations"], reverse=True)


# ─────────────────────────────────────────────────────
# SOURCE 3: Semantic Scholar  (dengan API key opsional)
# ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _search_semantic_scholar(topic: str, limit: int) -> tuple[list, int]:
    """
    Cari paper via Semantic Scholar Graph API.

    API key opsional tapi sangat dianjurkan — tanpa key sering kena 429.
    Daftarkan key gratis di: https://www.semanticscholar.org/product/api
    Tambahkan ke secrets.toml: SEMANTIC_SCHOLAR_KEY = "..."
    """
    extra_headers = {}
    try:
        key = st.secrets.get("SEMANTIC_SCHOLAR_KEY", "")
        if key:
            extra_headers["x-api-key"] = key
    except Exception:
        pass

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query":  topic,
        "limit":  limit,
        "fields": "title,authors,year,citationCount,abstract,url,venue",
    }
    data = _raw_get(url, params, extra_headers=extra_headers)
    return data.get("data", []), data.get("total", 0)


def _parse_semantic(raw: list) -> list[dict]:
    results = []
    for item in raw:
        citations = item.get("citationCount") or 0
        level, label = _impact(citations)

        authors_raw = item.get("authors", [])
        if not authors_raw:
            authors_str = "Unknown"
        elif len(authors_raw) <= 3:
            authors_str = ", ".join(a["name"] for a in authors_raw)
        else:
            authors_str = f"{authors_raw[0]['name']} et al. (+{len(authors_raw)-1})"

        paper_id = item.get("paperId", "")
        link = item.get("url") or (
            f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else "#"
        )

        results.append({
            "title":        item.get("title") or "No Title",
            "authors":      authors_str,
            "year":         str(item.get("year") or "?"),
            "citations":    citations,
            "impact_level": level,
            "impact_label": label,
            "venue":        item.get("venue") or "Tidak diketahui",
            "link":         link,
            "abstract":     item.get("abstract") or "Abstrak tidak tersedia.",
            "source":       "Semantic Scholar",
            "doi":          "",
        })
    return sorted(results, key=lambda x: x["citations"], reverse=True)


# ─────────────────────────────────────────────────────
# SOURCE 4: CrossRef  (last resort)
# ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _search_crossref(topic: str, limit: int) -> list[dict]:
    url = "https://api.crossref.org/works"
    params = {
        "query":  topic,
        "rows":   limit,
        "select": "title,author,published,is-referenced-by-count,abstract,URL,container-title,DOI",
    }
    data = _raw_get(url, params)
    return data.get("message", {}).get("items", [])


def _parse_crossref(raw: list) -> list[dict]:
    results = []
    for item in raw:
        title_list = item.get("title", [])
        title = title_list[0] if title_list else "No Title"

        authors_raw = item.get("author", [])
        if not authors_raw:
            authors_str = "Unknown"
        else:
            names = [
                f"{a.get('given','').strip()} {a.get('family','').strip()}".strip()
                for a in authors_raw[:3]
            ]
            authors_str = ", ".join(names)
            if len(authors_raw) > 3:
                authors_str += f" et al. (+{len(authors_raw)-3})"

        pub   = item.get("published", {}).get("date-parts", [[None]])
        year  = str(pub[0][0]) if pub[0][0] else "?"
        cits  = item.get("is-referenced-by-count") or 0
        venues = item.get("container-title", [])
        venue  = venues[0] if venues else "Tidak diketahui"
        doi    = item.get("DOI", "")
        link   = item.get("URL") or (f"https://doi.org/{doi}" if doi else "#")

        abstract = item.get("abstract", "Abstrak tidak tersedia.")
        abstract = re.sub(r"<[^>]+>", "", abstract)

        level, label = _impact(cits)

        results.append({
            "title":        title,
            "authors":      authors_str,
            "year":         year,
            "citations":    cits,
            "impact_level": level,
            "impact_label": label,
            "venue":        venue,
            "link":         link,
            "abstract":     abstract,
            "source":       "CrossRef",
            "doi":          doi,
        })
    return sorted(results, key=lambda x: x["citations"], reverse=True)


# ─────────────────────────────────────────────────────
# DEDUPLIKASI
# ─────────────────────────────────────────────────────

def _deduplicate(papers: list[dict]) -> list[dict]:
    """
    Hapus duplikat berdasarkan kesamaan judul.
    Prioritas: paper dengan citation count lebih tinggi dipertahankan.
    Matching: lowercase + hapus karakter non-alfanumerik.
    """
    seen: dict[str, dict] = {}
    for p in papers:
        key = re.sub(r"[^a-z0-9]", "", p["title"].lower())[:80]
        if key not in seen:
            seen[key] = p
        else:
            # Pertahankan yang citationnya lebih tinggi
            if p["citations"] > seen[key]["citations"]:
                seen[key] = p
    return list(seen.values())


# ─────────────────────────────────────────────────────
# FUNGSI PUBLIK UTAMA
# ─────────────────────────────────────────────────────

def search_papers(
    topic: str,
    limit: int = 8,
    sources: list[str] | None = None,
    debug: bool = False,
) -> tuple[list[dict] | None, str]:
    """
    Cari paper dari multiple sumber, merge, dan deduplikasi.

    Strategi:
      - arXiv + Europe PMC dicoba PARALEL (Thread) → merge hasilnya
      - Jika keduanya kosong → coba Semantic Scholar
      - Jika masih kosong  → coba CrossRef
      - Jika semuanya gagal → return None

    Args:
      topic:   query pencarian (sebaiknya bahasa Inggris)
      limit:   jumlah paper per sumber (total bisa 2× limit setelah merge)
      sources: daftar sumber yang diaktifkan, default semua
               ["arxiv", "europepmc", "semantic", "crossref"]
      debug:   jika True, log lebih detail

    Returns:
      (papers, debug_log)
      papers = None jika semua sumber gagal
    """
    if sources is None:
        sources = ["arxiv", "europepmc", "semantic", "crossref"]

    log   = []
    all_papers: list[dict] = []

    # ══════════════════════════════════════
    # TAHAP 1: arXiv + Europe PMC paralel
    # ══════════════════════════════════════
    arxiv_results: list[dict]  = []
    epmc_results:  list[dict]  = []
    arxiv_err  = ""
    epmc_err   = ""

    def _try_arxiv():
        nonlocal arxiv_results, arxiv_err
        try:
            arxiv_results = _search_arxiv(topic, limit)
        except Exception as e:
            arxiv_err = f"{type(e).__name__}: {e}"

    def _try_epmc():
        nonlocal epmc_results, epmc_err
        try:
            epmc_results = _search_europepmc(topic, limit)
        except Exception as e:
            epmc_err = f"{type(e).__name__}: {e}"

    threads = []
    if "arxiv" in sources and ARXIV_AVAILABLE:
        t1 = threading.Thread(target=_try_arxiv)
        t1.start()
        threads.append(("arXiv", t1))
    elif "arxiv" in sources and not ARXIV_AVAILABLE:
        log.append("[arXiv] ⚠️  Library tidak tersedia — install: pip install arxiv")

    if "europepmc" in sources:
        t2 = threading.Thread(target=_try_epmc)
        t2.start()
        threads.append(("Europe PMC", t2))

    for name, t in threads:
        t.join(timeout=20)

    # Log hasil paralel
    if "arxiv" in sources and ARXIV_AVAILABLE:
        if arxiv_err:
            log.append(f"[arXiv]      ❌ {arxiv_err}")
        else:
            log.append(f"[arXiv]      ✅ {len(arxiv_results)} paper ditemukan")
        all_papers.extend(arxiv_results)

    if "europepmc" in sources:
        if epmc_err:
            log.append(f"[Europe PMC] ❌ {epmc_err}")
        else:
            log.append(f"[Europe PMC] ✅ {len(epmc_results)} paper ditemukan")
        all_papers.extend(epmc_results)

    # Jika tahap 1 sudah cukup, skip ke merge
    if all_papers:
        log.append(f"\n→ Tahap 1 berhasil: {len(all_papers)} paper sebelum dedup")
    else:
        log.append("\n→ Tahap 1 kosong, mencoba Semantic Scholar...")

        # ══════════════════════════════════════
        # TAHAP 2: Semantic Scholar
        # ══════════════════════════════════════
        if "semantic" in sources:
            try:
                raw, total = _search_semantic_scholar(topic, limit)
                log.append(f"[Semantic Scholar] ✅ {len(raw)}/{total} paper")
                all_papers.extend(_parse_semantic(raw))
            except Exception as e:
                log.append(f"[Semantic Scholar] ❌ {type(e).__name__}: {e}")
                log.append("  → Tip: Daftarkan API key gratis di semanticscholar.org/product/api")
                log.append("    Lalu tambahkan ke secrets.toml: SEMANTIC_SCHOLAR_KEY = '...'")

        # ══════════════════════════════════════
        # TAHAP 3: CrossRef (last resort)
        # ══════════════════════════════════════
        if not all_papers and "crossref" in sources:
            log.append("\n→ Mencoba CrossRef sebagai last resort...")
            try:
                raw_cr = _search_crossref(topic, limit)
                log.append(f"[CrossRef] ✅ {len(raw_cr)} item")
                all_papers.extend(_parse_crossref(raw_cr))
            except Exception as e:
                log.append(f"[CrossRef] ❌ {type(e).__name__}: {e}")

    if not all_papers:
        log.append(f"\n❌ Semua sumber gagal untuk topik: '{topic}'")
        log.append("   Saran: gunakan kata kunci bahasa Inggris yang lebih umum")
        return None, "\n".join(log)

    # ══════════════════════════════════════
    # MERGE, DEDUP, SORT
    # ══════════════════════════════════════
    merged = _deduplicate(all_papers)

    # Sort: utamakan yang ada abstrak + punya sitasi tinggi
    merged.sort(key=lambda p: (
        0 if p["abstract"] == "Abstrak tidak tersedia." else 1,
        p["citations"]
    ), reverse=True)

    # Ambil top N
    final = merged[:limit * 2]  # bisa lebih dari limit karena multi-source

    log.append(f"\n✅ Final: {len(final)} paper unik dari {len(all_papers)} total")
    log.append("   Sumber: " + ", ".join(sorted({p['source'] for p in final})))

    return final, "\n".join(log)
