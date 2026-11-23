"""In-memory HTTP stand-in. No sockets."""

from __future__ import annotations

import json
from typing import Any


class Response:
    def __init__(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body) if not isinstance(body, str) else body

    def json(self) -> Any:
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class Session:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, params: Any = None, headers: Any = None, timeout: Any = None) -> Any:
        self.calls.append({"method": method, "url": url, "params": params, "headers": headers, "timeout": timeout})
        if not self._responses:
            raise AssertionError("unexpected HTTP call")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
