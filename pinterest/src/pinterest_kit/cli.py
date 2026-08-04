"""CLI тулкита: `python -m pinterest_kit <команда>` (или `pk` после установки).

Порядок работы в обычную неделю:
    pk validate            — проверить конфиг
    pk plan -i ideas.json  — разложить идеи по датам, доскам и ключам
    pk copy --check        — посмотреть предупреждения по текстам
    pk boards-sync --apply — создать недостающие доски (один раз)
    pk publish --apply     — опубликовать то, чему пришло время
    pk pull && pk report   — снять аналитику и получить отчёт
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import analytics, config as config_module, report as report_module
from .api import AuthError, PinterestClient, PinterestError
from .copywriter import Copywriter
from .keywords import KeywordBank
from .publisher import publish_due, retry_failed, sync_boards
from .scheduler import Scheduler
from .store import STATE_SCHEDULED, Queue

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "account.example.json"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return 1
    try:
        return args.handler(args)
    except config_module.ConfigError as exc:
        print(f"[конфиг] {exc}", file=sys.stderr)
        return 2
    except AuthError as exc:
        print(f"[авторизация] {exc}", file=sys.stderr)
        print("Подсказка: `pk auth-url`, затем `pk auth-exchange <code>`.", file=sys.stderr)
        return 3
    except PinterestError as exc:
        print(f"[api] {exc}", file=sys.stderr)
        return 4
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"[ошибка] {exc}", file=sys.stderr)
        return 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pk", description="Тулкит роста Pinterest-аккаунта: план, тексты, публикация, отчёты."
    )
    parser.add_argument("-c", "--config", default=None, help="путь к account.json")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="создать config/account.json из примера")
    p_init.add_argument("--force", action="store_true", help="перезаписать существующий")
    p_init.set_defaults(handler=cmd_init)

    p_validate = sub.add_parser("validate", help="проверить конфиг и показать ёмкость плана")
    p_validate.set_defaults(handler=cmd_validate)

    p_plan = sub.add_parser("plan", help="разложить идеи по календарю и сгенерировать тексты")
    p_plan.add_argument("-i", "--input", required=True, help="JSON со списком идей")
    p_plan.add_argument("--start", default=None, help="дата старта YYYY-MM-DD (по умолчанию сегодня)")
    p_plan.add_argument("--days", type=int, default=30, help="горизонт планирования, дней")
    p_plan.add_argument("--dry-run", action="store_true", help="не сохранять очередь")
    p_plan.set_defaults(handler=cmd_plan)

    p_copy = sub.add_parser("copy", help="перегенерировать тексты для очереди")
    p_copy.add_argument("--force", action="store_true", help="перезаписать уже готовые тексты")
    p_copy.add_argument("--check", action="store_true", help="только показать предупреждения")
    p_copy.set_defaults(handler=cmd_copy)

    p_status = sub.add_parser("status", help="состояние очереди")
    p_status.add_argument("--state", default=None, help="draft | scheduled | published | failed")
    p_status.add_argument("--limit", type=int, default=20)
    p_status.set_defaults(handler=cmd_status)

    p_calendar = sub.add_parser("calendar", help="показать ближайшие публикации")
    p_calendar.add_argument("--days", type=int, default=7)
    p_calendar.set_defaults(handler=cmd_calendar)

    p_auth_url = sub.add_parser("auth-url", help="ссылка для авторизации приложения")
    p_auth_url.set_defaults(handler=cmd_auth_url)

    p_auth_exchange = sub.add_parser("auth-exchange", help="обменять code на токены")
    p_auth_exchange.add_argument("code")
    p_auth_exchange.set_defaults(handler=cmd_auth_exchange)

    p_auth_check = sub.add_parser("auth-check", help="проверить токен и показать аккаунт")
    p_auth_check.set_defaults(handler=cmd_auth_check)

    p_boards = sub.add_parser("boards-sync", help="сверить доски конфига с аккаунтом")
    p_boards.add_argument("--apply", action="store_true", help="реально создавать недостающие")
    p_boards.set_defaults(handler=cmd_boards_sync)

    p_publish = sub.add_parser("publish", help="опубликовать пины, которым пришло время")
    p_publish.add_argument("--apply", action="store_true", help="без него — сухой прогон")
    p_publish.add_argument("--limit", type=int, default=25)
    p_publish.add_argument("--now", default=None, help="переопределить текущее время (ISO)")
    p_publish.set_defaults(handler=cmd_publish)

    p_retry = sub.add_parser("retry", help="вернуть упавшие пины в очередь")
    p_retry.set_defaults(handler=cmd_retry)

    p_pull = sub.add_parser("pull", help="снять аналитику аккаунта и пинов")
    p_pull.add_argument("--days", type=int, default=30)
    p_pull.add_argument("--pins", type=int, default=50, help="сколько последних пинов опрашивать")
    p_pull.set_defaults(handler=cmd_pull)

    p_report = sub.add_parser("report", help="собрать Markdown-отчёт из последнего снапшота")
    p_report.add_argument("-o", "--out", default="data/report.md")
    p_report.set_defaults(handler=cmd_report)

    return parser


# ----------------------------------------------------------------- команды


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.config or config_module.DEFAULT_CONFIG_PATH)
    if target.exists() and not args.force:
        print(f"{target} уже существует (--force чтобы перезаписать).")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(EXAMPLE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Создан {target}. Заполните account, boards и clusters под свою нишу.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    config = config_module.load(args.config)
    scheduler = Scheduler(config)
    capacity_30 = scheduler.capacity(date.today(), 30)
    bank = KeywordBank.from_config(config)
    terms = sum(len(bank.terms(k)) for k in bank.keys())

    print("Конфиг валиден.")
    print(f"  аккаунт:   @{config['account'].get('handle')} — {config['account'].get('niche')}")
    print(f"  досок:     {len(config['boards'])}")
    print(f"  кластеров: {len(bank.keys())} ({terms} термов)")
    print(f"  ёмкость:   {capacity_30} пинов за 30 дней "
          f"({config['cadence']['pins_per_day']}/день × {len(scheduler.publish_days(date.today(), 30))} дн.)")
    if terms < capacity_30 / 4:
        print("  ! термов мало относительно объёма публикаций — описания начнут повторяться")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    config = config_module.load(args.config)
    ideas = _read_ideas(Path(args.input))
    queue = Queue.load()
    added, updated = queue.upsert(ideas)

    pending = [
        item for item in queue.items
        if item.get("state") in {None, "draft"} or not item.get("publish_at")
    ]
    start = date.fromisoformat(args.start) if args.start else date.today()
    scheduler = Scheduler(config)
    scheduled, overflow = scheduler.build(pending, start, args.days)

    writer = Copywriter(config)
    warnings_total = 0
    for slot in scheduled:
        item = queue.by_id(slot.item_id)
        item.update(
            {
                "board": slot.board_key,
                "cluster": slot.cluster,
                "publish_at": slot.publish_at,
                "state": STATE_SCHEDULED,
            }
        )
        copy = writer.build(item)
        item["copy"] = copy.to_dict()
        warnings_total += len(copy.warnings)

    print(f"Идей на входе: {len(ideas)} (новых {added}, обновлено {updated}).")
    print(f"Запланировано: {len(scheduled)} на {args.days} дн. с {start.isoformat()}.")
    if overflow:
        print(f"Не влезло в окно: {len(overflow)} — увеличьте --days или pins_per_day.")
    if warnings_total:
        print(f"Предупреждений по текстам: {warnings_total} (подробности — `pk copy --check`).")

    balance = scheduler.cluster_balance(scheduled)
    idle = [key for key, stats in balance.items() if stats["pins"] == 0]
    if idle:
        print("Кластеры без пинов в этом плане: " + ", ".join(idle))

    if args.dry_run:
        print("(--dry-run: очередь не сохранена)")
        return 0
    queue.save()
    print(f"Очередь сохранена: {queue.path}")
    return 0


def cmd_copy(args: argparse.Namespace) -> int:
    config = config_module.load(args.config)
    queue = Queue.load()
    writer = Copywriter(config)
    rebuilt = 0
    issues: list[tuple[str, list[str]]] = []

    for item in queue.items:
        if not item.get("cluster"):
            continue
        if item.get("copy") and not (args.force or args.check):
            continue
        copy = writer.build(item)
        if not args.check:
            item["copy"] = copy.to_dict()
            rebuilt += 1
        if copy.warnings:
            issues.append((str(item["id"]), copy.warnings))

    for item_id, warnings in issues:
        print(f"{item_id}:")
        for warning in warnings:
            print(f"  - {warning}")

    if args.check:
        print(f"\nПроверено: {len(queue.items)}, с замечаниями: {len(issues)}.")
        return 0
    queue.save()
    print(f"Тексты пересобраны для {rebuilt} элементов.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    queue = Queue.load()
    counts = queue.counts()
    print("Очередь: " + ", ".join(f"{state}={count}" for state, count in counts.items()))
    items = queue.filter(args.state)
    items.sort(key=lambda item: item.get("publish_at") or "")
    for item in items[: args.limit]:
        copy = item.get("copy") or {}
        marker = "!" if item.get("state") == "failed" else " "
        print(
            f"{marker} {item.get('publish_at', '—'):<19} {item.get('board', '—'):<14} "
            f"{item.get('cluster', '—'):<16} {copy.get('title', '(без текста)')[:60]}"
        )
        if item.get("error"):
            print(f"    ошибка: {item['error']}")
    if len(items) > args.limit:
        print(f"… ещё {len(items) - args.limit}")
    return 0


def cmd_calendar(args: argparse.Namespace) -> int:
    queue = Queue.load()
    horizon = (datetime.now().date().toordinal() + args.days)
    by_day: dict[str, list[dict[str, Any]]] = {}
    for item in queue.filter(STATE_SCHEDULED):
        publish_at = item.get("publish_at")
        if not publish_at:
            continue
        day = publish_at[:10]
        if date.fromisoformat(day).toordinal() > horizon:
            continue
        by_day.setdefault(day, []).append(item)

    for day in sorted(by_day):
        print(f"\n{day} ({len(by_day[day])} пинов)")
        for item in sorted(by_day[day], key=lambda i: i["publish_at"]):
            copy = item.get("copy") or {}
            print(
                f"  {item['publish_at'][11:16]}  {item.get('board', '—'):<14} "
                f"{copy.get('title', '(без текста)')[:60]}"
            )
    if not by_day:
        print("На ближайшие дни ничего не запланировано.")
    return 0


def cmd_auth_url(args: argparse.Namespace) -> int:
    client = PinterestClient()
    print(client.authorization_url(state="pk"))
    print("\nОткройте ссылку, подтвердите доступ и скопируйте параметр `code` из redirect URL.")
    return 0


def cmd_auth_exchange(args: argparse.Namespace) -> int:
    client = PinterestClient()
    record = client.exchange_code(args.code)
    print(f"Токен получен, действителен до {record['expires_at']}.")
    print(f"Скоупы: {record.get('scope') or '—'}")
    return 0


def cmd_auth_check(args: argparse.Namespace) -> int:
    client = PinterestClient()
    account = client.get_user_account()
    mode = "SANDBOX" if client.sandbox else "PRODUCTION"
    print(f"[{mode}] @{account.get('username')} — {account.get('account_type', '?')}")
    for field in ("follower_count", "following_count", "pin_count", "board_count"):
        if field in account:
            print(f"  {field}: {account[field]}")
    if client.last_rate_limit:
        print(f"  лимиты: {client.last_rate_limit}")
    return 0


def cmd_boards_sync(args: argparse.Namespace) -> int:
    config = config_module.load(args.config)
    client = PinterestClient()
    mapping, actions = sync_boards(client, config, apply=args.apply)
    if actions:
        print(("Выполнено:" if args.apply else "Будет сделано (--apply чтобы применить):"))
        for action in actions:
            print(f"  - {action}")
    else:
        print("Все доски уже на месте.")
    print(f"Сопоставлено досок: {len(mapping)}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    config = config_module.load(args.config)
    queue = Queue.load()
    client = PinterestClient()
    now = datetime.fromisoformat(args.now) if args.now else None
    log = publish_due(client, config, queue, now=now, apply=args.apply, limit=args.limit)

    if not log:
        print("Нечего публиковать: нет элементов с наступившим временем.")
        return 0
    published = sum(1 for entry in log if entry["status"] == "published")
    errors = [entry for entry in log if entry["status"] == "error"]
    for entry in log:
        print(f"  [{entry['status']}] {entry['id']} — {entry.get('title', '')[:60]}")
        if entry.get("error"):
            print(f"      {entry['error']}")
    if not args.apply:
        print(f"\nСухой прогон: {len(log)} пинов готовы к публикации. Добавьте --apply.")
    else:
        print(f"\nОпубликовано: {published}, ошибок: {len(errors)}.")
    return 0 if not errors else 6


def cmd_retry(args: argparse.Namespace) -> int:
    queue = Queue.load()
    count = retry_failed(queue)
    print(f"Возвращено в очередь: {count}.")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    config_module.load(args.config)  # ранняя проверка конфига
    queue = Queue.load()
    client = PinterestClient()
    snapshot = analytics.pull(client, queue, days=args.days, pin_limit=args.pins)
    total = analytics.totals(snapshot["account_rows"])
    print(f"Окно {snapshot['window']['start']} → {snapshot['window']['end']}:")
    for metric, value in sorted(total.items(), key=lambda kv: -kv[1]):
        print(f"  {metric}: {value:,.0f}".replace(",", " "))
    print(f"Пинов опрошено: {len({row['pin_id'] for row in snapshot['pin_rows']})}, "
          f"ошибок: {len(snapshot['errors'])}.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .store import load_snapshots

    config = config_module.load(args.config)
    snapshots = load_snapshots()
    if not snapshots:
        print("Нет снапшотов аналитики — сначала `pk pull`.", file=sys.stderr)
        return 1
    queue = Queue.load()
    markdown = report_module.render(config, snapshots[-1], queue)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\n(сохранено в {out_path})")
    return 0


def _read_ideas(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Файл идей не найден: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    ideas = payload["items"] if isinstance(payload, dict) else payload
    for i, idea in enumerate(ideas):
        if "id" not in idea:
            raise ValueError(f"ideas[{i}]: нет поля id")
        if "hook" not in idea:
            raise ValueError(f"ideas[{i}] ({idea['id']}): нет поля hook")
    return ideas


if __name__ == "__main__":
    raise SystemExit(main())
