from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from rapidfuzz import fuzz

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FAQ_PATH = _REPO_ROOT / "bot" / "content" / "faqs.yaml"


@dataclass(frozen=True)
class FaqEntry:
    faq_id: str
    question: str
    answer: str


@dataclass(frozen=True)
class FaqMatch:
    faq_id: str
    canonical_question: str
    score: int
    answer: str


@dataclass(frozen=True)
class _FaqCandidate:
    faq_id: str
    canonical_question: str
    answer: str
    phrase: str


class FaqCatalog:
    def __init__(self, entries: list[FaqEntry], candidates: list[_FaqCandidate]) -> None:
        self.entries = entries
        self._candidates = candidates

    @property
    def count(self) -> int:
        return len(self.entries)

    def match(self, text: str, min_score: int) -> Optional[FaqMatch]:
        normalized = (text or "").strip().lower()
        if not normalized:
            return None

        best: Optional[tuple[int, str, _FaqCandidate]] = None
        for candidate in self._candidates:
            score = int(fuzz.token_sort_ratio(normalized, candidate.phrase))
            if score < min_score:
                continue
            tie_key = (score, candidate.faq_id)
            if best is None or tie_key > (best[0], best[1]):
                best = (score, candidate.faq_id, candidate)

        if best is None:
            return None

        score, _, candidate = best
        return FaqMatch(
            faq_id=candidate.faq_id,
            canonical_question=candidate.canonical_question,
            score=score,
            answer=candidate.answer,
        )

    def match_top_candidates(self, text: str, limit: int = 3) -> list[FaqMatch]:
        normalized = (text or "").strip().lower()
        if not normalized or limit < 1:
            return []

        best_by_id: dict[str, FaqMatch] = {}
        for candidate in self._candidates:
            score = int(fuzz.token_sort_ratio(normalized, candidate.phrase))
            existing = best_by_id.get(candidate.faq_id)
            if existing is not None and existing.score >= score:
                continue
            best_by_id[candidate.faq_id] = FaqMatch(
                faq_id=candidate.faq_id,
                canonical_question=candidate.canonical_question,
                score=score,
                answer=candidate.answer,
            )

        ranked = sorted(
            best_by_id.values(),
            key=lambda match: (match.score, match.faq_id),
            reverse=True,
        )
        return ranked[:limit]


_catalog_cache: dict[str, tuple[int, FaqCatalog]] = {}


def _resolve_faq_path(path: Optional[str]) -> Path:
    if path and path.strip():
        candidate = Path(path.strip())
        if not candidate.is_absolute():
            candidate = _REPO_ROOT / candidate
        return candidate
    return _DEFAULT_FAQ_PATH


def load_faq_catalog(path: Optional[str] = None) -> FaqCatalog:
    faq_path = _resolve_faq_path(path)
    resolved = str(faq_path)
    mtime_ns = faq_path.stat().st_mtime_ns if faq_path.is_file() else -1
    cached = _catalog_cache.get(resolved)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]

    if not faq_path.is_file():
        catalog = FaqCatalog(entries=[], candidates=[])
        _catalog_cache[resolved] = (mtime_ns, catalog)
        return catalog

    with faq_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    entries: list[FaqEntry] = []
    candidates: list[_FaqCandidate] = []
    for item in data.get("faqs") or []:
        if not isinstance(item, dict):
            continue
        faq_id = str(item.get("id") or "").strip()
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not faq_id or not answer:
            continue

        entries.append(FaqEntry(faq_id=faq_id, question=question, answer=answer))
        phrases = {question.lower()} if question else set()
        for trigger in item.get("triggers") or []:
            phrase = str(trigger).strip().lower()
            if phrase:
                phrases.add(phrase)

        for phrase in sorted(phrases):
            candidates.append(
                _FaqCandidate(
                    faq_id=faq_id,
                    canonical_question=question or faq_id,
                    answer=answer,
                    phrase=phrase,
                )
            )

    catalog = FaqCatalog(entries=entries, candidates=candidates)
    _catalog_cache[resolved] = (mtime_ns, catalog)
    return catalog


def clear_faq_catalog_cache() -> None:
    _catalog_cache.clear()
