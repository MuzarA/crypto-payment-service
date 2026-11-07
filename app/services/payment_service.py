"""Бизнес-логика платёжного сервиса — ровно тот сценарий, который описал преподаватель:

1. Сервис-клиент (магазин) присылает запрос: «хочу взять оплату с клиента в крипте».
2. Проверяем, есть ли у клиента кошелёк.
3. Если есть — запрашиваем данные клиента.
4. Повторным запросом проверяем, хватает ли денег на кошельке.
5. Списываем деньги и отвечаем: «деньги сняты успешно» (или почему нет).
+ Возврат (refund) уже проведённого платежа.

Этот класс ничего не знает о Bitcoin Core, SQLite или HTTP — он получает
абстракции через конструктор (Dependency Injection).
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from app.domain.errors import (
    DuplicateOrderError,
    InvalidStatusTransitionError,
    PaymentNotFoundError,
    ValidationError,
)
from app.domain.models import Payment
from app.domain.status import FailureReason, PaymentStatus
from app.ports.repository import PaymentRepository
from app.ports.wallet import (
    InsufficientFundsError,
    WalletError,
    WalletReader,
    WalletTransfer,
)

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = frozenset({"BTC"})
MAX_DECIMALS = 8  # 1 сатоши = 0.00000001 BTC
CUSTOMER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class PaymentService:
    def __init__(
        self,
        repository: PaymentRepository,
        wallet_reader: WalletReader,
        wallet_transfer: WalletTransfer,
        fee_reserve: Decimal = Decimal("0.0001"),
    ):
        self._repo = repository
        self._reader = wallet_reader
        self._transfer = wallet_transfer
        # Запас на комиссию сети: на кошельке должно быть amount + fee_reserve.
        self._fee_reserve = fee_reserve

    # ---------- сценарий 1: оплата ----------

    def create_payment(self, merchant_id: str, order_id: str, customer_id: str,
                       amount: Decimal, currency: str = "BTC") -> Payment:
        currency = currency.upper()
        self._validate(order_id, customer_id, amount, currency)

        existing = self._repo.find_by_order(merchant_id, order_id)
        if existing is not None:
            raise DuplicateOrderError(order_id, existing.id)

        payment = Payment.create(merchant_id, order_id, customer_id, amount, currency)
        self._repo.add(payment)
        logger.info("payment %s created: %s %s from %s", payment.id, amount, currency, customer_id)

        self._process(payment)
        return payment

    def _process(self, payment: Payment) -> None:
        try:
            # Шаг 1: есть ли кошелёк у клиента?
            if not self._reader.wallet_exists(payment.customer_id):
                self._fail(payment, FailureReason.WALLET_NOT_FOUND,
                           f"Wallet for customer '{payment.customer_id}' not found")
                return

            # Шаг 2: «дай мне данные клиента»
            info = self._reader.get_customer_info(payment.customer_id)
            payment.refund_address = info.refund_address
            payment.move_to(PaymentStatus.WALLET_VERIFIED)
            self._repo.save(payment)

            # Шаг 3: повторный запрос — хватает ли денег?
            balance = self._reader.get_balance(payment.customer_id)
            required = payment.amount + self._fee_reserve
            if balance < required:
                self._fail(payment, FailureReason.INSUFFICIENT_FUNDS,
                           f"Balance {balance} < required {required} (amount + network fee)")
                return
            payment.move_to(PaymentStatus.FUNDS_CONFIRMED)
            self._repo.save(payment)

            # Шаг 4: списываем деньги
            payment.txid = self._transfer.charge(payment.customer_id, payment.amount)
            payment.move_to(PaymentStatus.COMPLETED, note=f"txid={payment.txid}")
            self._repo.save(payment)
            logger.info("payment %s completed, txid=%s", payment.id, payment.txid)

        except InsufficientFundsError as exc:
            self._fail(payment, FailureReason.INSUFFICIENT_FUNDS, str(exc))
        except WalletError as exc:
            self._fail(payment, FailureReason.WALLET_ERROR, str(exc))

    def _fail(self, payment: Payment, reason: FailureReason, message: str) -> None:
        payment.fail(reason, message)
        self._repo.save(payment)
        logger.warning("payment %s failed: %s (%s)", payment.id, reason.value, message)

    # ---------- сценарий 2: возврат ----------

    def refund_payment(self, merchant_id: str, payment_id: str) -> Payment:
        payment = self.get_payment(merchant_id, payment_id)
        if payment.status is not PaymentStatus.COMPLETED:
            # Вернуть можно только успешно списанный платёж.
            raise InvalidStatusTransitionError(payment.status.value, PaymentStatus.REFUNDED.value)
        if not payment.refund_address:
            raise ValidationError("Payment has no refund address")

        # WalletError здесь пробрасывается наверх: платёж остаётся COMPLETED,
        # магазин может повторить возврат позже.
        payment.refund_txid = self._transfer.refund(payment.refund_address, payment.amount)
        payment.move_to(PaymentStatus.REFUNDED, note=f"refund_txid={payment.refund_txid}")
        self._repo.save(payment)
        logger.info("payment %s refunded, txid=%s", payment.id, payment.refund_txid)
        return payment

    # ---------- чтение ----------

    def get_payment(self, merchant_id: str, payment_id: str) -> Payment:
        payment = self._repo.get(payment_id)
        # Магазин видит только свои платежи.
        if payment is None or payment.merchant_id != merchant_id:
            raise PaymentNotFoundError(payment_id)
        return payment

    def list_payments(self, merchant_id: str, limit: int = 50) -> list[Payment]:
        return self._repo.list_by_merchant(merchant_id, limit)

    # ---------- проверки ----------

    @staticmethod
    def _validate(order_id: str, customer_id: str, amount: Decimal, currency: str) -> None:
        if not order_id or len(order_id) > 64:
            raise ValidationError("order_id must be 1..64 characters")
        if not CUSTOMER_ID_RE.match(customer_id or ""):
            raise ValidationError("customer_id must be 1..64 chars: letters, digits, '_' or '-'")
        if currency not in SUPPORTED_CURRENCIES:
            raise ValidationError(f"Unsupported currency {currency}; supported: {sorted(SUPPORTED_CURRENCIES)}")
        if not amount.is_finite():
            raise ValidationError("amount must be a finite number")
        if amount <= 0:
            raise ValidationError("amount must be greater than 0")
        if -amount.as_tuple().exponent > MAX_DECIMALS:
            raise ValidationError(f"amount can have at most {MAX_DECIMALS} decimal places")
