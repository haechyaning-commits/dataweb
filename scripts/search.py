# -*- coding: utf-8 -*-
"""
Search the index built by embed.py.

Embeds the query with the same model, then ranks chunks by cosine similarity
(vectors are L2-normalised, so cosine == dot product).

Usage:
    python scripts/search.py "임산부 시간외근로"
    python scripts/search.py --top 3 "전용통신망 수의계약"
    python scripts/search.py --json "방만경영 예산통제"
"""

from __future__ import annotations

import sys
import json

import numpy as np

from common import INDEX_PATH, EMBEDDING_MODEL, embed_texts, eprint


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
    query_parts: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--top", "-k") and i + 1 < len(argv):
            top_k = int(argv[i + 1]); i += 2; continue
        if a == "--json":
            as_json = True; i += 1; continue
        query_parts.append(a); i += 1
    return " ".join(query_parts).strip(), top_k, as_json


def main() -> int:
    query, top_k, as_json = parse_args(sys.argv[1:])
    if not query:
        eprint('Usage: search.bat "your question"  [--top N] [--json]')
        return 1

    vectors, metas = load_index()
    qvec = embed_texts([query], is_query=True)[0]
    scores = vectors @ qvec  # cosine similarity (both normalised)
    order = np.argsort(-scores)[:top_k]

    results = [{
        "rank": rank + 1,
        "score": round(float(scores[i]), 4),
        "source": metas[i]["source"],
        "chunk": metas[i]["chunk"],
        "preview": metas[i]["preview"],
    } for rank, i in enumerate(order)]

    if as_json:
        print(json.dumps({"query": query, "results": results}, ensure_ascii=False, indent=2))
        return 0

    print(f"\n🔎 Query: {query}\n" + "=" * 70)
    for r in results:
        print(f"[{r['rank']}] score={r['score']:.4f}  {r['source']}  (chunk {r['chunk']})")
        print(f"    {r['preview']}")
        print("-" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
