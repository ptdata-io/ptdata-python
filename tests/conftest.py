"""Default suite does not open sockets. Live tests opt in with PTDATA_LIVE=1."""

from __future__ import annotations

import os
import socket

import pytest

_REAL_SOCKET = socket.socket


class _NoNetworkSocket(_REAL_SOCKET):
    def connect(self, address):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"network disabled during unit tests ({address})")

    def connect_ex(self, address):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"network disabled during unit tests ({address})")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if os.environ.get("PTDATA_LIVE") == "1" and request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(socket, "socket", _NoNetworkSocket)
