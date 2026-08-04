from collections import Counter
from datetime import date, datetime

from pinterest_kit.scheduler import Scheduler


START = date(2026, 8, 3)  # понедельник


def test_capacity_matches_days_times_volume(config):
    config["cadence"]["days"] = ["mon", "wed", "fri"]
    scheduler = Scheduler(config)
    assert len(scheduler.publish_days(START, 7)) == 3
    assert scheduler.capacity(START, 7) == 3 * config["cadence"]["pins_per_day"]


def test_all_items_scheduled_when_window_is_large_enough(config, ideas):
    scheduled, overflow = Scheduler(config).build(ideas, START, days=14)
    assert len(scheduled) == len(ideas)
    assert overflow == []


def test_overflow_returned_when_window_too_small(config, ideas):
    config["cadence"]["pins_per_day"] = 1
    config["cadence"]["slots"] = ["09:00"]
    scheduled, overflow = Scheduler(config).build(ideas, START, days=3)
    assert len(scheduled) == 3
    assert len(overflow) == len(ideas) - 3


def test_daily_board_limit_is_respected(config, ideas):
    scheduled, _ = Scheduler(config).build(ideas, START, days=14)
    per_day_board = Counter((item.publish_at[:10], item.board_key) for item in scheduled)
    assert max(per_day_board.values()) <= config["cadence"]["max_per_board_per_day"]


def test_min_gap_between_pins_is_respected(config, ideas):
    config["cadence"]["min_gap_minutes"] = 150
    scheduled, _ = Scheduler(config).build(ideas, START, days=21)
    by_day: dict[str, list[datetime]] = {}
    for item in scheduled:
        stamp = datetime.fromisoformat(item.publish_at)
        by_day.setdefault(item.publish_at[:10], []).append(stamp)
    for stamps in by_day.values():
        stamps.sort()
        gaps = [
            (b - a).total_seconds() / 60 for a, b in zip(stamps, stamps[1:])
        ]
        assert all(gap >= 150 for gap in gaps)


def test_only_allowed_weekdays_are_used(config, ideas):
    config["cadence"]["days"] = ["tue", "thu"]
    scheduled, _ = Scheduler(config).build(ideas, START, days=28)
    weekdays = {date.fromisoformat(item.publish_at[:10]).weekday() for item in scheduled}
    assert weekdays <= {1, 3}


def test_board_weight_shifts_rotation(config, ideas):
    scheduled, _ = Scheduler(config).build(ideas, START, days=21)
    counts = Counter(item.board_key for item in scheduled)
    # beaches имеет weight 3, relocation — 1
    assert counts["beaches"] >= counts["relocation"]


def test_item_lands_on_board_that_leads_its_cluster(config, ideas):
    scheduled, _ = Scheduler(config).build(ideas, START, days=21)
    allowed = {
        board["key"]: set(board.get("clusters") or config["clusters"])
        for board in config["boards"]
    }
    for item in scheduled:
        assert item.cluster in allowed[item.board_key], (
            f"{item.cluster} попал на доску {item.board_key}"
        )


def test_cluster_without_board_raises(config, ideas):
    for board in config["boards"]:
        board["clusters"] = ["beaches"]
    try:
        Scheduler(config).build(ideas, START, days=14)
    except ValueError as exc:
        assert "Нет доски для кластеров" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ожидалась ValueError")


def test_explicit_board_on_item_wins(config, ideas):
    ideas[0]["board"] = "food"
    scheduled, _ = Scheduler(config).build(ideas, START, days=14)
    assert next(s for s in scheduled if s.item_id == ideas[0]["id"]).board_key == "food"


def test_schedule_is_reproducible(config, ideas):
    import copy as copy_module

    first, _ = Scheduler(config).build(copy_module.deepcopy(ideas), START, days=14)
    second, _ = Scheduler(config).build(copy_module.deepcopy(ideas), START, days=14)
    assert [s.to_dict() for s in first] == [s.to_dict() for s in second]


def test_cluster_balance_reports_every_cluster(config, ideas):
    scheduler = Scheduler(config)
    scheduled, _ = scheduler.build(ideas, START, days=14)
    balance = scheduler.cluster_balance(scheduled)
    assert set(balance) == set(config["clusters"])
    assert sum(stats["pins"] for stats in balance.values()) == len(scheduled)
