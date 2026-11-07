"""Подготовка тестовых данных в Bitcoin Core (regtest).

Создаёт клиентов:
  * alice — кошелёк с деньгами (50 BTC «намайнено»);
  * bob   — кошелёк почти без денег (0.001 BTC) -> оплата не пройдёт: INSUFFICIENT_FUNDS;
  * carol — НЕ создаётся                      -> оплата не пройдёт: WALLET_NOT_FOUND.

Запуск на сервере:  docker compose exec api python -m scripts.seed_regtest
"""

from decimal import Decimal

from app.adapters.bitcoin_core_wallet import BitcoinCoreWallet
from app.adapters.bitcoin_rpc import BitcoinRpcClient, BitcoinRpcError
from app.config import Settings


def ensure_wallet(rpc: BitcoinRpcClient, wallet: BitcoinCoreWallet, name: str) -> None:
    if not wallet.wallet_exists(name):
        rpc.call("createwallet", name)
        print(f"created wallet {name}")


def main() -> None:
    s = Settings.from_env()
    rpc = BitcoinRpcClient(s.bitcoin_rpc_url, s.bitcoin_rpc_user, s.bitcoin_rpc_password)
    wallet = BitcoinCoreWallet(rpc, service_wallet=s.service_wallet)
    wallet.ensure_ready()

    for name in ("alice", "bob"):
        ensure_wallet(rpc, wallet, name)

    if wallet.get_balance("alice") < Decimal("1"):
        # 101 блок: награда за первый блок «созревает» через 100 блоков и становится доступной
        addr = rpc.call("getnewaddress", wallet="alice")
        rpc.call("generatetoaddress", 101, addr)
        print("mined 101 blocks to alice")

    if wallet.get_balance("bob") == 0:
        bob_addr = rpc.call("getnewaddress", wallet="bob")
        rpc.call("sendtoaddress", bob_addr, "0.001", wallet="alice")
        miner = rpc.call("getnewaddress", wallet="_miner")
        rpc.call("generatetoaddress", 1, miner)
        print("sent 0.001 BTC to bob")

    for name in ("alice", "bob"):
        print(f"{name}: {wallet.get_balance(name)} BTC")
    try:
        print(f"{s.service_wallet}: {wallet.get_balance(s.service_wallet)} BTC")
    except Exception as exc:  # noqa: BLE001
        print(f"service wallet balance unavailable: {exc}")


if __name__ == "__main__":
    try:
        main()
    except BitcoinRpcError as e:
        raise SystemExit(f"Bitcoin RPC error: {e}")
