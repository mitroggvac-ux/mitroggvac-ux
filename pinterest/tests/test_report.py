from datetime import date

from pinterest_kit import report
from pinterest_kit.store import Queue


def snapshot(impressions_first=1000, impressions_second=3000, saves=40, clicks=10):
    return {
        "window": {"start": "2026-07-12", "end": "2026-08-10", "days": 30},
        "account_rows": [
            {"date": "2026-07-14", "metric": "IMPRESSION", "value": impressions_first},
            {"date": "2026-08-05", "metric": "IMPRESSION", "value": impressions_second},
            {"date": "2026-08-05", "metric": "SAVE", "value": saves},
            {"date": "2026-08-05", "metric": "OUTBOUND_CLICK", "value": clicks},
        ],
        "pin_rows": [
            {"pin_id": "p1", "metric": "IMPRESSION", "value": 2500},
            {"pin_id": "p1", "metric": "SAVE", "value": 35},
            {"pin_id": "p2", "metric": "IMPRESSION", "value": 500},
            {"pin_id": "p2", "metric": "SAVE", "value": 1},
        ],
        "errors": [],
    }


def queue_with_pins(tmp_path):
    return Queue(
        items=[
            {"id": "a", "pin_id": "p1", "cluster": "beaches", "state": "published"},
            {"id": "b", "pin_id": "p2", "cluster": "food", "state": "published"},
            {"id": "c", "cluster": "beaches", "state": "scheduled", "publish_at": "2026-08-11T09:00"},
        ],
        path=tmp_path / "queue.json",
    )


def test_report_contains_core_sections(config, tmp_path):
    markdown = report.render(config, snapshot(), queue_with_pins(tmp_path), today=date(2026, 8, 11))
    assert "# Pinterest: отчёт по росту — @test_handle" in markdown
    assert "## Сводка за окно" in markdown
    assert "## Цели месяца" in markdown
    assert "## Кластеры ключей" in markdown
    assert "## Что делать дальше" in markdown


def test_growth_direction_is_reported(config, tmp_path):
    markdown = report.render(config, snapshot(), queue_with_pins(tmp_path))
    assert "Показы растут" in markdown

    stalled = snapshot(impressions_first=3000, impressions_second=3050)
    markdown = report.render(config, stalled, queue_with_pins(tmp_path))
    assert "Показы почти не растут" in markdown


def test_low_save_rate_triggers_creative_advice(config, tmp_path):
    weak = snapshot(saves=2)
    markdown = report.render(config, weak, queue_with_pins(tmp_path))
    assert "ниже порога" in markdown


def test_idle_clusters_are_listed(config, tmp_path):
    markdown = report.render(config, snapshot(), queue_with_pins(tmp_path))
    assert "Кластеры без единого пина" in markdown
    assert "`routes`" in markdown


def test_thin_queue_is_flagged(config, tmp_path):
    markdown = report.render(config, snapshot(), queue_with_pins(tmp_path))
    assert "В очереди осталось" in markdown


def test_empty_metrics_give_actionable_message(config, tmp_path):
    empty = {"window": {"start": "2026-07-12", "end": "2026-08-10", "days": 30},
             "account_rows": [], "pin_rows": [], "errors": []}
    markdown = report.render(config, empty, queue_with_pins(tmp_path))
    assert "Данных нет" in markdown


def test_pull_errors_are_surfaced(config, tmp_path):
    payload = snapshot()
    payload["errors"] = [{"pin_id": "p9", "error": "404"}]
    markdown = report.render(config, payload, queue_with_pins(tmp_path))
    assert "## Не собралось" in markdown and "p9" in markdown
