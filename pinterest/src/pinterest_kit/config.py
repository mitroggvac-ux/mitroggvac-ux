"""Загрузка и валидация конфигурации аккаунта.

Конфиг — обычный JSON (см. config/account.example.json), чтобы его можно было
править руками и хранить в git без лишних зависимостей.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("config/account.json")

# Лимиты Pinterest на поля пина (символы).
PIN_TITLE_MAX = 100
PIN_DESCRIPTION_MAX = 500
PIN_ALT_TEXT_MAX = 500
BOARD_NAME_MAX = 50
BOARD_DESCRIPTION_MAX = 500

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class ConfigError(ValueError):
    """Конфиг не прошёл валидацию."""


def load(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Читает конфиг, подставляет умолчания и валидирует его."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise ConfigError(
            f"Конфиг не найден: {config_path}. "
            "Скопируйте config/account.example.json в config/account.json."
        )
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path}: невалидный JSON — {exc}") from exc

    config = _with_defaults(raw)
    validate(config)
    config["_path"] = str(config_path)
    return config


def _with_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(json.dumps(raw))  # глубокая копия
    config.setdefault("account", {})
    config["account"].setdefault("language", "ru")
    config["account"].setdefault("timezone", "UTC")

    cadence = config.setdefault("cadence", {})
    cadence.setdefault("pins_per_day", 5)
    cadence.setdefault("slots", ["09:00", "12:00", "15:00", "18:00", "21:00"])
    cadence.setdefault("days", list(WEEKDAYS))
    cadence.setdefault("max_per_board_per_day", 2)
    cadence.setdefault("min_gap_minutes", 45)

    copy_cfg = config.setdefault("copy", {})
    copy_cfg.setdefault("title_max", PIN_TITLE_MAX)
    copy_cfg.setdefault("description_max", PIN_DESCRIPTION_MAX)
    copy_cfg.setdefault("alt_max", PIN_ALT_TEXT_MAX)
    copy_cfg.setdefault("hashtags_max", 3)
    copy_cfg.setdefault("max_keyword_density", 0.1)
    copy_cfg.setdefault("title_templates", ["{term}: {hook}"])
    copy_cfg.setdefault("description_templates", ["{hook} {support} {cta}"])
    copy_cfg.setdefault("alt_templates", ["{term} — {hook}"])
    copy_cfg.setdefault("cta", ["Сохраните, чтобы не потерять."])

    utm = config.setdefault("utm", {})
    utm.setdefault("enabled", False)
    utm.setdefault("source", "pinterest")
    utm.setdefault("medium", "social")
    utm.setdefault("campaign", "organic")

    config.setdefault("goals", {})
    config.setdefault("boards", [])
    config.setdefault("clusters", {})
    return config


def validate(config: dict[str, Any]) -> None:
    """Бросает ConfigError со списком всех проблем сразу."""
    problems: list[str] = []

    account = config.get("account") or {}
    if not account.get("handle"):
        problems.append("account.handle обязателен (ник аккаунта без @).")
    if not account.get("niche"):
        problems.append("account.niche обязателен — на нём строится вся семантика.")

    boards = config.get("boards") or []
    if not boards:
        problems.append("boards: нужна хотя бы одна доска.")
    seen_keys: set[str] = set()
    for i, board in enumerate(boards):
        prefix = f"boards[{i}]"
        key = board.get("key")
        if not key:
            problems.append(f"{prefix}.key обязателен (латиницей, уникальный).")
        elif key in seen_keys:
            problems.append(f"{prefix}.key='{key}' дублируется.")
        else:
            seen_keys.add(key)
        name = board.get("name", "")
        if not name:
            problems.append(f"{prefix}.name обязателен.")
        elif len(name) > BOARD_NAME_MAX:
            problems.append(
                f"{prefix}.name длиннее {BOARD_NAME_MAX} символов ({len(name)})."
            )
        if len(board.get("description", "")) > BOARD_DESCRIPTION_MAX:
            problems.append(f"{prefix}.description длиннее {BOARD_DESCRIPTION_MAX}.")
        if board.get("privacy", "PUBLIC") not in {"PUBLIC", "PROTECTED", "SECRET"}:
            problems.append(f"{prefix}.privacy: PUBLIC | PROTECTED | SECRET.")
        weight = board.get("weight", 1)
        if not isinstance(weight, int) or weight < 1:
            problems.append(f"{prefix}.weight должен быть целым >= 1.")
        for cluster_key in board.get("clusters", []):
            if cluster_key not in (config.get("clusters") or {}):
                problems.append(
                    f"{prefix}.clusters: кластер '{cluster_key}' не описан в clusters."
                )

    catch_all_board = any(not board.get("clusters") for board in boards)
    led_clusters = {key for board in boards for key in board.get("clusters", [])}
    for cluster_key, cluster in (config.get("clusters") or {}).items():
        prefix = f"clusters.{cluster_key}"
        if not catch_all_board and cluster_key not in led_clusters:
            problems.append(
                f"{prefix}: ни одна доска не ведёт этот кластер — пины по нему некуда публиковать."
            )
        if not cluster.get("head"):
            problems.append(f"{prefix}.head обязателен (главный ключ кластера).")
        terms = cluster.get("terms") or []
        if len(terms) < 3:
            problems.append(
                f"{prefix}.terms: минимум 3 длинных хвоста, иначе описания будут повторяться."
            )

    cadence = config["cadence"]
    if cadence["pins_per_day"] < 1:
        problems.append("cadence.pins_per_day должен быть >= 1.")
    if cadence["pins_per_day"] > len(cadence["slots"]):
        problems.append(
            "cadence.slots: слотов меньше, чем pins_per_day "
            f"({len(cadence['slots'])} < {cadence['pins_per_day']})."
        )
    for slot in cadence["slots"]:
        if not _is_hhmm(slot):
            problems.append(f"cadence.slots: '{slot}' — ожидается формат HH:MM.")
    for day in cadence["days"]:
        if day not in WEEKDAYS:
            problems.append(f"cadence.days: '{day}' — ожидается одно из {WEEKDAYS}.")
    if not cadence["days"]:
        problems.append("cadence.days: нужен хотя бы один день недели.")

    copy_cfg = config["copy"]
    if copy_cfg["title_max"] > PIN_TITLE_MAX:
        problems.append(f"copy.title_max не может быть больше {PIN_TITLE_MAX}.")
    if copy_cfg["description_max"] > PIN_DESCRIPTION_MAX:
        problems.append(f"copy.description_max не может быть больше {PIN_DESCRIPTION_MAX}.")
    if copy_cfg["alt_max"] > PIN_ALT_TEXT_MAX:
        problems.append(f"copy.alt_max не может быть больше {PIN_ALT_TEXT_MAX}.")

    if problems:
        raise ConfigError("Проблемы в конфиге:\n  - " + "\n  - ".join(problems))


def _is_hhmm(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return False
    hours, _, minutes = value.partition(":")
    if not (hours.isdigit() and minutes.isdigit()):
        return False
    return 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59


def board_by_key(config: dict[str, Any], key: str) -> dict[str, Any]:
    for board in config["boards"]:
        if board["key"] == key:
            return board
    raise KeyError(f"Доска '{key}' не найдена в конфиге.")
