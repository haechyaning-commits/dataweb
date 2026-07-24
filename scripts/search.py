# -*- coding: utf-8 -*-
"""
Search the index built by embed.py.

Hybrid ranking: dense cosine similarity (vectors are L2-normalised, so
cosine == dot product) fused with a BM25 keyword score. The keyword component
recovers exact-token matches (법 조항·기관명·금액) that pure embeddings miss.
Set HYBRID_ALPHA=1.0 in .env to fall back to pure vector search.

A rerank hook lives just before results are formatted: to add a cross-encoder
reranker later (DIAGNOSIS D), re-order `order` there using the chunk text in
`metas[i]["text"]`.

Usage:
    python scripts/search.py "임산부 시간외근로"
    python scripts/search.py --top 3 "전용통신망 수의계약"
    python scripts/search.py --json "방만경영 예산통제"
    python scripts/search.py --alpha 1.0 "방만경영"   # pure vector, override .env
"""

from __future__ import annotations

import sys
import json

import numpy as np

from common import INDEX_PATH, EMBEDDING_MODEL, HYBRID_ALPHA, embed_texts, eprint
from retrieval import BM25, hybrid_scores, tokenize


def load_index():
    if not INDEX_PATH.exists():
        eprint(f"No index found at {INDEX_PATH}. Run embedding.bat first.")
        raise SystemExit(1)
    data = np.load(INDEX_PATH, allow_pickle=True)
    vectors = data["vectors"].astype(np.float32)
    metas = json.loads(str(data["metas"]))
    model = str(data["model"])
    if model != EMBEDDING_MODEL:
        eprint(f"[warn] index was built with '{model}' but EMBEDDING_MODEL is "
               f"'{EMBEDDING_MODEL}'. Re-run embedding.bat to stay consistent.")
    return vectors, metas


def parse_args(argv: list[str]):
    top_k = 5
    as_json = False
    alpha = HYBRID_ALPHA
    query_parts: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--top", "-k") and i + 1 < len(argv):
            top_k = int(argv[i + 1]); i += 2; continue
        if a == "--alpha" and i + 1 < len(argv):
            alpha = float(argv[i + 1]); i += 2; continue
        if a == "--json":
            as_json = True; i += 1; continue
        query_parts.append(a); i += 1
    return " ".join(query_parts).strip(), top_k, as_json, alpha


def main() -> int:
    query, top_k, as_json, alpha = parse_args(sys.argv[1:])
    if not query:
        eprint('Usage: search.bat "your question"  [--top N] [--alpha 0..1] [--json]')
        return 1

    vectors, metas = load_index()
    qvec = embed_texts([query], is_query=True)[0]
    dense = (vectors @ qvec).tolist()  # cosine similarity (both normalised)

    if alpha >= 1.0:
        final = dense  # pure vector search
    else:
        # Older indexes may predate the stored chunk text; fall back to preview.
        corpus = [m.get("text") or m.get("preview", "") for m in metas]
        bm25 = BM25([tokenize(t) for t in corpus])
        final = hybrid_scores(dense, bm25.scores(query), alpha)

    order = list(np.argsort(-np.asarray(final))[:top_k])

    # --- rerank hook: reorder `order` here with a cross-encoder if desired ---

    results = [{
        "rank": rank + 1,
        "score": round(float(final[i]), 4),
        "cosine": round(float(dense[i]), 4),
        "source": metas[i]["source"],
        "chunk": metas[i]["chunk"],
        "preview": metas[i]["preview"],
    } for rank, i in enumerate(order)]

    if as_json:
        print(json.dumps({"query": query, "results": results}, ensure_ascii=False, indent=2))
        return 0

    mode = "vector" if alpha >= 1.0 else f"hybrid α={alpha:g}"
    print(f"\n🔎 Query: {query}  ({mode})\n" + "=" * 70)
    for r in results:
        print(f"[{r['rank']}] score={r['score']:.4f} (cos {r['cosine']:.4f})  "
              f"{r['source']}  (chunk {r['chunk']})")
        print(f"    {r['preview']}")
        print("-" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
