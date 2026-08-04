"""Тонкий клиент Pinterest API v5 на stdlib.

Покрывает то, что нужно для роста аккаунта: OAuth с автообновлением токена,
доски и секции, создание пинов, аналитика аккаунта и отдельных пинов.

Аутентификация (см. docs/01-account-setup.md):
    PINTEREST_APP_ID, PINTEREST_APP_SECRET, PINTEREST_REDIRECT_URI
Песочница включается PINTEREST_SANDBOX=1 — в ней пины не публикуются наружу.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API_BASE = "https://api.pinterest.com/v5"
SANDBOX_BASE = "https://api-sandbox.pinterest.com/v5"
AUTH_URL = "https://www.pinterest.com/oauth/"

DEFAULT_SCOPES = [
    "user_accounts:read",
    "boards:read",
    "boards:write",
    "pins:read",
    "pins:write",
]

TOKEN_PATH = Path("data/token.json")
RETRY_STATUSES = {429, 500, 502, 503, 504}


class PinterestError(RuntimeError):
    def __init__(self, status: int, payload: Any, path: str):
        self.status = status
        self.payload = payload
        self.path = path
        message = payload.get("message") if isinstance(payload, dict) else payload
        super().__init__(f"Pinterest API {status} на {path}: {message}")


class AuthError(PinterestError):
    """Токена нет, он истёк или отозван."""


class TokenStore:
    """Хранит токены в JSON-файле. Файл содержит секреты — держите его вне git."""

    def __init__(self, path: Path = TOKEN_PATH):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        expires_in = int(payload.get("expires_in", 0))
        record = {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", self.load().get("refresh_token", "")),
            "scope": payload.get("scope", ""),
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(self.path, 0o600)
        return record

    def is_expired(self, skew_seconds: int = 300) -> bool:
        record = self.load()
        if not record.get("access_token"):
            return True
        expires_at = record.get("expires_at")
        if not expires_at:
            return True
        deadline = datetime.fromisoformat(expires_at) - timedelta(seconds=skew_seconds)
        return datetime.now(timezone.utc) >= deadline


class PinterestClient:
    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        redirect_uri: str | None = None,
        sandbox: bool | None = None,
        store: TokenStore | None = None,
        max_retries: int = 4,
    ):
        self.app_id = app_id or os.environ.get("PINTEREST_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("PINTEREST_APP_SECRET", "")
        self.redirect_uri = redirect_uri or os.environ.get("PINTEREST_REDIRECT_URI", "")
        if sandbox is None:
            sandbox = os.environ.get("PINTEREST_SANDBOX", "") not in {"", "0", "false"}
        self.base = SANDBOX_BASE if sandbox else API_BASE
        self.sandbox = sandbox
        self.store = store or TokenStore()
        self.max_retries = max_retries
        self.last_rate_limit: dict[str, str] = {}

    # ---------------------------------------------------------------- OAuth

    def authorization_url(self, scopes: list[str] | None = None, state: str = "") -> str:
        if not self.app_id or not self.redirect_uri:
            raise AuthError(0, "нет PINTEREST_APP_ID или PINTEREST_REDIRECT_URI", AUTH_URL)
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": ",".join(scopes or DEFAULT_SCOPES),
        }
        if state:
            params["state"] = state
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        """Обменивает код из redirect_uri на пару токенов."""
        return self.store.save(
            self._token_request(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "continuous_refresh": "true",
                }
            )
        )

    def refresh(self) -> dict[str, Any]:
        refresh_token = self.store.load().get("refresh_token")
        if not refresh_token:
            raise AuthError(401, "нет refresh_token — пройдите авторизацию заново", "/oauth/token")
        return self.store.save(
            self._token_request(
                {"grant_type": "refresh_token", "refresh_token": refresh_token}
            )
        )

    def access_token(self) -> str:
        if self.store.is_expired():
            self.refresh()
        token = self.store.load().get("access_token")
        if not token:
            raise AuthError(401, "токен не найден — выполните `auth-url` и `auth-exchange`", "/oauth/token")
        return token

    def _token_request(self, body: dict[str, str]) -> dict[str, Any]:
        if not self.app_id or not self.app_secret:
            raise AuthError(0, "нет PINTEREST_APP_ID / PINTEREST_APP_SECRET", "/oauth/token")
        basic = base64.b64encode(f"{self.app_id}:{self.app_secret}".encode()).decode()
        request = urllib.request.Request(
            f"{self.base}/oauth/token",
            data=urllib.parse.urlencode(body).encode(),
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        return self._send(request, "/oauth/token")

    # -------------------------------------------------------------- запросы

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}, doseq=True
            )
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method=method,
        )
        return self._send(request, path)

    def _send(self, request: urllib.request.Request, path: str) -> Any:
        delay = 2.0
        last_error: PinterestError | None = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    self._remember_rate_limit(response.headers)
                    raw = response.read().decode("utf-8") or "{}"
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                payload = _read_error(exc)
                self._remember_rate_limit(exc.headers)
                if exc.code in {401, 403}:
                    raise AuthError(exc.code, payload, path) from exc
                last_error = PinterestError(exc.code, payload, path)
                if exc.code not in RETRY_STATUSES or attempt == self.max_retries - 1:
                    raise last_error from exc
                time.sleep(_retry_after(exc.headers, delay))
                delay *= 2
            except urllib.error.URLError as exc:
                last_error = PinterestError(0, f"сеть недоступна: {exc.reason}", path)
                if attempt == self.max_retries - 1:
                    raise last_error from exc
                time.sleep(delay)
                delay *= 2
        raise last_error or PinterestError(0, "неизвестная ошибка", path)

    def _remember_rate_limit(self, headers: Any) -> None:
        for key in ("X-Ratelimit-Limit", "X-Ratelimit-Remaining", "X-Ratelimit-Reset"):
            value = headers.get(key)
            if value:
                self.last_rate_limit[key] = value

    def paginate(self, path: str, params: dict[str, Any] | None = None, limit: int = 250) -> list[dict[str, Any]]:
        """Собирает items со всех страниц (Pinterest отдаёт курсор в поле bookmark)."""
        collected: list[dict[str, Any]] = []
        query = dict(params or {})
        query.setdefault("page_size", 100)
        while len(collected) < limit:
            page = self.request("GET", path, params=query)
            collected.extend(page.get("items", []))
            bookmark = page.get("bookmark")
            if not bookmark:
                break
            query["bookmark"] = bookmark
        return collected[:limit]

    # -------------------------------------------------------------- ресурсы

    def get_user_account(self) -> dict[str, Any]:
        return self.request("GET", "/user_account")

    def list_boards(self) -> list[dict[str, Any]]:
        return self.paginate("/boards")

    def create_board(self, name: str, description: str = "", privacy: str = "PUBLIC") -> dict[str, Any]:
        return self.request(
            "POST",
            "/boards",
            body={"name": name, "description": description, "privacy": privacy},
        )

    def list_board_sections(self, board_id: str) -> list[dict[str, Any]]:
        return self.paginate(f"/boards/{board_id}/sections")

    def create_board_section(self, board_id: str, name: str) -> dict[str, Any]:
        return self.request("POST", f"/boards/{board_id}/sections", body={"name": name})

    def create_pin(
        self,
        board_id: str,
        title: str,
        description: str,
        media_source: dict[str, Any],
        link: str = "",
        alt_text: str = "",
        board_section_id: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "board_id": board_id,
            "title": title,
            "description": description,
            "media_source": media_source,
        }
        if link:
            body["link"] = link
        if alt_text:
            body["alt_text"] = alt_text
        if board_section_id:
            body["board_section_id"] = board_section_id
        return self.request("POST", "/pins", body=body)

    def get_pin(self, pin_id: str) -> dict[str, Any]:
        return self.request("GET", f"/pins/{pin_id}")

    def pin_analytics(
        self,
        pin_id: str,
        start_date: str,
        end_date: str,
        metric_types: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/pins/{pin_id}/analytics",
            params={
                "start_date": start_date,
                "end_date": end_date,
                "metric_types": ",".join(metric_types or DEFAULT_PIN_METRICS),
                "app_types": "ALL",
            },
        )

    def account_analytics(
        self,
        start_date: str,
        end_date: str,
        metric_types: list[str] | None = None,
        split_field: str | None = None,
    ) -> dict[str, Any]:
        return self.request(
            "GET",
            "/user_account/analytics",
            params={
                "start_date": start_date,
                "end_date": end_date,
                "metric_types": ",".join(metric_types or DEFAULT_ACCOUNT_METRICS),
                "app_types": "ALL",
                "split_field": split_field,
            },
        )


DEFAULT_PIN_METRICS = ["IMPRESSION", "SAVE", "PIN_CLICK", "OUTBOUND_CLICK"]
DEFAULT_ACCOUNT_METRICS = [
    "IMPRESSION",
    "SAVE",
    "PIN_CLICK",
    "OUTBOUND_CLICK",
    "ENGAGEMENT",
    "TOTAL_AUDIENCE",
]


def image_url_source(url: str) -> dict[str, Any]:
    return {"source_type": "image_url", "url": url}


def image_file_source(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Загрузка локального файла — Pinterest принимает base64 в media_source."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    content_type = {".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")
    return {
        "source_type": "image_base64",
        "content_type": content_type,
        "data": base64.b64encode(file_path.read_bytes()).decode(),
    }


def _read_error(exc: urllib.error.HTTPError) -> Any:
    try:
        return json.loads(exc.read().decode("utf-8"))
    except Exception:  # тело может быть пустым или HTML
        return exc.reason


def _retry_after(headers: Any, fallback: float) -> float:
    value = headers.get("Retry-After") if headers else None
    try:
        return max(float(value), 1.0)
    except (TypeError, ValueError):
        return fallback
