"""Календарь публикаций: раскладывает идеи по датам, слотам и доскам.

Правила, которые здесь зашиты, — это то, за что чаще всего прилетает от Pinterest
при «раскачке»: не лить всё в одну доску, держать паузы между пинами, не выходить
за дневную норму. Раскладка детерминированная: повторный запуск на тех же входных
данных даёт тот же план.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from .config import WEEKDAYS
from .keywords import KeywordBank, stable_index


@dataclass
class ScheduledItem:
    item_id: str
    board_key: str
    cluster: str
    publish_at: str  # ISO 8601, локальное время аккаунта
    slot: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Scheduler:
    def __init__(self, config: dict[str, Any], bank: KeywordBank | None = None):
        self.config = config
        self.cadence = config["cadence"]
        self.bank = bank or KeywordBank.from_config(config)
        self.boards = config["boards"]

    def publish_days(self, start: date, days: int) -> list[date]:
        """Даты в окне, попадающие в разрешённые дни недели."""
        allowed = {WEEKDAYS.index(d) for d in self.cadence["days"]}
        return [
            start + timedelta(days=offset)
            for offset in range(days)
            if (start + timedelta(days=offset)).weekday() in allowed
        ]

    def capacity(self, start: date, days: int) -> int:
        return len(self.publish_days(start, days)) * self.cadence["pins_per_day"]

    def build(
        self,
        items: Iterable[dict[str, Any]],
        start: date,
        days: int = 30,
    ) -> tuple[list[ScheduledItem], list[dict[str, Any]]]:
        """Возвращает (запланированные, не влезшие в окно).

        Слот отдаётся первому элементу, для которого нашлась подходящая доска:
        доска должна вести выбранный кластер и не выбрать дневной лимит.
        """
        remaining = list(items)
        self._assert_clusters_have_boards(remaining)
        calendar_days = self.publish_days(start, days)
        slots = sorted(self.cadence["slots"])[: self.cadence["pins_per_day"]]
        board_rotation = self._weighted_boards()

        scheduled: list[ScheduledItem] = []
        per_board_per_day: dict[tuple[date, str], int] = defaultdict(int)
        rotation_pos = 0

        for day in calendar_days:
            last_slot_minutes: int | None = None
            for slot in slots:
                if not remaining:
                    break
                slot_minutes = _minutes(slot)
                if (
                    last_slot_minutes is not None
                    and slot_minutes - last_slot_minutes < self.cadence["min_gap_minutes"]
                ):
                    continue

                placement = None
                for index, item in enumerate(remaining):
                    board_key, next_pos = self._next_board(
                        item, board_rotation, rotation_pos, per_board_per_day, day
                    )
                    if board_key is not None:
                        placement = (index, board_key, next_pos)
                        break
                if placement is None:
                    break  # на этот день доски выбрали лимиты

                index, board_key, rotation_pos = placement
                item = remaining.pop(index)
                cluster = item.get("cluster") or self.bank.cluster_for_board(
                    _board(self.boards, board_key), seed=str(item["id"])
                )
                item["cluster"] = cluster
                per_board_per_day[(day, board_key)] += 1
                scheduled.append(
                    ScheduledItem(
                        item_id=str(item["id"]),
                        board_key=board_key,
                        cluster=cluster,
                        publish_at=datetime.combine(day, _to_time(slot)).isoformat(),
                        slot=slot,
                    )
                )
                last_slot_minutes = slot_minutes

        return scheduled, remaining

    def boards_for_cluster(self, cluster: str) -> list[str]:
        """Доски, которые ведут этот кластер (пустой список clusters = доска берёт всё)."""
        return [
            board["key"]
            for board in self.boards
            if not board.get("clusters") or cluster in board["clusters"]
        ]

    def _assert_clusters_have_boards(self, items: list[dict[str, Any]]) -> None:
        orphans = sorted(
            {
                item["cluster"]
                for item in items
                if item.get("cluster") and not item.get("board")
                and not self.boards_for_cluster(item["cluster"])
            }
        )
        if orphans:
            raise ValueError(
                "Нет доски для кластеров: " + ", ".join(orphans)
                + ". Добавьте кластер в boards[].clusters или укажите board у элемента."
            )

    def _weighted_boards(self) -> list[str]:
        """Список ключей досок с учётом weight — чем выше вес, тем чаще доска в ротации."""
        rotation: list[str] = []
        for board in self.boards:
            rotation.extend([board["key"]] * int(board.get("weight", 1)))
        return rotation or [b["key"] for b in self.boards]

    def _next_board(
        self,
        item: dict[str, Any],
        rotation: list[str],
        position: int,
        per_board_per_day: dict[tuple[date, str], int],
        day: date,
    ) -> tuple[str | None, int]:
        """Явно заданная доска побеждает; иначе — первая свободная доска нужного кластера."""
        limit = self.cadence["max_per_board_per_day"]
        pinned = item.get("board")
        if pinned:
            if per_board_per_day[(day, pinned)] < limit:
                return pinned, position
            return None, position

        cluster = item.get("cluster")
        eligible = set(self.boards_for_cluster(cluster)) if cluster else None
        for step in range(len(rotation)):
            candidate = rotation[(position + step) % len(rotation)]
            if eligible is not None and candidate not in eligible:
                continue
            if per_board_per_day[(day, candidate)] < limit:
                return candidate, (position + step + 1) % len(rotation)
        return None, position

    def cluster_balance(self, scheduled: list[ScheduledItem]) -> dict[str, dict[str, Any]]:
        return self.bank.coverage(s.cluster for s in scheduled)


def _board(boards: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for board in boards:
        if board["key"] == key:
            return board
    raise KeyError(f"Доска '{key}' не найдена.")


def _minutes(slot: str) -> int:
    hours, minutes = slot.split(":")
    return int(hours) * 60 + int(minutes)


def _to_time(slot: str) -> time:
    hours, minutes = slot.split(":")
    return time(int(hours), int(minutes))


def spread_seed(item_id: str, buckets: int) -> int:
    """Экспортируется для тестов и внешних скриптов, которым нужна та же раскладка."""
    return stable_index(item_id, buckets)
