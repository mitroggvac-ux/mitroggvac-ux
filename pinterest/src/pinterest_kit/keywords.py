"""Семантика: кластеры ключей, детерминированная ротация, контроль покрытия.

Pinterest — поисковая система, а не лента. Поэтому ключи здесь первичны:
каждый пин привязан к кластеру, а внутри кластера термы выдаются по кругу,
чтобы одинаковые формулировки не повторялись из пина в пин.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

_WORD_RE = re.compile(r"[^\w\s-]", flags=re.UNICODE)


def normalize(term: str) -> str:
    """Приводит ключ к сравнимому виду: нижний регистр, без пунктуации и лишних пробелов."""
    text = unicodedata.normalize("NFKC", term).lower().replace("ё", "е")
    text = _WORD_RE.sub(" ", text)
    return " ".join(text.split())


def stable_index(seed: str, modulo: int) -> int:
    """Детерминированный индекс из строки — одинаковый вход даёт одинаковый выход."""
    if modulo <= 0:
        raise ValueError("modulo должен быть > 0")
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulo


class KeywordBank:
    """Кластеры ключей из конфига + выдача термов без повторов подряд."""

    def __init__(self, clusters: dict[str, dict[str, Any]]):
        self.clusters = clusters
        self._used: Counter[str] = Counter()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "KeywordBank":
        return cls(config.get("clusters") or {})

    def keys(self) -> list[str]:
        return list(self.clusters)

    def head(self, cluster_key: str) -> str:
        return self.clusters[cluster_key]["head"]

    def terms(self, cluster_key: str) -> list[str]:
        return list(self.clusters[cluster_key].get("terms") or [])

    def hashtags(self, cluster_key: str, limit: int) -> list[str]:
        tags = self.clusters[cluster_key].get("hashtags") or []
        return [_as_hashtag(tag) for tag in tags[:limit]]

    def pick(self, cluster_key: str, count: int, seed: str = "") -> list[str]:
        """Возвращает `count` термов кластера, начиная со смещения от seed.

        Смещение детерминировано: тот же seed → тот же набор, поэтому повторный
        прогон плана не переписывает уже сгенерированные тексты.
        """
        pool = self.terms(cluster_key)
        if not pool:
            raise KeyError(f"У кластера '{cluster_key}' нет terms.")
        offset = stable_index(f"{cluster_key}|{seed}", len(pool)) if seed else self._used[cluster_key]
        picked = [pool[(offset + i) % len(pool)] for i in range(min(count, len(pool)))]
        self._used[cluster_key] += len(picked)
        return picked

    def cluster_for_board(self, board: dict[str, Any], seed: str = "") -> str:
        """Выбирает кластер, разрешённый для доски."""
        allowed = board.get("clusters") or self.keys()
        if not allowed:
            raise KeyError("Нет ни одного кластера для выбора.")
        if seed:
            return allowed[stable_index(f"{board['key']}|{seed}", len(allowed))]
        return allowed[self._used["_board_" + board["key"]] % len(allowed)]

    def coverage(self, cluster_keys: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Сколько раз каждый кластер встречается в плане и есть ли перекос."""
        counts = Counter(cluster_keys)
        total = sum(counts.values()) or 1
        report: dict[str, dict[str, Any]] = {}
        for key in self.keys():
            used = counts.get(key, 0)
            report[key] = {
                "pins": used,
                "share": round(used / total, 3),
                "terms_available": len(self.terms(key)),
                "status": _coverage_status(used, len(self.terms(key))),
            }
        return report


def _coverage_status(pins: int, terms_available: int) -> str:
    if pins == 0:
        return "не используется"
    if terms_available and pins > terms_available * 3:
        return "термы выработаны — добавьте хвостов"
    return "ок"


def term_occurrences(text: str, term: str) -> int:
    """Сколько раз ключ входит в текст целиком (после нормализации)."""
    normalized_term = normalize(term)
    if not normalized_term:
        return 0
    return normalize(text).count(normalized_term)


def keyword_density(text: str, term: str) -> float:
    """Доля слов ключа в тексте. Нужна, чтобы не скатиться в keyword stuffing."""
    words = normalize(text).split()
    if not words:
        return 0.0
    term_words = normalize(term).split()
    if not term_words:
        return 0.0
    return round(term_occurrences(text, term) * len(term_words) / len(words), 4)


def _as_hashtag(tag: str) -> str:
    cleaned = normalize(tag).replace("-", " ")
    parts = cleaned.split()
    if not parts:
        return ""
    return "#" + "".join(part.capitalize() if i else part for i, part in enumerate(parts))
