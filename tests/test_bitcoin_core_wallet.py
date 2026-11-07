"""Тесты адаптера Bitcoin Core без настоящего узла: подменяем RPC-клиент."""

from decimal import Decimal

import pytest

from app.adapters.bitcoin_core_wallet import BitcoinCoreWallet
from app.adapters.bitcoin_rpc import BitcoinRpcClient, BitcoinRpcError
from app.ports.wallet import InsufficientFundsError, WalletError


class FakeRpc:
    def __init__(self, loaded=("_payment_service", "_miner"), on_disk=(), balances=None, send_error=None):
        self.loaded = list(loaded)
        self.on_disk = list(on_disk)
        self.balances = balances or {}
        self.send_error = send_error
        self.calls = []

    def call(self, method, *params, wallet=None):
        self.calls.append((method, params, wallet))
        if method == "listwallets":
            return list(self.loaded)
        if method == "listwalletdir":
            return {"wallets": [{"name": n} for n in self.loaded + self.on_disk]}
        if method == "loadwallet":
            self.loaded.append(params[0])
            return {"name": params[0]}
        if method == "createwallet":
            self.loaded.append(params[0])
            return {"name": params[0]}
        if method == "getwalletinfo":
            return {"walletname": wallet, "txcount": 3}
        if method == "getnewaddress":
            return f"bcrt1-{wallet}"
        if method == "getbalance":
            return self.balances.get(wallet, Decimal("0"))
        if method == "sendtoaddress":
            if self.send_error:
                raise self.send_error
            return "txid123"
        if method == "generatetoaddress":
            return ["blockhash"]
        raise AssertionError(method)


def test_wallet_exists_loads_from_disk():
    rpc = FakeRpc(on_disk=["alice"])
    w = BitcoinCoreWallet(rpc)
    assert w.wallet_exists("alice")
    assert ("loadwallet", ("alice",), None) in rpc.calls
    assert not w.wallet_exists("carol")


def test_customer_info_and_balance():
    rpc = FakeRpc(loaded=["alice"], balances={"alice": Decimal("1.5")})
    w = BitcoinCoreWallet(rpc)
    info = w.get_customer_info("alice")
    assert info.refund_address == "bcrt1-alice" and info.tx_count == 3
    assert w.get_balance("alice") == Decimal("1.5")


def test_charge_sends_to_service_wallet_and_mines():
    rpc = FakeRpc(loaded=["alice", "_payment_service", "_miner"])
    w = BitcoinCoreWallet(rpc, auto_mine=True)
    assert w.charge("alice", Decimal("0.01")) == "txid123"
    send = next(c for c in rpc.calls if c[0] == "sendtoaddress")
    assert send == ("sendtoaddress", ("bcrt1-_payment_service", Decimal("0.01"), "", "", False), "alice")
    assert any(c[0] == "generatetoaddress" for c in rpc.calls)


def test_refund_subtracts_fee_from_service_wallet():
    rpc = FakeRpc()
    w = BitcoinCoreWallet(rpc)
    w.refund("bcrt1-alice", Decimal("0.01"))
    send = next(c for c in rpc.calls if c[0] == "sendtoaddress")
    assert send == ("sendtoaddress", ("bcrt1-alice", Decimal("0.01"), "", "", True), "_payment_service")
    assert not any(c[0] == "generatetoaddress" for c in rpc.calls)  # auto_mine выключен


def test_insufficient_funds_error_is_mapped():
    rpc = FakeRpc(loaded=["alice"], send_error=BitcoinRpcError(-6, "Insufficient funds"))
    with pytest.raises(InsufficientFundsError):
        BitcoinCoreWallet(rpc).charge("alice", Decimal("1"))


def test_other_rpc_errors_are_wallet_errors():
    rpc = FakeRpc(loaded=["alice"], send_error=BitcoinRpcError(-5, "Invalid address"))
    with pytest.raises(WalletError):
        BitcoinCoreWallet(rpc).charge("alice", Decimal("1"))


def test_ensure_ready_creates_missing_wallets():
    rpc = FakeRpc(loaded=[])
    BitcoinCoreWallet(rpc).ensure_ready()
    assert {"_payment_service", "_miner"} <= set(rpc.loaded)


# ---------- сам RPC-клиент ----------

class FakeResponse:
    def __init__(self, status, text):
        self.status_code = status
        self._text = text

    def json(self, **kw):
        import json
        return json.loads(self._text, **kw)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.sent = None

    def post(self, url, **kw):
        self.sent = (url, kw)
        return self.response


def test_rpc_client_parses_decimal_and_wallet_url():
    s = FakeSession(FakeResponse(200, '{"result": 0.12345678, "error": null, "id": "x"}'))
    rpc = BitcoinRpcClient("http://node:18443/", "u", "p", session=s)
    assert rpc.call("getbalance", wallet="alice") == Decimal("0.12345678")
    assert s.sent[0] == "http://node:18443/wallet/alice"
    assert '"method": "getbalance"' in s.sent[1]["data"]


def test_rpc_client_sends_amount_as_exact_string():
    s = FakeSession(FakeResponse(200, '{"result": "tx", "error": null}'))
    BitcoinRpcClient("http://n", "u", "p", session=s).call("sendtoaddress", "a", Decimal("0.1"))
    assert '"params": ["a", "0.1"]' in s.sent[1]["data"]


def test_rpc_client_errors():
    from app.ports.wallet import WalletUnavailableError
    s = FakeSession(FakeResponse(500, '{"result": null, "error": {"code": -6, "message": "Insufficient funds"}}'))
    with pytest.raises(BitcoinRpcError) as e:
        BitcoinRpcClient("http://n", "u", "p", session=s).call("sendtoaddress")
    assert e.value.code == -6
    with pytest.raises(WalletUnavailableError):
        BitcoinRpcClient("http://n", "u", "p", session=FakeSession(FakeResponse(401, ""))).call("x")
