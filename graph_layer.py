"""
graph_layer.py
==============
Tanggung jawab:
  - Fetch referensi & sitasi tiap paper dari Semantic Scholar
  - Bangun directed graph (NetworkX) dari relasi antar paper
  - Render graph menjadi HTML interaktif (PyVis)
  - Hitung statistik graph: paper sentral, cluster, gap

Dependensi tambahan (tambahkan ke requirements.txt):
  networkx
  pyvis

Cara import di app.py:
  from graph_layer import build_knowledge_graph, render_graph, graph_stats
"""

import math
import streamlit as st
import networkx as nx
from pyvis.network import Network
from data_layer import _raw_get


# ─────────────────────────────────────────────────────
# 1. FETCH REFERENSI
# ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_paper_references(paper_id: str) -> dict:
    """
    Ambil referensi (paper yang di-cite) dan sitasi (paper yang mengutip)
    dari satu paper via Semantic Scholar.

    Returns dict dengan key 'references' dan 'citations'.
    Mengembalikan dict kosong jika gagal — tidak raise exception.
    """
    if not paper_id or paper_id == "#":
        return {"references": [], "citations": []}

    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    params = {
        "fields": (
            "references.paperId,references.title,"
            "references.year,references.citationCount,"
            "citations.paperId,citations.title,"
            "citations.citationCount"
        )
    }
    try:
        data = _raw_get(url, params)
        return {
            "references": data.get("references", []),
            "citations":  data.get("citations",  [])
        }
    except Exception:
        return {"references": [], "citations": []}


def _extract_paper_id(paper: dict) -> str:
    """
    Ekstrak paper ID dari URL Semantic Scholar.
    Contoh: https://www.semanticscholar.org/paper/abc123 → 'abc123'
    """
    link = paper.get("link", "")
    if "semanticscholar.org/paper/" in link:
        return link.split("/paper/")[-1].strip("/")
    return ""


# ─────────────────────────────────────────────────────
# 2. BANGUN GRAPH
# ─────────────────────────────────────────────────────

def build_knowledge_graph(papers: list[dict]) -> nx.DiGraph:
    """
    Bangun directed graph dari daftar paper hasil pencarian.

    Struktur:
      Node  = satu paper — menyimpan title, year, citations, source
      Edge  = relasi sitasi (A → B berarti A mengutip B)
      Bobot = log(citationCount + 1) untuk menghindari dominasi outlier

    Proses:
      1. Tambah semua paper utama sebagai node
      2. Fetch referensi tiap paper dari Semantic Scholar
      3. Tambah edge jika paper yang direferensikan ada di node set
      4. Tambah juga paper tetangga penting (meski tidak ada di set awal)
    """
    G = nx.DiGraph()

    # ── Tambah semua paper utama sebagai node
    paper_id_map = {}
    for p in papers:
        pid = _extract_paper_id(p)
        if not pid:
            pid = p["title"][:40]

        paper_id_map[pid] = p
        node_size = max(10, min(55, math.log(p["citations"] + 1) * 9))

        G.add_node(pid,
                   label=p["title"][:45],
                   year=p["year"],
                   citations=p["citations"],
                   source=p["source"],
                   size=node_size,
                   group="main")

    known_ids = set(G.nodes())

    # ── Fetch referensi dan bangun edge
    for pid in list(known_ids):
        refs_data = fetch_paper_references(pid)

        for ref in refs_data.get("references", []):
            ref_id = ref.get("paperId", "")
            if not ref_id:
                continue

            # Jika ref ada di node set → tambah edge langsung
            if ref_id in known_ids:
                weight = math.log(ref.get("citationCount", 0) + 1)
                G.add_edge(pid, ref_id,
                           weight=max(0.5, weight),
                           relation="cites")

            # Jika ref sangat banyak dikutip (>50) → tambah sebagai node tetangga
            elif ref.get("citationCount", 0) > 50 and ref.get("title"):
                neighbor_size = max(8, min(30,
                    math.log(ref.get("citationCount", 0) + 1) * 6))
                G.add_node(ref_id,
                           label=ref["title"][:40],
                           year=str(ref.get("year", "?")),
                           citations=ref.get("citationCount", 0),
                           source="neighbor",
                           size=neighbor_size,
                           group="neighbor")
                G.add_edge(pid, ref_id,
                           weight=math.log(ref.get("citationCount", 0) + 1),
                           relation="cites")

    return G


# ─────────────────────────────────────────────────────
# 3. STATISTIK GRAPH
# ─────────────────────────────────────────────────────

