"""Phase IV - deterministic entity resolution.

Resolution ladder for a raw name against the seed canonical registry:
1. exact match
2. normalized match (case, punctuation, legal suffixes stripped)
3. alias table (known alternative spellings)
4. token-similarity fuzzy match (Jaccard on tokens + prefix check)

Every decision is logged to the Entity Mapping Log with its strategy and
confidence. Unmatched names pass through as their own canonical form
(confidence 1.0, strategy "unmatched") so nothing is silently dropped.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..config import SEED_CANONICAL

_LEGAL_RE = re.compile(
    r"\b(inc|incorporated|corp|corporation|llc|ltd|limited|co|company|gmbh|"
    r"pty|plc|s\.a\.|lp|llp|labs|technologies|technology)\b\.?", re.I)
_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")

ALIASES = {
    "open ai": "OpenAI",
    "openai inc": "OpenAI",
    "google deepmind": "Google DeepMind",
    "deepmind": "Google DeepMind",
    "deep mind": "Google DeepMind",
    "facebook ai": "Meta AI",
    "meta": "Meta AI",
    "mistral": "Mistral AI",
    "huggingface": "Hugging Face",
    "hf": "Hugging Face",
    "perplexity ai": "Perplexity",
    "eleven labs": "ElevenLabs",
    "11labs": "ElevenLabs",
    "x.ai": "xAI",
    "weights and biases": "Weights & Biases",
    "wandb": "Weights & Biases",
    "copyai": "Copy.ai",
    "otter ai": "Otter.ai",
}


def normalize(name: str) -> str:
    n = name.lower().strip()
    n = _PUNCT_RE.sub(" ", n)
    n = _WS_RE.sub(" ", n).strip()
    n = _LEGAL_RE.sub("", n)
    return _WS_RE.sub(" ", n).strip()


def token_jaccard(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class EntityResolver:
    def __init__(self, seed: list[str] | None = None):
        self.seed = seed or SEED_CANONICAL
        self._norm_index = {normalize(c): c for c in self.seed}

    def resolve(self, raw_name: str) -> tuple[str, str, float]:
        """-> (canonical_name, strategy, confidence)"""
        raw = (raw_name or "").strip()
        if not raw:
            return raw, "unmatched", 1.0
        for c in self.seed:
            if raw == c:
                return c, "exact", 1.0
        norm = normalize(raw)
        if norm in self._norm_index:
            return self._norm_index[norm], "normalized", 0.97
        if norm in ALIASES:
            return ALIASES[norm], "alias", 0.95
        best, best_score = None, 0.0
        for cnorm, canonical in self._norm_index.items():
            score = token_jaccard(norm, cnorm)
            if score > best_score:
                best, best_score = canonical, score
        if best and best_score >= 0.6:
            return best, "fuzzy", round(best_score, 2)
        return raw, "unmatched", 1.0

    def resolve_and_log(self, store, raw_name: str, record_type: str) -> str:
        canonical, strategy, confidence = self.resolve(raw_name)
        store.log_mapping(raw_name, record_type, canonical, strategy, confidence,
                          datetime.now(timezone.utc).isoformat())
        return canonical
