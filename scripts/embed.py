# -*- coding: utf-8 -*-
"""
Build the search index.

Walks DATA_DIR, extracts text from every supported document, splits each
document into overlapping chunks, embeds the chunks, and writes everything to
index/index.npz (vectors + metadata).

Usage:
    python scripts/embed.py                # embed everything under data/
    python scripts/embed.py path/to/file   # embed specific files instead
"""

from __future__ import annotations

import sys
import json
import pathlib

import numpy as np

from common import (
    DATA_DIR, INDEX_DIR, INDEX_PATH, EMBEDDING_MODEL, EMBEDDING_BACKEND,
    BATCH_SIZE, embed_texts, chunk_text, eprint,
)
from extract import extract_text, SUPPORTED_EXTENSIONS


def gather_files(args: list[str]) -> list[pathlib.Path]:
    if args:
        return [pathlib.Path(a) for a in args]
    files: list[pathlib.Path] = []
    for path in sorted(DATA_DIR.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return files


def main() -> int:
    files = gather_files(sys.argv[1:])
    if not files:
        eprint(f"No supported documents found in {DATA_DIR}")
        eprint(f"Supported types: {', '.join(SUPPORTED_EXTENSIONS)}")
        return 1

    eprint(f"Backend : {EMBEDDING_BACKEND}")
    eprint(f"Model   : {EMBEDDING_MODEL}")
    eprint(f"Files   : {len(files)}")
    eprint("-" * 60)

    texts: list[str] = []
    metas: list[dict] = []
    doc_texts: dict[str, str] = {}

    for path in files:
        try:
            raw = extract_text(str(path))
        except Exception as e:  # noqa: BLE001
            eprint(f"[skip] {path.name}: extraction failed ({e})")
            continue
        chunks = chunk_text(raw)
        if not chunks:
            eprint(f"[warn] {path.name}: no extractable text "
                   f"(scanned image? set ENABLE_OCR=1) — skipped")
            continue
        doc_texts[path.name] = raw
        for idx, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append({
                "source": path.name,
                "path": str(path),
                "chunk": idx,
                "n_chunks": len(chunks),
                "text": chunk,
                "preview": chunk[:200].replace("\n", " "),
            })
        eprint(f"[ok]   {path.name}: {len(chunks)} chunk(s)")

    if not texts:
        eprint("Nothing to embed.")
        return 1

    eprint("-" * 60)
    eprint(f"Embedding {len(texts)} chunk(s)...")
    vectors = _embed_in_batches(texts)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        INDEX_PATH,
        vectors=vectors,
        metas=np.array(json.dumps(metas, ensure_ascii=False)),
        doc_texts=np.array(json.dumps(doc_texts, ensure_ascii=False)),
        model=np.array(EMBEDDING_MODEL),
    )
    eprint("-" * 60)
    eprint(f"Saved {vectors.shape[0]} vectors (dim={vectors.shape[1]}) -> {INDEX_PATH}")
    return 0


def _embed_in_batches(texts: list[str]) -> np.ndarray:
    out: list[np.ndarray] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        out.append(embed_texts(batch, is_query=False))
        eprint(f"  embedded {min(i + BATCH_SIZE, len(texts))}/{len(texts)}")
    return np.vstack(out)


if __name__ == "__main__":
    raise SystemExit(main())
