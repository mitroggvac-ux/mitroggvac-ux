"""Мост между очередью и API: синхронизация досок и публикация запланированного.

Всё по умолчанию работает в режиме dry-run — реальные запросы уходят только
с явным `--apply`. Публикация идемпотентна: элемент с уже проставленным pin_id
повторно не отправляется.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .api import PinterestClient, PinterestError, image_file_source, image_url_source
from .store import (
    STATE_FAILED,
    STATE_PUBLISHED,
    STATE_SCHEDULED,
    Queue,
    load_board_map,
    save_board_map,
)


def sync_boards(
    client: PinterestClient,
    config: dict[str, Any],
    apply: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Сопоставляет доски конфига с досками аккаунта, создаёт недостающие."""
    remote = {board["name"].strip().lower(): board for board in client.list_boards()}
    mapping = load_board_map()
    actions: list[str] = []

    for board in config["boards"]:
        key = board["key"]
        name = board["name"]
        existing = remote.get(name.strip().lower())

        if existing is None:
            actions.append(f"создать доску «{name}»")
            if not apply:
                continue
            existing = client.create_board(
                name=name,
                description=board.get("description", ""),
                privacy=board.get("privacy", "PUBLIC"),
            )
            actions[-1] += f" → id {existing['id']}"

        entry = mapping.setdefault(key, {})
        entry["board_id"] = existing["id"]
        entry["name"] = name
        sections = entry.setdefault("sections", {})

        wanted_sections = board.get("sections") or []
        if wanted_sections and apply:
            present = {
                section["name"].strip().lower(): section["id"]
                for section in client.list_board_sections(existing["id"])
            }
            for section_name in wanted_sections:
                section_id = present.get(section_name.strip().lower())
                if section_id is None:
                    section_id = client.create_board_section(existing["id"], section_name)["id"]
                    actions.append(f"создать секцию «{section_name}» в «{name}»")
                sections[section_name] = section_id
        elif wanted_sections:
            actions.extend(
                f"проверить/создать секцию «{s}» в «{name}»" for s in wanted_sections
            )

    if apply:
        save_board_map(mapping)
    return mapping, actions


def publish_due(
    client: PinterestClient,
    config: dict[str, Any],
    queue: Queue,
    now: datetime | None = None,
    apply: bool = False,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Публикует элементы, у которых наступило время. Возвращает журнал операций."""
    now_iso = (now or datetime.now()).isoformat()
    mapping = load_board_map()
    log: list[dict[str, Any]] = []

    for item in queue.due(now_iso)[:limit]:
        entry = {"id": str(item["id"]), "publish_at": item.get("publish_at")}
        try:
            board_key = item.get("board")
            if not board_key:
                raise ValueError("не задана доска (board)")
            board_entry = mapping.get(board_key)
            if not board_entry:
                raise ValueError(
                    f"доска '{board_key}' не синхронизирована — запустите `pk boards-sync --apply`"
                )
            copy = item.get("copy")
            if not copy:
                raise ValueError("нет текстов — запустите `pk copy`")

            media = _media_source(item)
            section_id = ""
            if item.get("section"):
                section_id = (board_entry.get("sections") or {}).get(item["section"], "")

            entry["board_id"] = board_entry["board_id"]
            entry["title"] = copy["title"]

            if not apply:
                entry["status"] = "dry-run"
                log.append(entry)
                continue

            response = client.create_pin(
                board_id=board_entry["board_id"],
                title=copy["title"],
                description=copy["description"],
                media_source=media,
                link=copy.get("link", ""),
                alt_text=copy.get("alt_text", ""),
                board_section_id=section_id,
            )
            item["pin_id"] = response.get("id", "")
            item["published_at"] = datetime.now().isoformat()
            item["state"] = STATE_PUBLISHED
            item.pop("error", None)
            entry["status"] = "published"
            entry["pin_id"] = item["pin_id"]

        except (PinterestError, ValueError, OSError) as exc:
            if apply:
                item["state"] = STATE_FAILED
                item["error"] = str(exc)
            entry["status"] = "error"
            entry["error"] = str(exc)

        log.append(entry)

    if apply:
        queue.save()
    return log


def retry_failed(queue: Queue) -> int:
    """Возвращает упавшие элементы в очередь на публикацию."""
    count = 0
    for item in queue.filter(STATE_FAILED):
        if item.get("pin_id"):
            item["state"] = STATE_PUBLISHED  # пин всё-таки создан, просто не записали
            continue
        item["state"] = STATE_SCHEDULED
        item.pop("error", None)
        count += 1
    queue.save()
    return count


def _media_source(item: dict[str, Any]) -> dict[str, Any]:
    image = item.get("image", "")
    if not image:
        raise ValueError("не указан image (URL или путь к файлу)")
    if image.startswith(("http://", "https://")):
        return image_url_source(image)
    path = Path(image)
    if not path.exists():
        raise ValueError(f"файл не найден: {image}")
    return image_file_source(path)
