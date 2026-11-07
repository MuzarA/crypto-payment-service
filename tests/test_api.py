"""Тесты HTTP-слоя (нужны fastapi и httpx: pip install -r requirements-dev.txt)."""

from decimal import Decimal

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.adapters.in_memory import FakeWallet, InMemoryPaymentRepository  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.payment_service import PaymentService  # noqa: E402

H = {"X-API-Key": "k1"}


@pytest.fixture
def client():
    wallet = FakeWallet({"alice": Decimal("1"), "bob": Decimal("0.001")})
    service = PaymentService(InMemoryPaymentRepository(), wallet, wallet)
    settings = Settings("fake", "", "", "", "_payment_service", False, ":memory:",
                        {"k1": "shop1", "k2": "shop2"}, Decimal("0.0001"))
    with TestClient(create_app(settings=settings, service=service)) as c:
        yield c


def pay(client, order, customer, amount="0.01", headers=H):
    return client.post("/api/v1/payments", headers=headers,
                       json={"order_id": order, "customer_id": customer, "amount": amount})


def test_full_flow(client):
    r = pay(client, "o1", "alice")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "COMPLETED" and body["message"] == "Деньги сняты успешно"
    pid = body["id"]

    assert client.get(f"/api/v1/payments/{pid}", headers=H).json()["status"] == "COMPLETED"
    assert client.post(f"/api/v1/payments/{pid}/refund", headers=H).json()["status"] == "REFUNDED"
    r = client.post(f"/api/v1/payments/{pid}/refund", headers=H)
    assert r.status_code == 409 and r.json()["error"] == "INVALID_STATUS"


def test_failures(client):
    assert pay(client, "o1", "bob").json()["failure_reason"] == "INSUFFICIENT_FUNDS"
    assert pay(client, "o2", "carol").json()["failure_reason"] == "WALLET_NOT_FOUND"
    r = pay(client, "o1", "alice")
    assert r.status_code == 409 and r.json()["error"] == "DUPLICATE_ORDER"


def test_auth_and_validation(client):
    assert pay(client, "o1", "alice", headers={"X-API-Key": "bad"}).status_code == 401
    assert client.post("/api/v1/payments", json={}).status_code == 422  # нет ключа и тела
    assert pay(client, "o1", "alice", amount="-1").status_code == 422
    assert pay(client, "o1", "alice", amount="0.123456789").status_code == 422


def test_merchant_isolation(client):
    pid = pay(client, "o1", "alice").json()["id"]
    assert client.get(f"/api/v1/payments/{pid}", headers={"X-API-Key": "k2"}).status_code == 404
    assert client.get("/api/v1/payments", headers={"X-API-Key": "k2"}).json() == []


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
