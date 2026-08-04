import io
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from pinterest_kit import api as api_module, publisher, store
from pinterest_kit.api import AuthError, PinterestClient, PinterestError, TokenStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return PinterestClient(
        app_id="app",
        app_secret="secret",
        redirect_uri="https://example.com/cb",
        sandbox=True,
        store=TokenStore(tmp_path / "token.json"),
        max_retries=3,
    )


def _authorize(client, expires_in=3600):
    return client.store.save(
        {"access_token": "pina_x", "refresh_token": "pinr_y", "expires_in": expires_in}
    )


def test_authorization_url_contains_required_params(client):
    url = client.authorization_url(state="pk")
    assert url.startswith("https://www.pinterest.com/oauth/?")
    assert "client_id=app" in url and "response_type=code" in url and "state=pk" in url
    assert "boards%3Awrite" in url or "boards:write" in url


def test_authorization_url_without_credentials_fails():
    with pytest.raises(AuthError):
        PinterestClient(app_id="", redirect_uri="").authorization_url()


def test_token_store_marks_expired_tokens(client):
    assert client.store.is_expired() is True
    _authorize(client, expires_in=3600)
    assert client.store.is_expired() is False
    _authorize(client, expires_in=60)  # меньше запаса в 5 минут
    assert client.store.is_expired() is True


def test_token_store_keeps_refresh_token_when_response_omits_it(client):
    _authorize(client)
    client.store.save({"access_token": "pina_new", "expires_in": 100})
    assert client.store.load()["refresh_token"] == "pinr_y"


def test_sandbox_base_url_is_used(client):
    assert client.base == api_module.SANDBOX_BASE


def test_missing_token_raises_auth_error(client):
    with pytest.raises(AuthError):
        client.get_user_account()


