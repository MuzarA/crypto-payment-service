"""HTTP-эндпоинты. Здесь только «перевод» HTTP <-> вызовы PaymentService, без бизнес-логики."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.schemas import CreatePaymentRequest, ErrorResponse, PaymentResponse
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/api/v1")


def get_service(request: Request) -> PaymentService:
    return request.app.state.payment_service


def get_merchant_id(request: Request, x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Аутентификация сервиса-клиента по API-ключу из заголовка X-API-Key."""
    merchant_id = request.app.state.settings.api_keys.get(x_api_key)
    if merchant_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return merchant_id


ERRORS = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
          409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.post("/payments", status_code=status.HTTP_201_CREATED, response_model=PaymentResponse,
             responses=ERRORS, summary="Взять оплату с клиента в BTC")
def create_payment(body: CreatePaymentRequest,
                   merchant_id: str = Depends(get_merchant_id),
                   service: PaymentService = Depends(get_service)) -> PaymentResponse:
    payment = service.create_payment(merchant_id, body.order_id, body.customer_id,
                                     body.amount, body.currency)
    return PaymentResponse.from_domain(payment)


@router.get("/payments", response_model=list[PaymentResponse], summary="Список платежей магазина")
def list_payments(limit: int = Query(50, ge=1, le=200),
                  merchant_id: str = Depends(get_merchant_id),
                  service: PaymentService = Depends(get_service)) -> list[PaymentResponse]:
    return [PaymentResponse.from_domain(p) for p in service.list_payments(merchant_id, limit)]


@router.get("/payments/{payment_id}", response_model=PaymentResponse, responses=ERRORS,
            summary="Статус платежа")
def get_payment(payment_id: str,
                merchant_id: str = Depends(get_merchant_id),
                service: PaymentService = Depends(get_service)) -> PaymentResponse:
    return PaymentResponse.from_domain(service.get_payment(merchant_id, payment_id))


@router.post("/payments/{payment_id}/refund", response_model=PaymentResponse, responses=ERRORS,
             summary="Вернуть деньги клиенту")
def refund_payment(payment_id: str,
                   merchant_id: str = Depends(get_merchant_id),
                   service: PaymentService = Depends(get_service)) -> PaymentResponse:
    return PaymentResponse.from_domain(service.refund_payment(merchant_id, payment_id))


health_router = APIRouter()


@health_router.get("/health", summary="Проверка, что сервис жив")
def health() -> dict:
    return {"status": "ok"}
