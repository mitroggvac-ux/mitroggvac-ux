"""Сбор и разбор аналитики: аккаунт целиком и отдельные пины.

Ответы Pinterest по аналитике исторически меняли форму (то `all`, то плоский
объект, то `daily_metrics`), поэтому здесь всё приводится к одному виду:
список строк {date, metric, value} — с ним дальше работают агрегации и отчёт.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from .api import PinterestClient
from .store import Queue, save_snapshot

Row = dict[str, Any]


def date_window(days: int, today: date | None = None) -> tuple[str, str]:
    end = today or date.today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def normalize_account(payload: dict[str, Any]) -> list[Row]:
    """Достаёт daily-метрики из ответа /user_account/analytics."""
    rows: list[Row] = []
    for scope, block in _iter_blocks(payload):
        for entry in block.get("daily_metrics", []) or []:
            day = entry.get("date")
            if not day:
                continue
            for metric, value in (entry.get("metrics") or {}).items():
                if isinstance(value, (int, float)):
                    rows.append({"date": day, "metric": metric, "value": value, "scope": scope})
    return rows


def normalize_pin(pin_id: str, payload: dict[str, Any]) -> list[Row]:
    rows: list[Row] = []
    for scope, block in _iter_blocks(payload):
        summary = block.get("summary_metrics") or {}
        for metric, value in summary.items():
            if isinstance(value, (int, float)):
                rows.append({"pin_id": pin_id, "metric": metric, "value": value, "scope": scope})
    return rows


def _iter_blocks(payload: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return []
    blocks = []
    for key, value in payload.items():
        if isinstance(value, dict) and ("daily_metrics" in value or "summary_metrics" in value):
            blocks.append((key, value))
    if not blocks and ("daily_metrics" in payload or "summary_metrics" in payload):
        blocks.append(("all", payload))
    return blocks


def totals(rows: Iterable[Row]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for row in rows:
        result[row["metric"]] += row["value"]
    return dict(result)


def split_periods(rows: list[Row], midpoint: str) -> tuple[dict[str, float], dict[str, float]]:
    """Делит окно пополам, чтобы увидеть динамику, а не только сумму."""
    earlier = [row for row in rows if row.get("date", "") < midpoint]
    later = [row for row in rows if row.get("date", "") >= midpoint]
    return totals(earlier), totals(later)


def growth(previous: dict[str, float], current: dict[str, float]) -> dict[str, float]:
    """Прирост в процентах по каждой метрике."""
    result: dict[str, float] = {}
    for metric in set(previous) | set(current):
        before = previous.get(metric, 0.0)
        after = current.get(metric, 0.0)
        if before == 0:
            result[metric] = 100.0 if after else 0.0
        else:
            result[metric] = round((after - before) / before * 100, 1)
    return result


def by_cluster(queue: Queue, pin_rows: list[Row]) -> dict[str, dict[str, float]]:
    """Сводит метрики пинов по кластерам ключей — что реально тянет охват."""
    cluster_of = {
        str(item.get("pin_id")): item.get("cluster", "?")
        for item in queue.items
        if item.get("pin_id")
    }
    result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in pin_rows:
        cluster = cluster_of.get(str(row.get("pin_id")), "?")
        result[cluster][row["metric"]] += row["value"]
        result[cluster]["pins"] = result[cluster].get("pins", 0)
    for cluster in result:
        pins = {p for p, c in cluster_of.items() if c == cluster}
        result[cluster]["pins"] = float(len(pins))
    return {k: dict(v) for k, v in result.items()}


def save_rate(metrics: dict[str, float]) -> float:
    impressions = metrics.get("IMPRESSION", 0.0)
    saves = metrics.get("SAVE", 0.0)
    return round(saves / impressions * 100, 2) if impressions else 0.0


def click_rate(metrics: dict[str, float]) -> float:
    impressions = metrics.get("IMPRESSION", 0.0)
    clicks = metrics.get("OUTBOUND_CLICK", 0.0) or metrics.get("PIN_CLICK", 0.0)
    return round(clicks / impressions * 100, 2) if impressions else 0.0


def pull(
    client: PinterestClient,
    queue: Queue,
    days: int = 30,
    pin_limit: int = 50,
    today: date | None = None,
) -> dict[str, Any]:
    """Тянет аналитику аккаунта и последних опубликованных пинов, кладёт снапшот."""
    start, end = date_window(days, today)
    account_payload = client.account_analytics(start, end)
    account_rows = normalize_account(account_payload)

    published = [item for item in queue.filter("published") if item.get("pin_id")]
    published.sort(key=lambda item: item.get("published_at", ""), reverse=True)

    pin_rows: list[Row] = []
    errors: list[dict[str, str]] = []
    for item in published[:pin_limit]:
        try:
            payload = client.pin_analytics(str(item["pin_id"]), start, end)
            pin_rows.extend(normalize_pin(str(item["pin_id"]), payload))
        except Exception as exc:  # аналитика одного пина не должна ронять весь сбор
            errors.append({"pin_id": str(item["pin_id"]), "error": str(exc)})

    snapshot = {
        "window": {"start": start, "end": end, "days": days},
        "account_rows": account_rows,
        "pin_rows": pin_rows,
        "errors": errors,
    }
    save_snapshot(f"{end}-{days}d", snapshot)
    return snapshot
