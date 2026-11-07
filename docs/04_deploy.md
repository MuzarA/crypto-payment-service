# Запуск на облачном сервере (DigitalOcean)

Подойдёт любой Linux-сервер с Docker. Ниже пример для DigitalOcean.

## 1. Создать сервер

1. DigitalOcean → **Create → Droplets**.
2. Образ: **Ubuntu 24.04**. Можно сразу выбрать в Marketplace образ **Docker on Ubuntu**, тогда шаг 2 не нужен.
3. Размер: самый дешёвый вариант с **1–2 GB RAM** (regtest почти не требует ресурсов).
4. Доступ: SSH-ключ или пароль.
5. Скопировать публичный IP сервера.

## 2. Установить Docker (если образ обычный Ubuntu)

```bash
ssh root@<IP>
curl -fsSL https://get.docker.com | sh
```

## 3. Загрузить проект и запустить

```bash
# на своём компьютере
scp crypto-payment-service.zip root@<IP>:~

# на сервере
apt-get install -y unzip
unzip crypto-payment-service.zip && cd crypto-payment-service
cp .env.example .env
nano .env                      # поменять BITCOIN_RPC_PASSWORD и API-ключи
docker compose up -d --build   # первая сборка ~2-3 минуты
docker compose ps              # оба контейнера: running / healthy
```

Если проект лежит на GitHub, вместо `scp` можно сделать `git clone <ваш-репозиторий>`.

## 4. Создать тестовых клиентов

```bash
docker compose exec api python -m scripts.seed_regtest
```

Результат:
- `alice`: 50 BTC (оплата пройдёт);
- `bob`: 0.001 BTC (не хватит денег);
- `carol`: кошелька нет.

## 5. Открыть порт и проверить

```bash
ufw allow 22 && ufw allow 8000 && ufw --force enable   # если включён firewall
curl http://<IP>:8000/health                           # {"status":"ok"}
```

В браузере: `http://<IP>:8000/docs` открывает Swagger UI. В нём можно отправлять запросы кнопкой **Try it out** (ключ `demo-key` вводится в поле `X-API-Key`).

## 6. Демонстрация для мидтерма

С любого компьютера, где есть bash и curl:

```bash
API_URL=http://<IP>:8000 API_KEY=demo-key ./scripts/demo.sh
```

Скрипт по очереди показывает: успешную оплату, нехватку денег, отсутствие кошелька, дубль заказа, статус платежа, возврат, повторный возврат и неверный ключ.

## Полезные команды

```bash
docker compose logs -f api                 # логи сервиса (каждый шаг платежа)
docker compose logs -f bitcoind            # логи узла
docker compose exec bitcoind bitcoin-cli -regtest \
  -rpcuser=bitcoin -rpcpassword=<пароль> -rpcwallet=alice getbalance
docker compose restart api                 # перезапуск
docker compose down                        # остановить (данные сохранятся в томах)
docker compose down -v                     # остановить и удалить все данные
```

## Запуск на Windows одной командой (без Docker)

Нужен Python 3.10+ (`winget install Python.Python.3.12`). Откройте PowerShell и вставьте:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/MuzarA/crypto-payment-service/main/scripts/run_local_windows.ps1 | iex"
```

Скрипт сделает всё сам:
1. скачает проект и Bitcoin Core;
2. запустит узел regtest и API на `http://127.0.0.1:8000`;
3. создаст клиентов, покажет демо и откроет Swagger UI.

Всё ставится в папку `%USERPROFILE%\crypto-payment-service-demo`. Чтобы остановить, выполните `Stop-Process -Name bitcoind` и закройте окно uvicorn.

## Запуск на своём компьютере без Docker (для отладки)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                                 # все тесты
WALLET_BACKEND=fake uvicorn app.main:app --reload      # без Bitcoin Core, с имитацией кошелька
```

В режиме `fake` уже есть клиенты `alice` (1 BTC) и `bob` (0.001 BTC). Откройте http://localhost:8000/docs.
