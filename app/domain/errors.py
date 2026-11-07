"""Ошибки бизнес-логики (домена).

Они не знают ни про HTTP, ни про биткоин — только про правила платежей.
Слой API превращает их в HTTP-коды (404, 409, 422).
"""


class DomainError(Exception):
    """Базовая ошибка домена."""


class ValidationError(DomainError):
    """Входные данные нарушают бизнес-правила (сумма <= 0, неизвестная валюта и т.п.)."""


class PaymentNotFoundError(DomainError):
    def __init__(self, payment_id: str):
        super().__init__(f"Payment {payment_id} not found")
        self.payment_id = payment_id


class DuplicateOrderError(DomainError):
    """Магазин уже создавал платёж для этого order_id (защита от двойного списания)."""

    def __init__(self, order_id: str, existing_payment_id: str):
        super().__init__(f"Payment for order {order_id} already exists: {existing_payment_id}")
        self.order_id = order_id
        self.existing_payment_id = existing_payment_id


class InvalidStatusTransitionError(DomainError):
    """Попытка перевести платёж в недопустимое состояние (например, вернуть FAILED-платёж)."""

    def __init__(self, current: str, target: str):
        super().__init__(f"Cannot move payment from {current} to {target}")
        self.current = current
        self.target = target