class FakeResponse(io.BytesIO):
    def __init__(self, payload, headers=None):
        super().__init__(json.dumps(payload).encode())
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_retries_on_429_then_succeeds(client, monkeypatch):
    _authorize(client)
    monkeypatch.setattr(api_module.time, "sleep", lambda _: None)
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", {"Retry-After": "1"}, io.BytesIO(b"{}")
            )
        return FakeResponse({"username": "test"}, {"X-Ratelimit-Remaining": "990"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert client.get_user_account()["username"] == "test"
    assert calls["n"] == 3
    assert client.last_rate_limit["X-Ratelimit-Remaining"] == "990"


def test_gives_up_after_max_retries(client, monkeypatch):
    _authorize(client)
    monkeypatch.setattr(api_module.time, "sleep", lambda _: None)

    def always_503(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 503, "nope", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(urllib.request, "urlopen", always_503)
    with pytest.raises(PinterestError) as exc:
        client.get_user_account()
    assert exc.value.status == 503


def test_400_is_not_retried(client, monkeypatch):
    _authorize(client)
    calls = {"n": 0}

    def bad_request(request, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"message": "board_id required"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", bad_request)
    with pytest.raises(PinterestError, match="board_id required"):
        client.get_user_account()
    assert calls["n"] == 1


def test_paginate_follows_bookmark(client, monkeypatch):
    _authorize(client)
    pages = [
        {"items": [{"id": "1"}], "bookmark": "b1"},
        {"items": [{"id": "2"}], "bookmark": None},
    ]

    def fake_urlopen(request, timeout=None):
        return FakeResponse(pages.pop(0))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert [item["id"] for item in client.list_boards()] == ["1", "2"]


def test_image_file_source_detects_content_type(tmp_path):
    path = tmp_path / "pin.png"
    path.write_bytes(b"fake-bytes")
    source = api_module.image_file_source(path)
    assert source["source_type"] == "image_base64"
    assert source["content_type"] == "image/png"


# ------------------------------------------------------------- publisher


class FakeClient:
    def __init__(self, boards=None, fail_on=None):
        self.boards = boards or []
        self.created_pins = []
        self.created_boards = []
        self.fail_on = fail_on or set()

    def list_boards(self):
        return self.boards

    def create_board(self, name, description="", privacy="PUBLIC"):
        board = {"id": f"board-{len(self.created_boards) + 1}", "name": name}
        self.created_boards.append(board)
        self.boards.append(board)
        return board

    def list_board_sections(self, board_id):
        return []

    def create_board_section(self, board_id, name):
        return {"id": f"section-{name}"}

    def create_pin(self, **kwargs):
        if kwargs["title"] in self.fail_on:
            raise PinterestError(400, {"message": "media_source invalid"}, "/pins")
        self.created_pins.append(kwargs)
        return {"id": f"pin-{len(self.created_pins)}"}


def _queue_with_one_due(tmp_path, **overrides):
    item = {
        "id": "a",
        "state": "scheduled",
        "publish_at": "2026-08-01T09:00:00",
        "board": "beaches",
        "cluster": "beaches",
        "image": "https://cdn.example.com/a.jpg",
        "copy": {
            "title": "Пляжи Кипра: 7 тихих бухт",
            "description": "Описание пина.",
            "alt_text": "Бухта",
            "link": "https://example.com/a",
        },
    }
    item.update(overrides)
    queue = store.Queue(items=[item], path=tmp_path / "queue.json")
    queue.save()
    return queue


def test_boards_sync_dry_run_creates_nothing(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = FakeClient()
    mapping, actions = publisher.sync_boards(client, config, apply=False)
    assert client.created_boards == []
    assert len(actions) >= len(config["boards"])
    assert not (tmp_path / "data" / "boards.json").exists()


def test_boards_sync_apply_creates_missing_and_saves_map(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    existing = {"id": "remote-1", "name": "Пляжи Кипра"}
    client = FakeClient(boards=[existing])
    mapping, _ = publisher.sync_boards(client, config, apply=True)
    assert mapping["beaches"]["board_id"] == "remote-1"
    assert len(client.created_boards) == len(config["boards"]) - 1
    assert store.load_board_map()["food"]["board_id"]


def test_publish_dry_run_does_not_touch_api(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store.save_board_map({"beaches": {"board_id": "b1", "sections": {}}})
    queue = _queue_with_one_due(tmp_path)
    client = FakeClient()
    log = publisher.publish_due(
        client, config, queue, now=datetime(2026, 8, 2), apply=False
    )
    assert log[0]["status"] == "dry-run"
    assert client.created_pins == []
    assert queue.by_id("a")["state"] == "scheduled"


def test_publish_apply_marks_item_published(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store.save_board_map({"beaches": {"board_id": "b1", "sections": {}}})
    queue = _queue_with_one_due(tmp_path)
    client = FakeClient()
    log = publisher.publish_due(client, config, queue, now=datetime(2026, 8, 2), apply=True)
    assert log[0]["status"] == "published"
    item = store.Queue.load(queue.path).by_id("a")
    assert item["state"] == "published" and item["pin_id"] == "pin-1"
    assert client.created_pins[0]["board_id"] == "b1"


def test_publish_skips_future_items(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store.save_board_map({"beaches": {"board_id": "b1", "sections": {}}})
    queue = _queue_with_one_due(tmp_path, publish_at="2026-09-01T09:00:00")
    log = publisher.publish_due(FakeClient(), config, queue, now=datetime(2026, 8, 2), apply=True)
    assert log == []


def test_publish_records_error_without_stopping(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store.save_board_map({"beaches": {"board_id": "b1", "sections": {}}})
    queue = _queue_with_one_due(tmp_path)
    client = FakeClient(fail_on={"Пляжи Кипра: 7 тихих бухт"})
    log = publisher.publish_due(client, config, queue, now=datetime(2026, 8, 2), apply=True)
    assert log[0]["status"] == "error"
    item = store.Queue.load(queue.path).by_id("a")
    assert item["state"] == "failed" and "media_source invalid" in item["error"]


def test_publish_requires_synced_board(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    queue = _queue_with_one_due(tmp_path)
    log = publisher.publish_due(FakeClient(), config, queue, now=datetime(2026, 8, 2), apply=True)
    assert "boards-sync" in log[0]["error"]


def test_publish_requires_local_file_to_exist(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store.save_board_map({"beaches": {"board_id": "b1", "sections": {}}})
    queue = _queue_with_one_due(tmp_path, image="assets/pins/missing.jpg")
    log = publisher.publish_due(FakeClient(), config, queue, now=datetime(2026, 8, 2), apply=True)
    assert "файл не найден" in log[0]["error"]


def test_retry_failed_returns_items_to_queue(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    queue = store.Queue(
        items=[
            {"id": "a", "state": "failed", "error": "boom"},
            {"id": "b", "state": "failed", "pin_id": "pin-9"},
        ],
        path=tmp_path / "queue.json",
    )
    assert publisher.retry_failed(queue) == 1
    assert queue.by_id("a")["state"] == "scheduled"
    assert queue.by_id("b")["state"] == "published"


def test_token_file_permissions_are_private(client):
    import os
    import stat

    _authorize(client)
    mode = stat.S_IMODE(os.stat(client.store.path).st_mode)
    assert mode == 0o600
