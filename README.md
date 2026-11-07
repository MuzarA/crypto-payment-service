# Crypto Payment Service

Учебный проект: бэкенд-сервис платёжной системы, который принимает оплату в **BTC** через open-source криптокошелёк **Bitcoin Core** (тестовая сеть regtest).

**Стек:** Python 3.12 · FastAPI · SQLite · Bitcoin Core 27.1 · Docker Compose

## Что умеет

1. Принимает от другого сервиса запрос «взять оплату с клиента» (`POST /api/v1/payments`).
2. Проверяет, есть ли у клиента кошелёк, и получает данные клиента.
3. Отдельным запросом проверяет, хватает ли денег.
4. Списывает деньги на кошелёк сервиса и отвечает «Деньги сняты успешно» с `txid`.
5. Делает возврат (`POST /api/v1/payments/{id}/refund`).
6. Хранит историю статусов каждого платежа.

## Документы для мидтерма

| # | Документ |
|---|---|
| 1 | [Требования](docs/01_requirements.md) |
| 2 | [4 диаграммы: Context, Sequence, Class, State](docs/02_diagrams.md) |
| 3 | [Архитектура и SOLID](docs/03_architecture_solid.md) |
| 4 | [Запуск на сервере (DigitalOcean)](docs/04_deploy.md) |
| 5 | [Шпаргалка к защите](docs/05_defense_cheatsheet.md) |

## Быстрый старт

```bash
cp .env.example .env                                  # поменять пароль и ключи
docker compose up -d --build
docker compose exec api python -m scripts.seed_regtest  # клиенты alice, bob
./scripts/demo.sh                                       # демонстрация
```

Swagger UI: `http://<сервер>:8000/docs`

Без Docker и Bitcoin Core (имитация кошелька):

```bash
pip install -r requirements-dev.txt
pytest
WALLET_BACKEND=fake uvicorn app.main:app --reload
```

## Структура

```
app/
  domain/      Payment, статусы, машина состояний, доменные ошибки
  ports/       интерфейсы: WalletReader, WalletTransfer, PaymentRepository
  services/    PaymentService — бизнес-логика
  adapters/    Bitcoin Core (JSON-RPC), SQLite, имитации для тестов
  api/         FastAPI: роуты, схемы, API-ключи
  main.py      сборка приложения (Dependency Injection)
docker/bitcoind/  Dockerfile Bitcoin Core
scripts/       seed_regtest.py (тестовые клиенты), demo.sh (демо)
tests/         автотесты (pytest)
docs/          требования, диаграммы, архитектура, деплой, шпаргалка
```
