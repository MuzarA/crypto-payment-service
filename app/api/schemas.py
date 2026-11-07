"""Формат JSON запросов и ответов (DTO). Проверку типов делает pydantic."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain.models import Payment


class CreatePaymentRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64, examples=["order-1001"])
    customer_id: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", examples=["alice"])
    amount: Decimal = Field(..., gt=0, max_digits=16, decimal_places=8, examples=["0.01"])
    currency: str = Field("BTC", examples=["BTC"])


class StatusChangeDTO(BaseModel):
    status: str
    at: datetime
    note: str | None = None


class PaymentResponse(BaseModel):
    id: str
    order_id: str
    customer_id: str
    amount: str
    currency: str
    status: str
    message: str
    txid: str | None = None
    refund_txid: str | None = None
    failure_reason: str | None = None
    failure_message: str | None = None
    created_at: datetime
    updated_at: datetime
    history: list[StatusChangeDTO]

    @classmethod
    def from_domain(cls, p: Payment) -> "PaymentResponse":
        return cls(
            id=p.id, order_id=p.order_id, customer_id=p.customer_id,
            amount=str(p.amount), currency=p.currency, status=p.status.value,
            message=_human_message(p), txid=p.txid, refund_txid=p.refund_txid,
            failure_reason=p.failure_reason.value if p.failure_reason else None,
            failure_message=p.failure_message, created_at=p.created_at, updated_at=p.updated_at,
            history=[StatusChangeDTO(status=h.status.value, at=h.at, note=h.note) for h in p.history],
        )


class ErrorResponse(BaseModel):
    error: str
    detail: str


def _human_message(p: Payment) -> str:
    return {
        "COMPLETED": "Деньги сняты успешно",
        "REFUNDED": "Деньги возвращены клиенту",
        "FAILED": "Оплата не прошла",
    }.get(p.status.value, "Платёж в обработке")
