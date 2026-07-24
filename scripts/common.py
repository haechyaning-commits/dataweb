# -*- coding: utf-8 -*-
"""
Shared configuration and the embedding backend for the audit-document RAG demo.

Two backends, selected by EMBEDDING_BACKEND in .env:

  hf_api  (default) - call the model through the Hugging Face Inference API.
                      Needs HUGGINGFACEHUB_API_TOKEN. Nothing heavy runs locally.
  local             - run the model on this machine with sentence-transformers
                      (downloads the model once; no token needed, works offline).

The model itself is configurable (EMBEDDING_MODEL) so you can swap
BAAI/bge-m3 for a more Korean-specialised model without touching code.
"""

from __future__ import annotations

import os
import sys
import time
import pathlib

import numpy as np

# Load .env sitting next to the project root (../.env relative to this file).
_ROOT = pathlib.Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:  # dotenv is optional; env vars may be set another way
    pass


# ---------------------------------------------------------------------------
# Configuration (all overridable via .env)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3").strip()
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "hf_api").strip().lower()
HF_TOKEN = (
    os.getenv("HUGGINGFACEHUB_API_TOKEN")
    or os.getenv("HF_TOKEN")
    or ""
).strip()

# Some models (e5 family) want a role prefix; bge-m3 does not. Leave blank for bge.
QUERY_PREFIX = os.getenv("QUERY_PREFIX", "")
PASSAGE_PREFIX = os.getenv("PASSAGE_PREFIX", "")

# Chunking (characters, not tokens — good enough for a demo corpus).
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

def _resolve(value) -> pathlib.Path:
    """Absolute paths are used as-is; relative ones hang off the project root."""
    p = pathlib.Path(value)
    return p if p.is_absolute() else (_ROOT / p)


DATA_DIR = _resolve(os.getenv("DATA_DIR", "data"))
INDEX_DIR = _resolve(os.getenv("INDEX_DIR", "index"))
INDEX_PATH = INDEX_DIR / "index.npz"

BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "16"))


# ---------------------------------------------------------------------------
# Embedding backends
# ---------------------------------------------------------------------------
_local_model = None  # lazy-loaded sentence-transformers model


def _pick_device() -> str:
    """Prefer GPU when available; fall back to CPU. Overridable via EMBEDDING_DEVICE."""
    forced = os.getenv("EMBEDDING_DEVICE", "").strip().lower()
    if forced:
        return forced
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001 - torch missing/broken -> just use CPU
        pass
    return "cpu"


def _embed_local(texts: list[str]) -> np.ndarray:
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "EMBEDDING_BACKEND=local needs sentence-transformers.\n"
                "Install with: pip install -r requirements-local.txt\n"
                "(or: pip install sentence-transformers)"
            ) from e
        device = _pick_device()
        eprint(f"[local] loading {EMBEDDING_MODEL} on {device} "
               f"(first run downloads the model — KURE-v1 is ~2GB)...")
        _local_model = SentenceTransformer(EMBEDDING_MODEL, device=device)
        if device == "cpu":
            eprint("[local] running on CPU — 대량 문서는 시간이 걸립니다. "
                   "GPU가 있으면 자동으로 사용합니다.")
    vecs = _local_model.encode(
        texts, batch_size=BATCH_SIZE, normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vecs, dtype=np.float32)


_hf_client = None  # lazy-loaded InferenceClient


def _embed_hf_api(texts: list[str]) -> np.ndarray:
    global _hf_client
    if not HF_TOKEN:
        raise RuntimeError(
            "HUGGINGFACEHUB_API_TOKEN is not set.\n"
            "Put your token in .env (get one at https://huggingface.co/settings/tokens),\n"
            "or switch to a local model with EMBEDDING_BACKEND=local."
        )
    if _hf_client is None:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "EMBEDDING_BACKEND=hf_api needs huggingface_hub.\n"
                "Install with: pip install huggingface_hub"
            ) from e
        _hf_client = InferenceClient(model=EMBEDDING_MODEL, token=HF_TOKEN)

    out: list[np.ndarray] = []
    for text in texts:
        vec = _hf_api_one(text)
        out.append(vec)
    return np.vstack(out).astype(np.float32)


def _hf_api_one(text: str, retries: int = 4) -> np.ndarray:
    """Embed one string via the Inference API, with backoff for cold starts / 503s."""
    delay = 2.0
    for attempt in range(retries):
        try:
            vec = np.asarray(_hf_client.feature_extraction(text), dtype=np.float32)
            # Token-level output (n_tokens, dim) -> mean pool to a single vector.
            if vec.ndim == 2:
                vec = vec.mean(axis=0)
            return _l2_normalize(vec)
        except Exception as e:  # noqa: BLE001 - surface a readable message after retries
            if attempt == retries - 1:
                raise RuntimeError(f"HF Inference API call failed: {e}") from e
            eprint(f"  ...retry {attempt + 1}/{retries - 1} after error: {e}")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def embed_texts(texts: list[str], *, is_query: bool = False) -> np.ndarray:
    """Return an (n, dim) L2-normalised float32 matrix for the given texts."""
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    prefix = QUERY_PREFIX if is_query else PASSAGE_PREFIX
    prepared = [f"{prefix}{t}" if prefix else t for t in texts]
    if EMBEDDING_BACKEND == "local":
        return _embed_local(prepared)
    if EMBEDDING_BACKEND == "hf_api":
        return _embed_hf_api(prepared)
    raise RuntimeError(f"Unknown EMBEDDING_BACKEND: {EMBEDDING_BACKEND!r} (use hf_api or local)")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Try to end on a paragraph/sentence boundary within the last 30%.
        if end < len(text):
            window = text[start:end]
            for sep in ("\n\n", "\n", ". ", "。", " "):
                cut = window.rfind(sep)
                if cut > size * 0.7:
                    end = start + cut + len(sep)
                    break
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)
