"""Интерфейсы (порты) для работы с криптокошельком.

Бизнес-логика (PaymentService) зависит ТОЛЬКО от этих абстракций,
а не от конкретного Bitcoin Core. Это принцип D из SOLID.

Интерфейс специально разделён на два маленьких (принцип I из SOLID):
  * WalletReader   — только читать: есть ли кошелёк, данные клиента, баланс;
  * WalletTransfer — только двигать деньги: списать и вернуть.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


class WalletError(Exception):
    """Любая ошибка со стороны кошелька."""


class WalletUnavailableError(WalletError):
    """Узел кошелька не отвечает / неверный логин-пароль."""


class InsufficientFundsError(WalletError):
    """Кошелёк отказал в переводе из-за нехватки денег (с учётом комиссии сети)."""


@dataclass(frozen=True)
class CustomerWalletInfo:
    """«Данные клиента», которые возвращает кошелёк."""

    customer_id: str
    wallet_name: str
    refund_address: str  # адрес клиента, на который можно вернуть деньги
    tx_count: int


class WalletReader(ABC):
    @abstractmethod
    def wallet_exists(self, customer_id: str) -> bool:
        """Есть ли у клиента кошелёк."""

    @abstractmethod
    def get_customer_info(self, customer_id: str) -> CustomerWalletInfo:
        """Данные клиента из кошелька."""

    @abstractmethod
    def get_balance(self, customer_id: str) -> Decimal:
        """Сколько денег доступно на кошельке клиента."""


class WalletTransfer(ABC):
    @abstractmethod
    def charge(self, customer_id: str, amount: Decimal) -> str:
        """Списать amount с кошелька клиента в кошелёк платёжного сервиса. Возвращает txid."""

    @abstractmethod
    def refund(self, to_address: str, amount: Decimal) -> str:
        """Вернуть amount из кошелька сервиса на адрес клиента. Возвращает txid."""


class WalletGateway(WalletReader, WalletTransfer, ABC):
    """Полный адаптер кошелька = чтение + переводы."""
