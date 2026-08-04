"""Отчёт по росту аккаунта в Markdown: факт против целей + что чинить дальше.

Рекомендации выводятся из порогов в docs/05-metrics.md, а не из «ощущений»:
каждая строка отчёта привязана к конкретной метрике и её значению.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from . import analytics
from .keywords import KeywordBank
from .store import Queue

# Пороги здоровья аккаунта (обоснование — docs/05-metrics.md).
SAVE_RATE_FLOOR = 0.5  # % сохранений от показов
CLICK_RATE_FLOOR = 0.2  # % исходящих кликов от показов
STALLED_GROWTH = 5.0  # % прироста показов между половинами окна


def render(
    config: dict[str, Any],
    snapshot: dict[str, Any],
    queue: Queue,
    today: date | None = None,
) -> str:
    window = snapshot["window"]
    account_rows = snapshot["account_rows"]
    pin_rows = snapshot["pin_rows"]
    total = analytics.totals(account_rows)
    midpoint = _midpoint(window["start"], window["end"])
    first_half, second_half = analytics.split_periods(account_rows, midpoint)
    delta = analytics.growth(first_half, second_half)

    lines: list[str] = []
    handle = config["account"].get("handle", "—")
    lines.append(f"# Pinterest: отчёт по росту — @{handle}")
    lines.append("")
    lines.append(
        f"Окно: **{window['start']} → {window['end']}** ({window['days']} дн.). "
        f"Сформировано: {(today or date.today()).isoformat()}."
    )
    lines.append("")

    lines.append("## Сводка за окно")
    lines.append("")
    lines.append("| Метрика | Значение | 1-я половина | 2-я половина | Динамика |")
    lines.append("|---|---:|---:|---:|---:|")
    for metric in sorted(total, key=lambda m: -total[m]):
        lines.append(
            f"| {metric} | {_num(total[metric])} | {_num(first_half.get(metric, 0))} | "
            f"{_num(second_half.get(metric, 0))} | {_pct(delta.get(metric, 0))} |"
        )
    save_rate = analytics.save_rate(total)
    click_rate = analytics.click_rate(total)
    lines.append(f"| Save rate | {save_rate}% | — | — | порог {SAVE_RATE_FLOOR}% |")
    lines.append(f"| Click rate | {click_rate}% | — | — | порог {CLICK_RATE_FLOOR}% |")
    lines.append("")

    goals = config.get("goals") or {}
    if goals:
        lines.append("## Цели месяца")
        lines.append("")
        lines.append("| Цель | План | Факт за окно | Выполнено |")
        lines.append("|---|---:|---:|---:|")
        for goal_key, target in goals.items():
            metric = _GOAL_METRICS.get(goal_key)
            fact = total.get(metric, 0.0) if metric else 0.0
            share = round(fact / target * 100, 1) if target else 0.0
            lines.append(f"| {goal_key} | {_num(target)} | {_num(fact)} | {share}% |")
        lines.append("")

    cluster_stats = analytics.by_cluster(queue, pin_rows)
    if cluster_stats:
        lines.append("## Кластеры ключей")
        lines.append("")
        lines.append("| Кластер | Пинов | Показы | Сохранения | Save rate | Показов на пин |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        ranked = sorted(
            cluster_stats.items(), key=lambda kv: -kv[1].get("IMPRESSION", 0.0)
        )
        for cluster, metrics in ranked:
            pins = metrics.get("pins", 0) or 1
            lines.append(
                f"| {cluster} | {_num(metrics.get('pins', 0))} | "
                f"{_num(metrics.get('IMPRESSION', 0))} | {_num(metrics.get('SAVE', 0))} | "
                f"{analytics.save_rate(metrics)}% | {_num(metrics.get('IMPRESSION', 0) / pins)} |"
            )
        lines.append("")

    lines.append("## Что делать дальше")
    lines.append("")
    for recommendation in recommendations(config, snapshot, queue, total, delta, cluster_stats):
        lines.append(f"- {recommendation}")
    lines.append("")

    if snapshot.get("errors"):
        lines.append("## Не собралось")
        lines.append("")
        for error in snapshot["errors"]:
            lines.append(f"- пин `{error['pin_id']}`: {error['error']}")
        lines.append("")

    return "\n".join(lines)


def recommendations(
    config: dict[str, Any],
    snapshot: dict[str, Any],
    queue: Queue,
    total: dict[str, float],
    delta: dict[str, float],
    cluster_stats: dict[str, dict[str, float]],
) -> list[str]:
    out: list[str] = []
    save_rate = analytics.save_rate(total)
    click_rate = analytics.click_rate(total)
    impressions_growth = delta.get("IMPRESSION", 0.0)

    if not total:
        return [
            "Данных нет: либо аккаунт ещё не набрал статистику, либо не хватает "
            "скоупа `user_accounts:read`. Проверьте `pk auth-check`."
        ]

    if save_rate < SAVE_RATE_FLOOR:
        out.append(
            f"**Save rate {save_rate}% ниже порога {SAVE_RATE_FLOOR}%** — тему находят, "
            "но пин не хочется сохранять. Чинится обложкой и заголовком, а не количеством пинов: "
            "переберите 3 варианта визуала на один и тот же ключ."
        )
    else:
        out.append(f"Save rate {save_rate}% в норме — формат работает, можно наращивать объём.")

    if click_rate < CLICK_RATE_FLOOR and total.get("OUTBOUND_CLICK") is not None:
        out.append(
            f"Click rate {click_rate}% ниже {CLICK_RATE_FLOOR}% — пин закрывает потребность "
            "целиком внутри Pinterest. Оставляйте открытый вопрос и явный повод перейти."
        )

    if impressions_growth < STALLED_GROWTH:
        out.append(
            f"Показы почти не растут ({_pct(impressions_growth)} между половинами окна). "
            "Сначала проверьте регулярность публикаций, потом — новые кластеры ключей."
        )
    else:
        out.append(f"Показы растут ({_pct(impressions_growth)}) — держите текущий ритм.")

    bank = KeywordBank.from_config(config)
    planned_clusters = [item.get("cluster") for item in queue.items if item.get("cluster")]
    coverage = bank.coverage(c for c in planned_clusters if c)
    idle = [key for key, stats in coverage.items() if stats["pins"] == 0]
    if idle:
        out.append(
            "Кластеры без единого пина: " + ", ".join(f"`{k}`" for k in idle) +
            ". Это неиспользованный поисковый спрос — добавьте их в ближайший план."
        )
    exhausted = [
        key for key, stats in coverage.items() if stats["status"].startswith("термы выработаны")
    ]
    if exhausted:
        out.append(
            "Термы кончились в кластерах: " + ", ".join(f"`{k}`" for k in exhausted) +
            ". Описания начнут повторяться — расширьте `terms` в конфиге."
        )

    if cluster_stats:
        ranked = sorted(cluster_stats.items(), key=lambda kv: -kv[1].get("IMPRESSION", 0.0))
        best = ranked[0]
        out.append(
            f"Лучший кластер — `{best[0]}` ({_num(best[1].get('IMPRESSION', 0))} показов). "
            "Дайте ему больше слотов в следующем плане и разложите на под-темы."
        )
        weak = [c for c, m in ranked if m.get("pins", 0) >= 5 and analytics.save_rate(m) < SAVE_RATE_FLOOR]
        if weak:
            out.append(
                "Кластеры с достаточной выборкой, но слабым откликом: "
                + ", ".join(f"`{c}`" for c in weak)
                + ". Либо меняйте подачу, либо убирайте из ротации."
            )

    counts = queue.counts()
    cadence = config["cadence"]["pins_per_day"]
    if counts.get("scheduled", 0) < cadence * 7:
        out.append(
            f"В очереди осталось {counts.get('scheduled', 0)} запланированных пинов — "
            f"меньше недели при {cadence} пинах в день. Пополните план: пауза бьёт по охвату сильнее, "
            "чем снижение качества."
        )
    if counts.get("failed", 0):
        out.append(f"{counts['failed']} пинов упали при публикации — разберите `pk status --state failed`.")

    return out


_GOAL_METRICS = {
    "monthly_impressions": "IMPRESSION",
    "monthly_saves": "SAVE",
    "monthly_outbound_clicks": "OUTBOUND_CLICK",
    "monthly_pin_clicks": "PIN_CLICK",
    "monthly_engagement": "ENGAGEMENT",
    "audience": "TOTAL_AUDIENCE",
}


def _midpoint(start: str, end: str) -> str:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return (start_date + (end_date - start_date) / 2).isoformat()


def _num(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _pct(value: float) -> str:
    return f"+{value}%" if value > 0 else f"{value}%"
