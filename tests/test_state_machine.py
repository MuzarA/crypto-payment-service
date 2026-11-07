from decimal import Decimal

import pytest

from app.domain.errors import InvalidStatusTransitionError
from app.domain.models import Payment
from app.domain.state_machine import PaymentStateMachine
from app.domain.status import PaymentStatus as S


@pytest.mark.parametrize("a,b", [
    (S.CREATED, S.WALLET_VERIFIED), (S.CREATED, S.FAILED),
    (S.WALLET_VERIFIED, S.FUNDS_CONFIRMED), (S.WALLET_VERIFIED, S.FAILED),
    (S.FUNDS_CONFIRMED, S.COMPLETED), (S.FUNDS_CONFIRMED, S.FAILED),
    (S.COMPLETED, S.REFUNDED),
])
def test_allowed(a, b):
    assert PaymentStateMachine.can_transition(a, b)


@pytest.mark.parametrize("a,b", [
    (S.CREATED, S.COMPLETED),          # нельзя пропустить проверки
    (S.WALLET_VERIFIED, S.COMPLETED),
    (S.COMPLETED, S.FAILED),
    (S.FAILED, S.REFUNDED),            # нечего возвращать
    (S.REFUNDED, S.REFUNDED),
    (S.REFUNDED, S.COMPLETED),
])
def test_forbidden(a, b):
    assert not PaymentStateMachine.can_transition(a, b)


def test_final_states():
    assert PaymentStateMachine.is_final(S.FAILED)
    assert PaymentStateMachine.is_final(S.REFUNDED)
    assert not PaymentStateMachine.is_final(S.COMPLETED)


def test_payment_move_to_enforces_rules():
    p = Payment.create("shop", "o1", "alice", Decimal("1"), "BTC")
    with pytest.raises(InvalidStatusTransitionError):
        p.move_to(S.COMPLETED)
    assert p.status is S.CREATED
