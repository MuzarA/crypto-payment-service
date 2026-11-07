"""Реализации «понарошку»: хранилище в памяти и поддельный кошелёк.

Нужны для тестов и для запуска без Bitcoin Core (WALLET_BACKEND=fake).
То, что их можно подставить вместо настоящих без изменения PaymentService,
и есть принцип подстановки Лисков (L из SOLID).
"""

from __future__ import annotations

import copy
import threading
import uuid
from decimal import Decimal

from app.domain.models import Payment
from app.ports.repository import PaymentRepository
from app.ports.wallet import (
    CustomerWalletInfo,
    InsufficientFundsError,
    WalletGateway,
)


class InMemoryPaymentRepository(PaymentRepository):
    def __init__(self):
        self._items: dict[str, Payment] = {}
        self._lock = threading.Lock()

    def add(self, payment: Payment) -> None:
        with self._lock:
            self._items[payment.id] = copy.deepcopy(payment)

    def save(self, payment: Payment) -> None:
        self.add(payment)

    def get(self, payment_id: str) -> Payment | None:
        p = self._items.get(payment_id)
        return copy.deepcopy(p) if p else None

    def find_by_order(self, merchant_id: str, order_id: str) -> Payment | None:
        for p in self._items.values():
            if p.merchant_id == merchant_id and p.order_id == order_id:
                return copy.deepcopy(p)
        return None

    def list_by_merchant(self, merchant_id: str, limit: int = 50) -> list[Payment]:
        items = [p for p in self._items.values() if p.merchant_id == merchant_id]
        items.sort(key=lambda p: p.created_at, reverse=True)
        return [copy.deepcopy(p) for p in items[:limit]]


class FakeWallet(WalletGateway):
    """Кошелёк-имитация: балансы хранятся в словаре, комиссия сети фиксированная."""

    def __init__(self, balances: dict[str, Decimal] | None = None, network_fee: Decimal = Decimal("0.00001")):
        self.balances: dict[str, Decimal] = dict(balances or {})
        self.service_balance = Decimal("0")
        self.network_fee = network_fee
        self._addresses: dict[str, str] = {}  # адрес -> клиент
        self._lock = threading.Lock()

    def wallet_exists(self, customer_id: str) -> bool:
        return customer_id in self.balances

    def get_customer_info(self, customer_id: str) -> CustomerWalletInfo:
        address = f"fake-addr-{customer_id}-{uuid.uuid4().hex[:8]}"
        self._addresses[address] = customer_id
        return CustomerWalletInfo(customer_id, customer_id, address, tx_count=0)

    def get_balance(self, customer_id: str) -> Decimal:
        return self.balances[customer_id]

    def charge(self, customer_id: str, amount: Decimal) -> str:
        with self._lock:
            total = amount + self.network_fee
            if self.balances.get(customer_id, Decimal("0")) < total:
                raise InsufficientFundsError("Insufficient funds")
            self.balances[customer_id] -= total
            self.service_balance += amount
        return f"fake-tx-{uuid.uuid4().hex}"

    def refund(self, to_address: str, amount: Decimal) -> str:
        # Как и в BitcoinCoreWallet: комиссия сети вычитается из суммы возврата.
        with self._lock:
            if self.service_balance < amount:
                raise InsufficientFundsError("Service wallet has insufficient funds")
            self.service_balance -= amount
            customer = self._addresses[to_address]
            self.balances[customer] += amount - self.network_fee
        return f"fake-tx-{uuid.uuid4().hex}"