def graph_stats(G: nx.DiGraph) -> dict:
    """
    Hitung statistik penting dari graph:
      - paper paling banyak dikutip (in-degree tinggi)
      - paper paling banyak mengutip (out-degree tinggi)
      - paper "jembatan" — menghubungkan dua cluster berbeda
      - jumlah komponen (cluster terpisah)
    """
    if G.number_of_nodes() == 0:
        return {}

    # Paper paling dikutip dalam graph ini
    most_cited = sorted(G.nodes(data=True),
                        key=lambda x: x[1].get("citations", 0),
                        reverse=True)

    # Paper paling banyak meng-cite (out-degree)
    most_citing = sorted(G.nodes(),
                         key=lambda n: G.out_degree(n),
                         reverse=True)

    # Paper paling banyak incoming edges (dalam konteks graph ini)
    most_referenced = sorted(G.nodes(),
                              key=lambda n: G.in_degree(n),
                              reverse=True)

    # Coba hitung betweenness centrality untuk temukan "jembatan"
    try:
        undirected = G.to_undirected()
        betweenness = nx.betweenness_centrality(undirected, k=min(10, G.number_of_nodes()))
        bridge_node = max(betweenness, key=betweenness.get)
        bridge_label = G.nodes[bridge_node].get("label", bridge_node[:30])
    except Exception:
        bridge_label = "-"

    # Jumlah komponen terkoneksi
    n_components = nx.number_weakly_connected_components(G)

    return {
        "nodes":          G.number_of_nodes(),
        "edges":          G.number_of_edges(),
        "components":     n_components,
        "most_cited":     most_cited[0][1].get("label", "?") if most_cited else "-",
        "most_citing":    G.nodes[most_citing[0]].get("label", "?") if most_citing else "-",
        "bridge_paper":   bridge_label,
        "density":        round(nx.density(G), 4),
    }


# ─────────────────────────────────────────────────────
# 4. RENDER GRAPH
# ─────────────────────────────────────────────────────

def render_graph(G: nx.DiGraph, height: int = 520) -> str:
    """
    Render directed graph menjadi HTML interaktif menggunakan PyVis.
    
    Warna node:
      Ungu  (#7F77DD) = sangat berpengaruh (> 100 sitasi)
      Hijau (#1D9E75) = cukup berpengaruh (20-100 sitasi)
      Abu   (#B4B2A9) = baru/niche (< 20 sitasi)
      Oranye (#EF9F27)= paper tetangga (bukan dari hasil pencarian)

    Ukuran node = log(citationCount) — besar = banyak dikutip.
    Tebal edge  = bobot sitasi.

    Returns:
      HTML string — tampilkan dengan st.components.v1.html()
    """
    net = Network(
        height=f"{height}px",
        width="100%",
        directed=True,
        bgcolor="transparent",
        font_color="#444441"
    )

    # ── Tambah node
    for node_id, data in G.nodes(data=True):
        citations = data.get("citations", 0)
        group     = data.get("group", "main")
        size      = data.get("size", 15)

        if group == "neighbor":
            color = "#EF9F27"
        elif citations > 100:
            color = "#7F77DD"
        elif citations > 20:
            color = "#1D9E75"
        else:
            color = "#B4B2A9"

        tooltip = (
            f"<b>{data.get('label', node_id[:40])}</b><br>"
            f"Tahun: {data.get('year', '?')}<br>"
            f"Sitasi: {citations:,}<br>"
            f"Sumber: {data.get('source', '?')}"
        )

        net.add_node(
            node_id,
            label=data.get("label", node_id[:35]),
            size=size,
            color=color,
            title=tooltip,
            font={"size": 11, "color": "#444441"}
        )

    # ── Tambah edge
    for u, v, data in G.edges(data=True):
        weight = data.get("weight", 1.0)
        net.add_edge(
            u, v,
            width=max(0.5, weight * 0.6),
            color={"color": "#AFA9EC", "opacity": 0.6},
            arrows="to",
            smooth={"type": "curvedCW", "roundness": 0.2}
        )

    # ── Physics: forceAtlas2 agar cluster terlihat natural
    net.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 130,
          "springConstant": 0.06,
          "damping": 0.4,
          "avoidOverlap": 0.5
        },
        "solver": "forceAtlas2Based",
        "stabilization": {
          "enabled": true,
          "iterations": 200,
          "updateInterval": 25
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 80,
        "navigationButtons": false,
        "keyboard": false
      },
      "edges": {
        "smooth": { "type": "curvedCW", "roundness": 0.15 }
      }
    }
    """)

    return net.generate_html()
