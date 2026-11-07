"""Точка входа и «корень композиции»: только здесь решается, какие реализации
подставить вместо интерфейсов (Bitcoin Core или имитация, SQLite или память).

Запуск:  uvicorn app.main:app --host 0.0.0.0 --port 8000
Документация API (Swagger UI): http://<сервер>:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.adapters.bitcoin_core_wallet import BitcoinCoreWallet
from app.adapters.bitcoin_rpc import BitcoinRpcClient
from app.adapters.in_memory import FakeWallet
from app.adapters.sqlite_repository import SqlitePaymentRepository
from app.api.routes import health_router, router
from app.config import Settings
from app.domain.errors import (
    DuplicateOrderError,
    InvalidStatusTransitionError,
    PaymentNotFoundError,
    ValidationError,
)
from app.ports.wallet import WalletError, WalletGateway
from app.services.payment_service import PaymentService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("payment-service")


def build_wallet(settings: Settings) -> WalletGateway:
    if settings.wallet_backend == "fake":
        logger.warning("WALLET_BACKEND=fake: используется имитация кошелька, а не Bitcoin Core")
        return FakeWallet({"alice": Decimal("1.0"), "bob": Decimal("0.001")})
    rpc = BitcoinRpcClient(settings.bitcoin_rpc_url, settings.bitcoin_rpc_user, settings.bitcoin_rpc_password)
    return BitcoinCoreWallet(rpc, service_wallet=settings.service_wallet, auto_mine=settings.auto_mine)


def create_app(settings: Settings | None = None, service: PaymentService | None = None,
               wallet: WalletGateway | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if service is None:
        wallet = wallet or build_wallet(settings)
        repo = SqlitePaymentRepository(settings.db_path)
        # Один и тот же объект кошелька подставляется в обе «роли» (чтение и переводы).
        service = PaymentService(repo, wallet_reader=wallet, wallet_transfer=wallet,
                                 fee_reserve=settings.fee_reserve)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if isinstance(wallet, BitcoinCoreWallet):
            try:
                wallet.ensure_ready()
            except WalletError as exc:  # сервис стартует, но оплаты будут FAILED/WALLET_ERROR
                logger.error("Bitcoin node is not ready: %s", exc)
        yield

    app = FastAPI(title="Crypto Payment Service",
                  description="Учебный платёжный бэкенд-сервис: приём оплаты в BTC через Bitcoin Core.",
                  version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.payment_service = service
    app.include_router(health_router)
    app.include_router(router)
    _register_error_handlers(app)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    """Перевод доменных ошибок в HTTP-коды."""

    def handler(code: int, name: str):
        async def _h(_: Request, exc: Exception) -> JSONResponse:
            body = {"error": name, "detail": str(exc)}
            if isinstance(exc, DuplicateOrderError):
                body["existing_payment_id"] = exc.existing_payment_id
            return JSONResponse(status_code=code, content=body)
        return _h

    app.add_exception_handler(PaymentNotFoundError, handler(404, "PAYMENT_NOT_FOUND"))
    app.add_exception_handler(DuplicateOrderError, handler(409, "DUPLICATE_ORDER"))
    app.add_exception_handler(InvalidStatusTransitionError, handler(409, "INVALID_STATUS"))
    app.add_exception_handler(ValidationError, handler(422, "VALIDATION_ERROR"))
    app.add_exception_handler(WalletError, handler(502, "WALLET_ERROR"))


app = create_app()
