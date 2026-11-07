from enum import Enum


class PaymentStatus(str, Enum):
    """Состояния платежа."""

    CREATED = "CREATED"                  # запрос принят, платёж записан
    WALLET_VERIFIED = "WALLET_VERIFIED"  # кошелёк клиента найден, данные клиента получены
    FUNDS_CONFIRMED = "FUNDS_CONFIRMED"  # на кошельке хватает денег
    COMPLETED = "COMPLETED"              # деньги списаны, есть txid транзакции
    FAILED = "FAILED"                    # оплата не прошла (см. failure_reason)
    REFUNDED = "REFUNDED"                # деньги возвращены клиенту


class FailureReason(str, Enum):
    WALLET_NOT_FOUND = "WALLET_NOT_FOUND"      # у клиента нет кошелька
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"  # не хватает денег
    WALLET_ERROR = "WALLET_ERROR"              # кошелёк недоступен / другая ошибка узла
