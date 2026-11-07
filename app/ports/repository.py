"""Интерфейс хранилища платежей. Реализации: SQLite (прод) и в памяти (тесты)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import Payment


class PaymentRepository(ABC):
    @abstractmethod
    def add(self, payment: Payment) -> None:
        """Сохранить новый платёж."""

    @abstractmethod
    def save(self, payment: Payment) -> None:
        """Обновить существующий платёж."""

    @abstractmethod
    def get(self, payment_id: str) -> Payment | None:
        """Найти платёж по id."""

    @abstractmethod
    def find_by_order(self, merchant_id: str, order_id: str) -> Payment | None:
        """Найти платёж по номеру заказа магазина."""

    @abstractmethod
    def list_by_merchant(self, merchant_id: str, limit: int = 50) -> list[Payment]:
        """Последние платежи магазина."""
