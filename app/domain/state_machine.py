"""Машина состояний платежа (это то, что нарисовано на state-диаграмме).

    CREATED -> WALLET_VERIFIED -> FUNDS_CONFIRMED -> COMPLETED -> REFUNDED
       \\              \\                  \\
        +--------------+------------------+--> FAILED

FAILED и REFUNDED — конечные состояния, из них никуда перейти нельзя.
"""

from app.domain.errors import InvalidStatusTransitionError
from app.domain.status import PaymentStatus

ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.CREATED: frozenset({PaymentStatus.WALLET_VERIFIED, PaymentStatus.FAILED}),
    PaymentStatus.WALLET_VERIFIED: frozenset({PaymentStatus.FUNDS_CONFIRMED, PaymentStatus.FAILED}),
    PaymentStatus.FUNDS_CONFIRMED: frozenset({PaymentStatus.COMPLETED, PaymentStatus.FAILED}),
    PaymentStatus.COMPLETED: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


class PaymentStateMachine:
    """Единственная ответственность — решать, разрешён ли переход между состояниями."""

    @staticmethod
    def can_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
        return target in ALLOWED_TRANSITIONS[current]

    @classmethod
    def ensure_transition(cls, current: PaymentStatus, target: PaymentStatus) -> None:
        if not cls.can_transition(current, target):
            raise InvalidStatusTransitionError(current.value, target.value)

    @staticmethod
    def is_final(status: PaymentStatus) -> bool:
        return not ALLOWED_TRANSITIONS[status]
