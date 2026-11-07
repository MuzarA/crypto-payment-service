"""Хранилище платежей в SQLite (встроено в Python, отдельная БД не нужна)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from decimal import Decimal

from app.domain.models import Payment, StatusChange
from app.domain.status import FailureReason, PaymentStatus
from app.ports.repository import PaymentRepository

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id              TEXT PRIMARY KEY,
    merchant_id     TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    customer_id     TEXT NOT NULL,
    amount          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    status          TEXT NOT NULL,
    txid            TEXT,
    refund_txid     TEXT,
    refund_address  TEXT,
    failure_reason  TEXT,
    failure_message TEXT,
    history         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (merchant_id, order_id)
);
"""

COLUMNS = ("id", "merchant_id", "order_id", "customer_id", "amount", "currency", "status",
           "txid", "refund_txid", "refund_address", "failure_reason", "failure_message",
           "history", "created_at", "updated_at")


class SqlitePaymentRepository(PaymentRepository):
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()  # FastAPI обрабатывает запросы в нескольких потоках
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)

    def add(self, payment: Payment) -> None:
        placeholders = ", ".join("?" for _ in COLUMNS)
        with self._lock, self._conn:
            self._conn.execute(f"INSERT INTO payments ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                               self._to_row(payment))

    def save(self, payment: Payment) -> None:
        assignments = ", ".join(f"{c} = ?" for c in COLUMNS[1:])
        row = self._to_row(payment)
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE payments SET {assignments} WHERE id = ?", (*row[1:], row[0]))

    def get(self, payment_id: str) -> Payment | None:
        return self._one("SELECT * FROM payments WHERE id = ?", (payment_id,))

    def find_by_order(self, merchant_id: str, order_id: str) -> Payment | None:
        return self._one("SELECT * FROM payments WHERE merchant_id = ? AND order_id = ?",
                         (merchant_id, order_id))

    def list_by_merchant(self, merchant_id: str, limit: int = 50) -> list[Payment]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM payments WHERE merchant_id = ? ORDER BY created_at DESC LIMIT ?",
                (merchant_id, limit)).fetchall()
        return [self._from_row(r) for r in rows]

    # ---------- преобразование объект <-> строка таблицы ----------

    def _one(self, sql: str, params: tuple) -> Payment | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _to_row(p: Payment) -> tuple:
        history = json.dumps([{"status": h.status.value, "at": h.at.isoformat(), "note": h.note}
                              for h in p.history])
        return (p.id, p.merchant_id, p.order_id, p.customer_id, str(p.amount), p.currency,
                p.status.value, p.txid, p.refund_txid, p.refund_address,
                p.failure_reason.value if p.failure_reason else None, p.failure_message,
                history, p.created_at.isoformat(), p.updated_at.isoformat())

    @staticmethod
    def _from_row(r: sqlite3.Row) -> Payment:
        return Payment(
            id=r["id"], merchant_id=r["merchant_id"], order_id=r["order_id"],
            customer_id=r["customer_id"], amount=Decimal(r["amount"]), currency=r["currency"],
            status=PaymentStatus(r["status"]), txid=r["txid"], refund_txid=r["refund_txid"],
            refund_address=r["refund_address"],
            failure_reason=FailureReason(r["failure_reason"]) if r["failure_reason"] else None,
            failure_message=r["failure_message"],
            history=[StatusChange(PaymentStatus(h["status"]), datetime.fromisoformat(h["at"]), h["note"])
                     for h in json.loads(r["history"])],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )
