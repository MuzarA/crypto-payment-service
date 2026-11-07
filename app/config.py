"""Настройки берутся из переменных окружения (файл .env в docker-compose)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_api_keys(raw: str) -> dict[str, str]:
    """'shop1:key1,shop2:key2' -> {'key1': 'shop1', 'key2': 'shop2'}"""
    keys: dict[str, str] = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        merchant, _, key = pair.partition(":")
        if merchant and key:
            keys[key.strip()] = merchant.strip()
    return keys


@dataclass(frozen=True)
class Settings:
    wallet_backend: str          # "bitcoin" (Bitcoin Core) или "fake" (имитация без узла)
    bitcoin_rpc_url: str
    bitcoin_rpc_user: str
    bitcoin_rpc_password: str
    service_wallet: str
    auto_mine: bool
    db_path: str
    api_keys: dict[str, str]     # api_key -> merchant_id
    fee_reserve: Decimal

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            wallet_backend=os.getenv("WALLET_BACKEND", "bitcoin").lower(),
            bitcoin_rpc_url=os.getenv("BITCOIN_RPC_URL", "http://localhost:18443"),
            bitcoin_rpc_user=os.getenv("BITCOIN_RPC_USER", "bitcoin"),
            bitcoin_rpc_password=os.getenv("BITCOIN_RPC_PASSWORD", "bitcoin"),
            service_wallet=os.getenv("SERVICE_WALLET", "_payment_service"),
            auto_mine=_bool(os.getenv("AUTO_MINE", "true")),
            db_path=os.getenv("DB_PATH", "payments.db"),
            api_keys=_parse_api_keys(os.getenv("MERCHANT_API_KEYS", "demo-shop:demo-key")),
            fee_reserve=Decimal(os.getenv("FEE_RESERVE", "0.0001")),
        )
