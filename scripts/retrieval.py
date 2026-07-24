# -*- coding: utf-8 -*-
"""
Keyword scoring (BM25) and hybrid fusion for the audit-document search.

Why this exists
---------------
Pure dense (embedding) search blurs exact tokens — 법 조항 번호(제74조제5항),
기관명(㈜케이티), 금액(990,323원), 규정명(일상감사시행세칙) — that are decisive in
audit documents. A lightweight keyword signal recovers those exact matches, and
fusing the two ranks (dense + keyword) is the single highest-leverage accuracy
fix identified in docs/DIAGNOSIS.md (cause C).

No external dependency: BM25 is implemented here, and Korean is tokenised with a
word + character-bigram scheme that works without a morphological analyser.
"""

from __future__ import annotations

import math
import re
from collections import Counter


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------
# Runs of Hangul/Latin/digits are "words". Korean is largely space-separated in
# these documents, but josa/조사 make word matching brittle, so we ALSO emit
# character bigrams for Hangul runs — a cheap stand-in for morpheme matching that
# lets "수의계약" match "수의로 계약" and shrugs off particle differences.
_WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_HANGUL_RUN_RE = re.compile(r"[가-힣]{2,}")

# Common function/filler words. Overlap on these signals nothing about relevance,
# so we drop them from keyword scoring. Domain terms (조치·시정·감사 …) are NOT
# listed — those are legitimate query words. Kept in sync with web/index.html STOP.
_STOP = {
    "있는", "없는", "하는", "되는", "있다", "없다", "한다", "된다", "관련", "관한",
    "대한", "대하여", "위한", "위하여", "통한", "통하여", "및", "등", "등의", "또는",
    "그리고", "그러나", "경우", "때문", "해당", "각각", "이하", "이상", "부터", "까지",
    "에서", "으로", "같은", "따라", "또한",
}


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = _WORD_RE.findall(text)
    for run in _HANGUL_RUN_RE.findall(text):
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return [t for t in tokens if t not in _STOP]


# ---------------------------------------------------------------------------
# BM25 (Okapi)
# ---------------------------------------------------------------------------
class BM25:
    """Classic Okapi BM25 over a fixed corpus of already-tokenised documents."""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_tokens = corpus_tokens
        self.doc_len = [len(d) for d in corpus_tokens]
        self.n = len(corpus_tokens)
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.freqs: list[Counter] = [Counter(d) for d in corpus_tokens]
        df: Counter = Counter()
        for f in self.freqs:
            df.update(f.keys())
        # BM25+ style idf, floored at 0 so common terms never push scores negative.
        self.idf = {
            term: max(0.0, math.log(1 + (self.n - c + 0.5) / (c + 0.5)))
            for term, c in df.items()
        }

    def scores(self, query: str) -> list[float]:
        q_terms = tokenize(query)
        out = [0.0] * self.n
        if not self.n or self.avgdl == 0:
            return out
        for term in q_terms:
            idf = self.idf.get(term)
            if not idf:
                continue
            for i, f in enumerate(self.freqs):
                tf = f.get(term)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                out[i] += idf * (tf * (self.k1 + 1)) / denom
        return out


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------
def _minmax(values: list[float]) -> list[float]:
    """Scale to [0,1]. Dense cosine and BM25 live on different scales; normalise
    each per-query before blending so alpha means the same thing every time."""
    if not values:
        return values
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [0.0] * len(values)
    span = hi - lo
    return [(v - lo) / span for v in values]


def hybrid_scores(dense: list[float], keyword: list[float], alpha: float) -> list[float]:
    """alpha * dense + (1 - alpha) * keyword, each min-max normalised per query."""
    d = _minmax(list(dense))
    k = _minmax(list(keyword))
    return [alpha * d[i] + (1 - alpha) * k[i] for i in range(len(d))]
