"""Генерация метаданных пина: title / description / alt_text / хэштеги / ссылка.

Тексты собираются из шаблонов конфига и термов кластера, затем проходят проверки:
лимиты Pinterest, наличие ключа в заголовке и описании, отсутствие переспама.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .keywords import KeywordBank, keyword_density, normalize, stable_index, term_occurrences


@dataclass
class PinCopy:
    """Готовый текстовый пакет для одного пина."""

    item_id: str
    cluster: str
    term: str
    title: str
    description: str
    alt_text: str
    link: str = ""
    hashtags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Copywriter:
    def __init__(self, config: dict[str, Any], bank: KeywordBank | None = None):
        self.config = config
        self.copy_cfg = config["copy"]
        self.bank = bank or KeywordBank.from_config(config)
        self.niche = config["account"].get("niche", "")

    def build(self, item: dict[str, Any]) -> PinCopy:
        """item: {id, cluster, hook, support?, link?}."""
        item_id = str(item["id"])
        cluster_key = item["cluster"]
        if cluster_key not in self.bank.clusters:
            raise KeyError(f"Кластер '{cluster_key}' не описан в конфиге (item {item_id}).")

        term = item.get("term") or self.bank.pick(cluster_key, 1, seed=item_id)[0]
        head = self.bank.head(cluster_key)
        hook = item.get("hook", "").strip()
        support = item.get("support", "").strip()
        cta = self._pick(self.copy_cfg["cta"], item_id + "cta")

        fields = {
            "term": term,
            "head": head,
            "hook": hook,
            "support": support,
            "cta": cta,
            "niche": self.niche,
        }

        title = self._render("title_templates", fields, item_id)
        description = self._render("description_templates", fields, item_id)
        alt_text = self._render("alt_templates", fields, item_id)

        hashtags = self.bank.hashtags(cluster_key, self.copy_cfg["hashtags_max"])
        if hashtags:
            description = _append_within(
                description, " ".join(hashtags), self.copy_cfg["description_max"]
            )

        copy = PinCopy(
            item_id=item_id,
            cluster=cluster_key,
            term=term,
            title=_clip(title, self.copy_cfg["title_max"]),
            description=_clip(description, self.copy_cfg["description_max"]),
            alt_text=_clip(alt_text, self.copy_cfg["alt_max"]),
            link=self.build_link(item.get("link", "")),
            hashtags=hashtags,
        )
        copy.warnings = self.check(copy)
        return copy

    def build_link(self, link: str) -> str:
        """Добавляет UTM-метки, не затирая уже существующие параметры."""
        utm = self.config["utm"]
        if not link or not utm.get("enabled"):
            return link
        parts = urlparse(link)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault("utm_source", utm["source"])
        query.setdefault("utm_medium", utm["medium"])
        query.setdefault("utm_campaign", utm["campaign"])
        return urlunparse(parts._replace(query=urlencode(query)))

    def check(self, copy: PinCopy) -> list[str]:
        """Мягкие предупреждения — они не блокируют публикацию, но видны в отчёте."""
        warnings: list[str] = []
        term_norm = normalize(copy.term)
        head_words = term_norm.split()[:2]

        if head_words and not all(w in normalize(copy.title) for w in head_words):
            warnings.append("в заголовке нет ключа — Pinterest хуже поймёт тему пина")
        if term_norm not in normalize(copy.description):
            warnings.append("в описании нет точного вхождения ключа")
        if not copy.alt_text:
            warnings.append("пустой alt_text — теряется доступность и часть SEO-сигнала")

        # Одно точное вхождение ключа — это норма и цель; переспам начинается с повторов.
        occurrences = term_occurrences(copy.description, copy.term)
        density = keyword_density(copy.description, copy.term)
        if occurrences >= 3 or (
            occurrences >= 2 and density > self.copy_cfg["max_keyword_density"]
        ):
            warnings.append(
                f"переспам ключом в описании ({occurrences} вхождения, плотность {density}, "
                f"порог {self.copy_cfg['max_keyword_density']})"
            )
        if copy.title and copy.title.isupper():
            warnings.append("заголовок капсом читается как реклама")
        if len(copy.title) < 20:
            warnings.append("заголовок короче 20 символов — мало контекста для поиска")
        if len(copy.description) < 100:
            warnings.append("описание короче 100 символов — недобираете охват в поиске")
        return warnings

    def _render(self, template_key: str, fields: dict[str, str], seed: str) -> str:
        template = self._pick(self.copy_cfg[template_key], seed + template_key)
        try:
            text = template.format(**fields)
        except KeyError as exc:
            raise KeyError(
                f"В шаблоне copy.{template_key} используется неизвестное поле {exc}. "
                f"Доступны: {', '.join(sorted(fields))}."
            ) from exc
        return " ".join(text.split())

    @staticmethod
    def _pick(options: list[str], seed: str) -> str:
        if not options:
            return ""
        return options[stable_index(seed, len(options))]


def _clip(text: str, limit: int) -> str:
    """Обрезает по границе слова, чтобы не оставлять обрубков и висячих предлогов."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:—-")


def _append_within(text: str, suffix: str, limit: int) -> str:
    if not suffix:
        return text
    candidate = f"{text} {suffix}".strip()
    return candidate if len(candidate) <= limit else text
