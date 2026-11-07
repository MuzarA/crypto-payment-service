"""Адаптер к open-source криптокошельку Bitcoin Core.

Как устроено:
  * у каждого клиента свой кошелёк в Bitcoin Core, имя кошелька = customer_id;
  * у платёжного сервиса свой кошелёк (по умолчанию «_payment_service») — туда приходят деньги;
  * узел работает в режиме regtest (локальная тестовая сеть: «деньги» бесплатные, блоки
    создаются командой), поэтому настоящие биткоины не тратятся.

Учебное упрощение: в реальной системе клиент сам подписывает перевод в своём кошельке,
а здесь сервис имеет доступ к кошелькам клиентов — так задумано в задании («имитация»).

Чтобы перейти на другой кошелёк (например, Ethereum), достаточно написать новый класс,
реализующий WalletGateway, — PaymentService менять не придётся (принцип O из SOLID).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.adapters.bitcoin_rpc import BitcoinRpcClient, BitcoinRpcError
from app.ports.wallet import (
    CustomerWalletInfo,
    InsufficientFundsError,
    WalletError,
    WalletGateway,
)

logger = logging.getLogger(__name__)

RPC_WALLET_INSUFFICIENT_FUNDS = -6
RPC_WALLET_ALREADY_LOADED = -35


class BitcoinCoreWallet(WalletGateway):
    def __init__(self, rpc: BitcoinRpcClient, service_wallet: str = "_payment_service",
                 miner_wallet: str = "_miner", auto_mine: bool = False):
        self._rpc = rpc
        self._service_wallet = service_wallet
        self._miner_wallet = miner_wallet
        # В regtest транзакция подтверждается только когда кто-то создал блок.
        # auto_mine=True — после каждого перевода создаём 1 блок (только для учебной сети!).
        self._auto_mine = auto_mine

    # ---------- подготовка ----------

    def ensure_ready(self) -> None:
        """При старте: создать/загрузить служебные кошельки, если их ещё нет."""
        for name in (self._service_wallet, self._miner_wallet):
            if not self._load_if_exists(name):
                self._call("createwallet", name)
                logger.info("created wallet %s", name)

    # ---------- WalletReader ----------

    def wallet_exists(self, customer_id: str) -> bool:
        return self._load_if_exists(customer_id)

    def get_customer_info(self, customer_id: str) -> CustomerWalletInfo:
        info = self._call("getwalletinfo", wallet=customer_id)
        address = self._call("getnewaddress", "refund", wallet=customer_id)
        return CustomerWalletInfo(
            customer_id=customer_id,
            wallet_name=info.get("walletname", customer_id),
            refund_address=address,
            tx_count=int(info.get("txcount", 0)),
        )

    def get_balance(self, customer_id: str) -> Decimal:
        # getbalance = подтверждённые («доверенные») деньги, которые можно тратить
        return Decimal(str(self._call("getbalance", wallet=customer_id)))

    # ---------- WalletTransfer ----------

    def charge(self, customer_id: str, amount: Decimal) -> str:
        destination = self._call("getnewaddress", "payment", wallet=self._service_wallet)
        txid = self._send(from_wallet=customer_id, to_address=destination, amount=amount)
        self._mine_if_needed()
        return txid

    def refund(self, to_address: str, amount: Decimal) -> str:
        # Комиссию сети за возврат вычитаем из суммы (subtract_fee=True): у сервиса на кошельке
        # лежит ровно полученная сумма, лишних денег на комиссию у него может не быть.
        txid = self._send(from_wallet=self._service_wallet, to_address=to_address, amount=amount,
                          subtract_fee=True)
        self._mine_if_needed()
        return txid

    # ---------- внутреннее ----------

    def _send(self, from_wallet: str, to_address: str, amount: Decimal,
              subtract_fee: bool = False) -> str:
        # sendtoaddress <address> <amount> <comment> <comment_to> <subtractfeefromamount>
        try:
            return self._rpc.call("sendtoaddress", to_address, amount, "", "", subtract_fee,
                                  wallet=from_wallet)
        except BitcoinRpcError as exc:
            if exc.code == RPC_WALLET_INSUFFICIENT_FUNDS:
                raise InsufficientFundsError(exc.message) from exc
            raise WalletError(str(exc)) from exc

    def _load_if_exists(self, name: str) -> bool:
        """True, если кошелёк есть (при необходимости загружаем его с диска)."""
        if name in self._call("listwallets"):
            return True
        on_disk = {w["name"] for w in self._call("listwalletdir").get("wallets", [])}
        if name not in on_disk:
            return False
        try:
            self._rpc.call("loadwallet", name)
        except BitcoinRpcError as exc:
            if exc.code != RPC_WALLET_ALREADY_LOADED:  # кто-то успел загрузить параллельно
                raise WalletError(str(exc)) from exc
        return True

    def _mine_if_needed(self) -> None:
        if self._auto_mine:
            address = self._call("getnewaddress", wallet=self._miner_wallet)
            self._call("generatetoaddress", 1, address)

    def _call(self, method: str, *params, wallet: str | None = None):
        try:
            return self._rpc.call(method, *params, wallet=wallet)
        except BitcoinRpcError as exc:
            raise WalletError(str(exc)) from exc
