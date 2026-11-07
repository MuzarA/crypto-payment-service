from decimal import Decimal

import pytest

from app.adapters.in_memory import FakeWallet, InMemoryPaymentRepository
from app.domain.errors import (
    DuplicateOrderError,
    InvalidStatusTransitionError,
    PaymentNotFoundError,
    ValidationError,
)
from app.domain.status import FailureReason, PaymentStatus
from app.ports.wallet import WalletUnavailableError
from app.services.payment_service import PaymentService

D = Decimal


@pytest.fixture
def wallet():
    return FakeWallet({"alice": D("1.0"), "bob": D("0.001")})


@pytest.fixture
def service(wallet):
    return PaymentService(InMemoryPaymentRepository(), wallet, wallet, fee_reserve=D("0.0001"))


def test_successful_payment(service, wallet):
    p = service.create_payment("shop", "o1", "alice", D("0.01"))
    assert p.status is PaymentStatus.COMPLETED
    assert p.txid
    assert [h.status for h in p.history] == [
        PaymentStatus.CREATED, PaymentStatus.WALLET_VERIFIED,
        PaymentStatus.FUNDS_CONFIRMED, PaymentStatus.COMPLETED]
    assert wallet.service_balance == D("0.01")
    assert wallet.balances["alice"] == D("1.0") - D("0.01") - wallet.network_fee


def test_wallet_not_found(service):
    p = service.create_payment("shop", "o1", "carol", D("0.01"))
    assert p.status is PaymentStatus.FAILED
    assert p.failure_reason is FailureReason.WALLET_NOT_FOUND


def test_insufficient_funds(service, wallet):
    p = service.create_payment("shop", "o1", "bob", D("0.01"))
    assert p.status is PaymentStatus.FAILED
    assert p.failure_reason is FailureReason.INSUFFICIENT_FUNDS
    assert wallet.balances["bob"] == D("0.001")  # деньги не тронуты


def test_fee_reserve_is_required(service):
    # на кошельке ровно сумма, но на комиссию не хватает
    p = service.create_payment("shop", "o1", "bob", D("0.001"))
    assert p.failure_reason is FailureReason.INSUFFICIENT_FUNDS


def test_duplicate_order_rejected(service):
    first = service.create_payment("shop", "o1", "alice", D("0.01"))
    with pytest.raises(DuplicateOrderError) as exc:
        service.create_payment("shop", "o1", "alice", D("0.01"))
    assert exc.value.existing_payment_id == first.id
    # у другого магазина такой же номер заказа — это нормально
    assert service.create_payment("other", "o1", "alice", D("0.01")).status is PaymentStatus.COMPLETED


@pytest.mark.parametrize("amount", [D("0"), D("-1"), D("0.000000001"), D("NaN"), D("Infinity")])
def test_invalid_amount(service, amount):
    with pytest.raises(ValidationError):
        service.create_payment("shop", "o1", "alice", amount)


def test_invalid_currency_and_customer(service):
    with pytest.raises(ValidationError):
        service.create_payment("shop", "o1", "alice", D("0.01"), currency="ETH")
    with pytest.raises(ValidationError):
        service.create_payment("shop", "o1", "_payment_service", D("0.01"))  # служебный кошелёк


def test_refund(service, wallet):
    p = service.create_payment("shop", "o1", "alice", D("0.5"))
    alice_after_payment = wallet.balances["alice"]
    r = service.refund_payment("shop", p.id)
    assert r.status is PaymentStatus.REFUNDED
    assert r.refund_txid
    assert wallet.balances["alice"] == alice_after_payment + D("0.5") - wallet.network_fee
    assert wallet.service_balance == 0


def test_refund_twice_or_failed_is_rejected(service):
    p = service.create_payment("shop", "o1", "alice", D("0.01"))
    service.refund_payment("shop", p.id)
    with pytest.raises(InvalidStatusTransitionError):
        service.refund_payment("shop", p.id)
    failed = service.create_payment("shop", "o2", "carol", D("0.01"))
    with pytest.raises(InvalidStatusTransitionError):
        service.refund_payment("shop", failed.id)


def test_merchant_sees_only_own_payments(service):
    p = service.create_payment("shop", "o1", "alice", D("0.01"))
    with pytest.raises(PaymentNotFoundError):
        service.get_payment("other-shop", p.id)
    assert service.list_payments("other-shop") == []
    assert [x.id for x in service.list_payments("shop")] == [p.id]


def test_wallet_unavailable_marks_payment_failed():
    class BrokenWallet(FakeWallet):
        def wallet_exists(self, customer_id):
            raise WalletUnavailableError("node down")

    w = BrokenWallet()
    service = PaymentService(InMemoryPaymentRepository(), w, w)
    p = service.create_payment("shop", "o1", "alice", D("0.01"))
    assert p.status is PaymentStatus.FAILED
    assert p.failure_reason is FailureReason.WALLET_ERROR


def test_payment_is_persisted(wallet):
    repo = InMemoryPaymentRepository()
    service = PaymentService(repo, wallet, wallet)
    p = service.create_payment("shop", "o1", "alice", D("0.01"))
    stored = repo.get(p.id)
    assert stored.status is PaymentStatus.COMPLETED and stored.txid == p.txid
