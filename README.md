# GTA5RP Family Finances Bot — Modular Build

Проект разнесён на независимые компоненты:

- `core/` — запуск бота, конфиг, БД, общие утилиты
- `modules/bank/` — банк, взносы, кредиты, погашение, долги, топ, логи
- `modules/passports/` — паспортный контроль и телефоны
- `modules/cars/` — автопарк, выдача/возврат, админ-команды `/add_car`, `/delete_car`, `/change_car`
- `modules/bp/` — embed с Bonus Points

## Railway

Procfile уже настроен:

```txt
worker: python main.py
```

Обязательная переменная окружения:

```txt
TOKEN=токен_бота
```

Остальные ID каналов и ролей имеют текущие значения по умолчанию, но их можно переопределить через Variables Railway:

```txt
GUILD_ID
HEAD_ROLE_ID
CHANNEL_REQUEST
CHANNEL_REPORT
CHANNEL_APPROVE
PASSPORT_CHANNEL
CAR_CHANNEL
CAR_ADMIN_CHANNEL
BP_CHANNEL
DATABASE_PATH
```

По умолчанию база хранится в `/data/family.db`, как и раньше.


## Contracts V1 / PostgreSQL

Railway variables required:

```env
DATABASE_URL=postgresql://...
CHANNEL_CONTRACT_PANEL=1505366731881975919
CHANNEL_CONTRACT_LOGS=1505366841185406986
CHANNEL_ADMIN_ALERTS=1505366944235389040
ROLE_FAMILY=1447314644141347008
ROLE_WRESTLER=1447315536550559846
MAX_CONTRACT_MEMBERS=5
```

OCR uses template matching. Put icon images here:

```text
assets/ocr/templates/strength.png
assets/ocr/templates/shooting.png
...
assets/ocr/templates/reporter_rank.png
```

Both personnel OCR and contract OCR use the same rule: `icon -> number near icon`.
