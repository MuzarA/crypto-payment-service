# Архитектура и SOLID

## Подход: Hexagonal / Ports & Adapters (+ слоистая архитектура)

Главная идея: **бизнес-логика в центре и ни от чего внешнего не зависит**. Внешний мир (HTTP, Bitcoin Core, база данных) подключается к ней через интерфейсы, так называемые «порты». Конкретные реализации этих интерфейсов называются «адаптерами».

```
                ┌───────────────────────────────────────────┐
  HTTP  ──────► │  api/        (FastAPI: роуты, JSON, ключи) │   входящий адаптер
                └───────────────┬───────────────────────────┘
                                ▼
                ┌───────────────────────────────────────────┐
                │  services/   PaymentService (сценарии)     │   бизнес-логика
                │  domain/     Payment, статусы, state machine│   доменная модель
                └───────┬───────────────────────┬───────────┘
                        ▼ (интерфейсы — ports/)  ▼
          ┌─────────────────────────┐  ┌──────────────────────────┐
          │ WalletReader/Transfer   │  │ PaymentRepository        │   порты
          └───────────┬─────────────┘  └────────────┬─────────────┘
                      ▼                             ▼
          BitcoinCoreWallet (RPC)          SqlitePaymentRepository     исходящие адаптеры
          FakeWallet (тесты)               InMemoryPaymentRepository
```

Зависимости направлены **внутрь**: `api` → `services` → `domain`. Адаптеры зависят от портов, а сервис от адаптеров не зависит. Все реализации «собираются» в одном месте: `app/main.py`. Это корень композиции (composition root).

| Папка | Что внутри | От чего зависит |
|---|---|---|
| `app/domain/` | `Payment`, `PaymentStatus`, `PaymentStateMachine`, доменные ошибки | ни от чего |
| `app/ports/` | интерфейсы `WalletReader`, `WalletTransfer`, `WalletGateway`, `PaymentRepository` | domain |
| `app/services/` | `PaymentService`: сценарии «оплата», «возврат», «просмотр» | domain, ports |
| `app/adapters/` | Bitcoin Core RPC, SQLite, тестовые реализации | ports, domain, `requests`, `sqlite3` |
| `app/api/` | HTTP-роуты, схемы JSON, проверка API-ключа | services, FastAPI |
| `app/main.py` | сборка приложения, выбор реализаций, коды ошибок | всё |

## Где в коде SOLID

### S — Single Responsibility (одна причина для изменения)

Каждый класс отвечает за одну вещь:

| Класс | Его единственная задача |
|---|---|
| `PaymentStateMachine` (`domain/state_machine.py`) | решать, разрешён ли переход статуса |
| `PaymentService` (`services/payment_service.py`) | выполнять сценарий оплаты и возврата |
| `BitcoinRpcClient` (`adapters/bitcoin_rpc.py`) | отправить JSON-RPC запрос и разобрать ответ |
| `BitcoinCoreWallet` (`adapters/bitcoin_core_wallet.py`) | переводить «язык» бизнес-логики в команды Bitcoin Core |
| `SqlitePaymentRepository` | сохранять и загружать платежи |
| `routes.py` | превращать HTTP в вызовы сервиса и обратно |

Пример: если Bitcoin Core поменяет формат RPC, изменится только `BitcoinRpcClient`. Если поменяются правила статусов, изменится только `PaymentStateMachine`.

### O — Open/Closed (открыт для расширения, закрыт для изменения)

Чтобы добавить Ethereum-кошелёк, пишем **новый** класс `EthereumWallet(WalletGateway)` и подключаем его в `main.py`. `PaymentService` при этом **не меняется**. Так же можно заменить SQLite на PostgreSQL: новый `PostgresPaymentRepository(PaymentRepository)`.

### L — Liskov Substitution (подстановка)

`BitcoinCoreWallet` и `FakeWallet`, `SqlitePaymentRepository` и `InMemoryPaymentRepository` взаимозаменяемы. `PaymentService` работает с любой парой одинаково. Это доказывают тесты: `tests/test_payment_service.py` проверяет всю логику на подделках, а в продакшене подставляются настоящие классы. Переменная `WALLET_BACKEND=fake` запускает сервис вообще без биткоин-узла.

### I — Interface Segregation (маленькие интерфейсы)

Кошелёк описан не одним «толстым» интерфейсом, а двумя:
- `WalletReader`: только чтение (`wallet_exists`, `get_customer_info`, `get_balance`);
- `WalletTransfer`: только переводы (`charge`, `refund`).

`PaymentService` получает их как **две отдельные зависимости** (`wallet_reader`, `wallet_transfer`). Например, будущему сервису отчётов понадобится только `WalletReader`, и доступа к переводам денег у него не будет. `PaymentRepository` тоже отдельный интерфейс и не смешан с кошельком.

### D — Dependency Inversion (зависимость от абстракций)

`PaymentService` зависит от абстракций (`PaymentRepository`, `WalletReader`, `WalletTransfer`), а не от `BitcoinCoreWallet` или SQLite. Конкретные объекты передаются в конструктор (**Dependency Injection**) в `app/main.py`:

```python
wallet = build_wallet(settings)                 # BitcoinCoreWallet или FakeWallet
repo = SqlitePaymentRepository(settings.db_path)
service = PaymentService(repo, wallet_reader=wallet, wallet_transfer=wallet)
```

## Другие решения, о которых могут спросить

- **Почему Bitcoin Core?** Это эталонный open-source кошелёк и узел (MIT-лицензия) с JSON-RPC API и поддержкой нескольких кошельков. Режим regtest позволяет тестировать без настоящих денег.
- **Почему статусы сохраняются после каждого шага?** Если сервис упадёт посреди оплаты, будет видно, на каком шаге он остановился.
- **Почему `Decimal`, а не `float`?** `0.1 + 0.2 != 0.3` во float. С деньгами такие ошибки недопустимы.
- **Защита от двойного списания:** уникальная пара `merchant_id + order_id` (BR-4).
- **Доменные ошибки → HTTP-коды** переводятся в одном месте (`main.py`), поэтому бизнес-логика не знает про HTTP.
