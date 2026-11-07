"""Тонкий JSON-RPC клиент для Bitcoin Core (bitcoind).

Единственная ответственность — отправить RPC-запрос и вернуть результат или ошибку.
Никакой бизнес-логики здесь нет.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import requests

from app.ports.wallet import WalletUnavailableError


class BitcoinRpcError(Exception):
    """Узел ответил ошибкой (например, -6 = Insufficient funds, -18 = wallet not found)."""

    def __init__(self, code: int, message: str):
        super().__init__(f"RPC error {code}: {message}")
        self.code = code
        self.message = message


class BitcoinRpcClient:
    def __init__(self, url: str, user: str, password: str, timeout: float = 15.0,
                 session: requests.Session | None = None):
        self._url = url.rstrip("/")
        self._auth = (user, password)
        self._timeout = timeout
        self._session = session or requests.Session()

    def call(self, method: str, *params: Any, wallet: str | None = None) -> Any:
        # Запросы к конкретному кошельку идут на /wallet/<имя>
        url = self._url + (f"/wallet/{quote(wallet, safe='')}" if wallet else "")
        body = json.dumps(
            {"jsonrpc": "1.0", "id": "payment-service", "method": method, "params": list(params)},
            default=str,  # Decimal -> строка; bitcoind принимает суммы строкой без потери точности
        )
        try:
            resp = self._session.post(url, data=body, auth=self._auth, timeout=self._timeout,
                                      headers={"Content-Type": "application/json"})
        except requests.RequestException as exc:
            raise WalletUnavailableError(f"Bitcoin node is unreachable: {exc}") from exc

        if resp.status_code in (401, 403):
            raise WalletUnavailableError("Bitcoin node rejected RPC credentials")
        try:
            # parse_float=Decimal — чтобы суммы в BTC не превращались в неточные float
            data = resp.json(parse_float=Decimal)
        except ValueError as exc:
            raise WalletUnavailableError(f"Bad response from bitcoin node (HTTP {resp.status_code})") from exc

        error = data.get("error")
        if error:
            raise BitcoinRpcError(int(error.get("code", 0)), str(error.get("message", "")))
        return data.get("result")
