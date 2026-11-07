#!/usr/bin/env bash
# Демонстрация для мидтерма: шлём запросы и показываем ответы.
# Использование:  API_URL=http://<IP-сервера>:8000 API_KEY=demo-key ./scripts/demo.sh
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-demo-key}"
RUN="$(date +%s)"   # чтобы номера заказов не повторялись между запусками

pretty() { python3 -m json.tool 2>/dev/null || cat; }
pay() {  # pay <order_id> <customer_id> <amount>
  curl -s -X POST "$API_URL/api/v1/payments" \
       -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
       -d "{\"order_id\":\"$1\",\"customer_id\":\"$2\",\"amount\":\"$3\",\"currency\":\"BTC\"}"
}
step() { printf '\n\033[1;34m=== %s ===\033[0m\n' "$1"; }

step "0. Сервис жив?"
curl -s "$API_URL/health" | pretty

step "1. alice платит 0.01 BTC -> ожидаем COMPLETED"
RESP="$(pay "order-$RUN-1" alice 0.01)"
echo "$RESP" | pretty
PAYMENT_ID="$(echo "$RESP" | python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')"

step "2. bob платит 0.01 BTC -> ожидаем FAILED / INSUFFICIENT_FUNDS"
pay "order-$RUN-2" bob 0.01 | pretty

step "3. carol (нет кошелька) -> ожидаем FAILED / WALLET_NOT_FOUND"
pay "order-$RUN-3" carol 0.01 | pretty

step "4. Повтор того же заказа -> ожидаем 409 DUPLICATE_ORDER"
pay "order-$RUN-1" alice 0.01 | pretty

step "5. Статус платежа №1"
curl -s "$API_URL/api/v1/payments/$PAYMENT_ID" -H "X-API-Key: $API_KEY" | pretty

step "6. Возврат платежа №1 -> ожидаем REFUNDED"
curl -s -X POST "$API_URL/api/v1/payments/$PAYMENT_ID/refund" -H "X-API-Key: $API_KEY" | pretty

step "7. Повторный возврат -> ожидаем 409 INVALID_STATUS"
curl -s -X POST "$API_URL/api/v1/payments/$PAYMENT_ID/refund" -H "X-API-Key: $API_KEY" | pretty

step "8. Неверный API-ключ -> ожидаем 401"
curl -s "$API_URL/api/v1/payments" -H "X-API-Key: wrong" | pretty
