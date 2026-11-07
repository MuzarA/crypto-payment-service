from decimal import Decimal

from app.adapters.sqlite_repository import SqlitePaymentRepository
from app.domain.models import Payment
from app.domain.status import FailureReason, PaymentStatus


def test_roundtrip(tmp_path):
    repo = SqlitePaymentRepository(str(tmp_path / "p.db"))
    p = Payment.create("shop", "o1", "alice", Decimal("0.12345678"), "BTC")
    repo.add(p)
    p.refund_address = "addr"
    p.move_to(PaymentStatus.WALLET_VERIFIED)
    p.fail(FailureReason.INSUFFICIENT_FUNDS, "no money")
    repo.save(p)

    loaded = repo.get(p.id)
    assert loaded.amount == Decimal("0.12345678")
    assert loaded.status is PaymentStatus.FAILED
    assert loaded.failure_reason is FailureReason.INSUFFICIENT_FUNDS
    assert [h.status for h in loaded.history] == [
        PaymentStatus.CREATED, PaymentStatus.WALLET_VERIFIED, PaymentStatus.FAILED]
    assert repo.find_by_order("shop", "o1").id == p.id
    assert repo.find_by_order("other", "o1") is None
    assert [x.id for x in repo.list_by_merchant("shop")] == [p.id]
    assert repo.get("missing") is None


def test_data_survives_restart(tmp_path):
    path = str(tmp_path / "p.db")
    p = Payment.create("shop", "o1", "alice", Decimal("1"), "BTC")
    SqlitePaymentRepository(path).add(p)
    assert SqlitePaymentRepository(path).get(p.id) is not None
