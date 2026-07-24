# -*- coding: utf-8 -*-
"""
Search-quality evaluation harness (PRD 5.6 / roadmap step 5).

Runs a labelled query set (eval/queryset.json) through each retrieval mode and
reports document-level Precision@k, MRR, and a *discrimination* metric — the gap
between the best relevant score and the best non-relevant score. The PRD's core
symptom is low discrimination ("유사도 변별력 부족"), so we measure it directly and
make before/after comparison reproducible.

Modes:
  bm25    - keyword only. Needs no embeddings, so it always runs (offline).
  vector  - dense cosine only. Needs an embedding backend (HF token or local).
  hybrid  - fused (uses HYBRID_ALPHA). Needs an embedding backend.

Usage:
    python scripts/evaluate.py                 # all modes it can run, k=5
    python scripts/evaluate.py --top 3
    python scripts/evaluate.py --modes bm25    # keyword-only, no backend needed
    python scripts/evaluate.py --alpha 0.5
"""

from __future__ import annotations

import sys
import json
import pathlib

from common import DATA_DIR, HYBRID_ALPHA, chunk_text, eprint
from extract import extract_text, SUPPORTED_EXTENSIONS
from retrieval import BM25, hybrid_scores, tokenize

_ROOT = pathlib.Path(__file__).resolve().parent.parent
QUERYSET = _ROOT / "eval" / "queryset.json"


def parse_args(argv):
    top_k, alpha, modes = 5, HYBRID_ALPHA, ["bm25", "vector", "hybrid"]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--top" and i + 1 < len(argv):
            top_k = int(argv[i + 1]); i += 2; continue
        if a == "--alpha" and i + 1 < len(argv):
            alpha = float(argv[i + 1]); i += 2; continue
        if a == "--modes" and i + 1 < len(argv):
            modes = [m.strip() for m in argv[i + 1].split(",")]; i += 2; continue
        i += 1
    return top_k, alpha, modes


def build_corpus():
    """Extract + chunk every supported document; return (chunk_texts, sources)."""
    texts, sources = [], []
    for path in sorted(DATA_DIR.rglob("*")):
        if not (path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS):
            continue
        try:
            raw = extract_text(str(path))
        except Exception as e:  # noqa: BLE001
            eprint(f"[skip] {path.name}: {e}")
            continue
        for chunk in chunk_text(raw):
            texts.append(chunk)
            sources.append(path.name)
    return texts, sources


def _doc_ranking(chunk_scores, sources, k):
    """Collapse chunk scores to best-per-document, return top-k (source, score)."""
    best: dict[str, float] = {}
    for src, sc in zip(sources, chunk_scores):
        if src not in best or sc > best[src]:
            best[src] = sc
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    return ranked[:k], ranked


def _metrics(queries, score_fn, sources, k):
    """score_fn(query) -> per-chunk score list. Returns aggregate metrics."""
    p_at_k, rr, gaps, hits = [], [], [], 0
    for q in queries:
        rel = set(q["relevant"])
        topk, full = _doc_ranking(score_fn(q["query"]), sources, k)
        top_sources = [s for s, _ in topk]
        n_rel = sum(1 for s in top_sources if s in rel)
        p_at_k.append(n_rel / k)
        # reciprocal rank of the first relevant document over the full ranking
        rank = next((i + 1 for i, (s, _) in enumerate(full) if s in rel), None)
        rr.append(1.0 / rank if rank else 0.0)
        hits += 1 if (top_sources and top_sources[0] in rel) else 0
        # discrimination: best relevant score minus best non-relevant score
        best_rel = max((sc for s, sc in full if s in rel), default=0.0)
        best_non = max((sc for s, sc in full if s not in rel), default=0.0)
        gaps.append(best_rel - best_non)
    n = len(queries)
    return {
        "P@k": sum(p_at_k) / n,
        "MRR": sum(rr) / n,
        "top1_acc": hits / n,
        "avg_score_gap": sum(gaps) / n,  # higher = better discrimination
    }


def main() -> int:
    top_k, alpha, modes = parse_args(sys.argv[1:])
    qs = json.loads(QUERYSET.read_text(encoding="utf-8"))["queries"]
    texts, sources = build_corpus()
    if not texts:
        eprint("No documents to evaluate. Put files in data/.")
        return 1
    eprint(f"Corpus: {len(texts)} chunks / {len(set(sources))} docs · "
           f"{len(qs)} queries · k={top_k}")

    bm25 = BM25([tokenize(t) for t in texts])

    # Dense scores need embeddings; degrade gracefully if no backend is configured.
    vectors = None
    if any(m in modes for m in ("vector", "hybrid")):
        try:
            import numpy as np
            from common import embed_texts
            vectors = embed_texts(texts, is_query=False)
            _np = np
        except Exception as e:  # noqa: BLE001
            eprint(f"[info] vector/hybrid skipped — no embedding backend ({e}).")
            eprint("       Set up .env (HF token or EMBEDDING_BACKEND=local) to enable.")
            modes = [m for m in modes if m == "bm25"]

    def scorer(mode):
        if mode == "bm25":
            return lambda q: bm25.scores(q)
        def dense(q):
            qv = embed_texts([q], is_query=True)[0]
            return (vectors @ qv).tolist()
        if mode == "vector":
            return dense
        if mode == "hybrid":
            return lambda q: hybrid_scores(dense(q), bm25.scores(q), alpha)
        raise ValueError(mode)

    rows = []
    for mode in modes:
        m = _metrics(qs, scorer(mode), sources, top_k)
        label = mode + (f"(α={alpha:g})" if mode == "hybrid" else "")
        rows.append((label, m))

    print(f"\n{'mode':<14}{'P@'+str(top_k):>8}{'MRR':>8}{'top1':>8}{'score_gap':>12}")
    print("-" * 50)
    for label, m in rows:
        print(f"{label:<14}{m['P@k']:>8.3f}{m['MRR']:>8.3f}"
              f"{m['top1_acc']:>8.3f}{m['avg_score_gap']:>12.4f}")
    print("\nscore_gap = 관련 문서 최고점 − 비관련 문서 최고점 (클수록 변별력 좋음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
