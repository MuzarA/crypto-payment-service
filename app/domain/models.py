"""Сущность «Платёж» — главный объект системы."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.state_machine import PaymentStateMachine
from app.domain.status import FailureReason, PaymentStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StatusChange:
    """Одна запись в истории платежа: в какое состояние и когда перешли."""

    status: PaymentStatus
    at: datetime
    note: str | None = None


@dataclass
class Payment:
    id: str
    merchant_id: str      # какой сервис (магазин) запросил оплату
    order_id: str         # номер заказа в системе магазина
    customer_id: str      # клиент = имя его кошелька
    amount: Decimal       # сумма в BTC
    currency: str
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime
    txid: str | None = None            # id транзакции списания в блокчейне
    refund_txid: str | None = None     # id транзакции возврата
    refund_address: str | None = None  # адрес клиента, куда вернуть деньги
    failure_reason: FailureReason | None = None
    failure_message: str | None = None
    history: list[StatusChange] = field(default_factory=list)

    @classmethod
    def create(cls, merchant_id: str, order_id: str, customer_id: str,
               amount: Decimal, currency: str) -> "Payment":
        now = utcnow()
        return cls(
            id=str(uuid.uuid4()),
            merchant_id=merchant_id,
            order_id=order_id,
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            status=PaymentStatus.CREATED,
            created_at=now,
            updated_at=now,
            history=[StatusChange(PaymentStatus.CREATED, now)],
        )

    def move_to(self, target: PaymentStatus, note: str | None = None) -> None:
        """Сменить состояние. Правила проверяет машина состояний."""
        PaymentStateMachine.ensure_transition(self.status, target)
        self.status = target
        self.updated_at = utcnow()
        self.history.append(StatusChange(target, self.updated_at, note))

    def fail(self, reason: FailureReason, message: str | None = None) -> None:
        self.failure_reason = reason
        self.failure_message = message
        self.move_to(PaymentStatus.FAILED, note=reason.value)
