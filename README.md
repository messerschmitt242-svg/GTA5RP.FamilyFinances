# GTA5RP Family Finances Bot — Modular Build

Проект разнесён на независимые компоненты:

- `core/` — запуск бота, конфиг, БД, общие утилиты
- `modules/bank/` — банк, взносы, кредиты, погашение, долги, топ, логи
- `modules/passports/` — паспортный контроль и телефоны
- `modules/cars/` — автопарк, выдача/возврат, админ-команды `/add_car`, `/delete_car`, `/change_car`
- `modules/bp/` — embed с Bonus Points
- `modules/contracts/` — ручная система контрактов, людей, навыков, активных контрактов и истории

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
DATABASE_URL
CHANNEL_CONTRACT_PANEL
CHANNEL_CONTRACT_LOGS
CHANNEL_ADMIN_ALERTS
ROLE_FAMILY
ROLE_WRESTLER
MAX_CONTRACT_MEMBERS
```

## Contracts / PostgreSQL

OCR полностью удалён. Контракты и люди добавляются вручную через кнопку панели.

Кнопки панели контрактов:

- `Добавить контракт`
- `Добавить человека`
- `Редактировать навык`
- `Активные`
- `История контрактов`

Лимиты для навыков человека и редактирования:

- обычные навыки/клубы — максимум 5
- Рыбалка — максимум 6
- Стрельба — максимум 10
- Мотоклуб — максимум 4
- все ранги — максимум 15

Из-за ограничения Discord Select максимум в 25 пунктов полный список разбит на категории: навыки, ранги, клубы.
