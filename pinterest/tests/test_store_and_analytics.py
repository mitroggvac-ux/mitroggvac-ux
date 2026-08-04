import json

from pinterest_kit import analytics
from pinterest_kit.store import STATE_PUBLISHED, STATE_SCHEDULED, Queue


def make_queue(tmp_path, items):
    queue = Queue(items=items, path=tmp_path / "queue.json")
    queue.save()
    return Queue.load(tmp_path / "queue.json")


def test_queue_roundtrip_and_counts(tmp_path):
    queue = make_queue(
        tmp_path,
        [
            {"id": "a", "state": STATE_SCHEDULED, "publish_at": "2026-08-05T09:00:00"},
            {"id": "b", "state": STATE_PUBLISHED, "pin_id": "1"},
        ],
    )
    assert queue.counts()["scheduled"] == 1
    assert queue.by_id("b")["pin_id"] == "1"


def test_upsert_updates_existing_and_adds_new(tmp_path):
    queue = make_queue(tmp_path, [{"id": "a", "hook": "старый"}])
    added, updated = queue.upsert([{"id": "a", "hook": "новый"}, {"id": "b", "hook": "b"}])
    assert (added, updated) == (1, 1)
    assert queue.by_id("a")["hook"] == "новый"
    assert queue.by_id("b")["state"] == "draft"


def test_due_returns_only_past_items_in_order(tmp_path):
    queue = make_queue(
        tmp_path,
        [
            {"id": "later", "state": STATE_SCHEDULED, "publish_at": "2026-08-10T09:00:00"},
            {"id": "now", "state": STATE_SCHEDULED, "publish_at": "2026-08-01T09:00:00"},
            {"id": "mid", "state": STATE_SCHEDULED, "publish_at": "2026-08-04T09:00:00"},
        ],
    )
    due = queue.due("2026-08-05T00:00:00")
    assert [item["id"] for item in due] == ["now", "mid"]


def test_normalize_account_handles_nested_and_flat_shapes():
    nested = {
        "all": {
            "daily_metrics": [
                {"date": "2026-08-01", "metrics": {"IMPRESSION": 100, "SAVE": 5}},
                {"date": "2026-08-02", "metrics": {"IMPRESSION": 150, "SAVE": 9}},
            ]
        }
    }
    flat = {
        "daily_metrics": [{"date": "2026-08-01", "metrics": {"IMPRESSION": 42}}],
    }
    assert len(analytics.normalize_account(nested)) == 4
    assert analytics.totals(analytics.normalize_account(nested))["IMPRESSION"] == 250
    assert analytics.totals(analytics.normalize_account(flat))["IMPRESSION"] == 42


def test_normalize_account_ignores_non_numeric_metrics():
    payload = {"all": {"daily_metrics": [{"date": "2026-08-01", "metrics": {"IMPRESSION": 10, "DATA_STATUS": "READY"}}]}}
    rows = analytics.normalize_account(payload)
    assert {row["metric"] for row in rows} == {"IMPRESSION"}


def test_split_and_growth():
    rows = [
        {"date": "2026-08-01", "metric": "IMPRESSION", "value": 100},
        {"date": "2026-08-10", "metric": "IMPRESSION", "value": 150},
    ]
    before, after = analytics.split_periods(rows, "2026-08-05")
    assert before["IMPRESSION"] == 100 and after["IMPRESSION"] == 150
    assert analytics.growth(before, after)["IMPRESSION"] == 50.0
    assert analytics.growth({}, {"SAVE": 3})["SAVE"] == 100.0


def test_rates():
    metrics = {"IMPRESSION": 1000, "SAVE": 12, "OUTBOUND_CLICK": 4}
    assert analytics.save_rate(metrics) == 1.2
    assert analytics.click_rate(metrics) == 0.4
    assert analytics.save_rate({}) == 0.0


def test_by_cluster_maps_pins_to_clusters(tmp_path):
    queue = make_queue(
        tmp_path,
        [
            {"id": "a", "pin_id": "p1", "cluster": "beaches", "state": STATE_PUBLISHED},
            {"id": "b", "pin_id": "p2", "cluster": "beaches", "state": STATE_PUBLISHED},
            {"id": "c", "pin_id": "p3", "cluster": "food", "state": STATE_PUBLISHED},
        ],
    )
    rows = [
        {"pin_id": "p1", "metric": "IMPRESSION", "value": 100},
        {"pin_id": "p2", "metric": "IMPRESSION", "value": 50},
        {"pin_id": "p3", "metric": "IMPRESSION", "value": 700},
    ]
    result = analytics.by_cluster(queue, rows)
    assert result["beaches"]["IMPRESSION"] == 150
    assert result["beaches"]["pins"] == 2
    assert result["food"]["IMPRESSION"] == 700


def test_date_window_is_inclusive():
    from datetime import date

    start, end = analytics.date_window(7, today=date(2026, 8, 10))
    assert (start, end) == ("2026-08-04", "2026-08-10")


def test_snapshot_written_as_json(tmp_path):
    from pinterest_kit.store import save_snapshot

    path = save_snapshot("2026-08-10-30d", {"window": {}}, directory=tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"window": {}}
