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
