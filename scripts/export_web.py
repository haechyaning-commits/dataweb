# -*- coding: utf-8 -*-
"""
Export the .npz index built by embed.py into the JSON format the web page
(web/index.html) loads with "인덱스 불러오기".

Why: build a high-quality Korean index once on a capable machine (e.g.
nlpai-lab/KURE-v1 via EMBEDDING_BACKEND=local), then hand a single
`index.json` to colleagues who only open the web page — no Python, no model
download, no token. This matches the "공용 인덱스 배포" workflow.

Note on search in the browser:
    The web page embeds the *query* in-browser with Xenova/multilingual-e5-small
    (384-dim). If this index was built with a different model (e.g. KURE-v1,
    1024-dim) the dimensions will not match, so the browser can browse the
    exported documents but cannot run semantic search on them — run searches
    with search.bat instead. The exported JSON records the model so the page
    can warn about the mismatch. An index built with e5-small is fully
    searchable in the browser.

Usage:
    python scripts/export_web.py                 # -> web/index.json
    python scripts/export_web.py out/shared.json  # custom output path
"""

from __future__ import annotations

import sys
import json
import pathlib

import numpy as np

from common import INDEX_PATH, eprint

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DEFAULT_OUT = _ROOT / "web" / "index.json"


def main() -> int:
    if not INDEX_PATH.exists():
        eprint(f"No index found at {INDEX_PATH}. Run embedding.bat first.")
        return 1

    out_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUT

    data = np.load(INDEX_PATH, allow_pickle=True)
    vectors = data["vectors"].astype(np.float32)
    metas = json.loads(str(data["metas"]))
    model = str(data["model"])
    doc_texts = json.loads(str(data["doc_texts"])) if "doc_texts" in data.files else {}

    if len(metas) != len(vectors):
        eprint(f"[error] metas ({len(metas)}) and vectors ({len(vectors)}) "
               f"count mismatch — rebuild the index with embedding.bat.")
        return 1

    items = []
    for meta, vec in zip(metas, vectors):
        items.append({
            "source": meta["source"],
            "chunk": meta.get("chunk", 0),
            "nChunks": meta.get("n_chunks", 1),
            # Older indexes stored only a 200-char preview; fall back to it.
            "text": meta.get("text") or meta.get("preview", ""),
            "vector": [round(float(x), 6) for x in vec],
        })

    # If the index predates doc_texts, approximate full text from single-chunk
    # documents; multi-chunk docs without stored text just show chunk text.
    if not doc_texts:
        for meta in metas:
            if meta.get("n_chunks", 1) == 1 and meta.get("source") not in doc_texts:
                doc_texts[meta["source"]] = meta.get("text") or meta.get("preview", "")

    payload = {"model": model, "docTexts": doc_texts, "items": items}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    dim = vectors.shape[1] if vectors.ndim == 2 else 0
    eprint(f"Exported {len(items)} vectors (model={model}, dim={dim})")
    eprint(f"  -> {out_path}")
    if "e5-small" not in model:
        eprint("[note] 이 인덱스는 브라우저 검색 모델(e5-small, 384차원)과 다른 "
               "모델로 만들어졌습니다.\n"
               "       웹페이지에서 문서 열람은 되지만 의미검색은 search.bat 을 "
               "사용하세요(차원 불일치).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
