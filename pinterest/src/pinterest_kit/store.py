"""Очередь контента и маппинг досок — состояние пайплайна в простых JSON-файлах.

Хранение файлами, а не в БД, сделано намеренно: очередь читается глазами,
правится руками и коммитится в git вместе с планом (кроме токенов).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path("data")
QUEUE_PATH = DATA_DIR / "queue.json"
BOARD_MAP_PATH = DATA_DIR / "boards.json"
ANALYTICS_DIR = DATA_DIR / "analytics"

STATE_DRAFT = "draft"
STATE_SCHEDULED = "scheduled"
STATE_PUBLISHED = "published"
STATE_FAILED = "failed"
STATES = {STATE_DRAFT, STATE_SCHEDULED, STATE_PUBLISHED, STATE_FAILED}


@dataclass
class Queue:
    """Список элементов контент-плана с их состоянием."""

    items: list[dict[str, Any]]
    path: Path = QUEUE_PATH

    @classmethod
    def load(cls, path: Path | str = QUEUE_PATH) -> "Queue":
        file_path = Path(path)
        if not file_path.exists():
            return cls(items=[], path=file_path)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        items = payload["items"] if isinstance(payload, dict) else payload
        return cls(items=items, path=file_path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"items": self.items}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def by_id(self, item_id: str) -> dict[str, Any]:
        for item in self.items:
            if str(item["id"]) == str(item_id):
                return item
        raise KeyError(f"Элемент '{item_id}' не найден в очереди.")

    def filter(self, state: str | None = None) -> list[dict[str, Any]]:
        if state is None:
            return list(self.items)
        return [item for item in self.items if item.get("state", STATE_DRAFT) == state]

    def due(self, now_iso: str, state: str = STATE_SCHEDULED) -> list[dict[str, Any]]:
        """Элементы, у которых время публикации уже наступило."""
        return sorted(
            (
                item
                for item in self.filter(state)
                if item.get("publish_at") and item["publish_at"] <= now_iso
            ),
            key=lambda item: item["publish_at"],
        )

    def upsert(self, items: Iterable[dict[str, Any]]) -> tuple[int, int]:
        """Добавляет новые и обновляет существующие по id. Возвращает (добавлено, обновлено)."""
        index = {str(item["id"]): item for item in self.items}
        added = updated = 0
        for incoming in items:
            key = str(incoming["id"])
            if key in index:
                index[key].update(incoming)
                updated += 1
            else:
                incoming.setdefault("state", STATE_DRAFT)
                self.items.append(incoming)
                index[key] = incoming
                added += 1
        return added, updated

    def counts(self) -> dict[str, int]:
        result = {state: 0 for state in sorted(STATES)}
        for item in self.items:
            state = item.get("state", STATE_DRAFT)
            result[state] = result.get(state, 0) + 1
        return result


def load_board_map(path: Path | str = BOARD_MAP_PATH) -> dict[str, dict[str, Any]]:
    """key доски из конфига -> {board_id, name, sections: {name: id}}."""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def save_board_map(mapping: dict[str, dict[str, Any]], path: Path | str = BOARD_MAP_PATH) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")


def save_snapshot(name: str, payload: dict[str, Any], directory: Path | str = ANALYTICS_DIR) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_snapshots(directory: Path | str = ANALYTICS_DIR) -> list[dict[str, Any]]:
    target_dir = Path(directory)
    if not target_dir.exists():
        return []
    snapshots = []
    for path in sorted(target_dir.glob("*.json")):
        snapshots.append(json.loads(path.read_text(encoding="utf-8")))
    return snapshots
