# Установка музыкального модуля Wayne Bot

## 1. Скопировать файлы

Скопируй папку:

```text
modules/music/
```

в свой проект рядом с остальными модулями.

## 2. Добавить зависимости

В `requirements.txt` добавь:

```text
wavelink>=3.5.2
PyNaCl>=1.5.0
```

`PyNaCl` нужен для voice-подключений Discord.

## 3. Добавить переменные в Railway Bot Service

В сервисе основного Discord-бота:

```env
LAVALINK_HOST=твой-домен.up.railway.app
LAVALINK_PORT=443
LAVALINK_PASSWORD=тот_же_пароль_что_в_Lavalink
LAVALINK_SECURE=true
MUSIC_RECONNECT_INTERVAL=600
MUSIC_DEFAULT_VOLUME=70
MUSIC_MAX_VOLUME=150
```

`LAVALINK_HOST` указывать без `https://`.

## 4. Подключить модуль в core/bot.py

В список extensions добавь:

```python
"modules.music.cog",
```

Пример:

```python
extensions = [
    "modules.bank.bank",
    "modules.cars.cog",
    "modules.contracts.cog",
    "modules.music.cog",
]
```

## 5. Задеплоить

Commit → Push → Railway Redeploy.

## 6. Проверка в Discord

В Discord выполни:

```text
/music status
```

Потом:

```text
/music panel
/music play never gonna give you up
```

## Важное ограничение Discord

Один bot account может играть только в одном голосовом канале одного Discord-сервера одновременно.

То есть схема:

```text
1 сервер = 1 активный voice-плеер
```

Если нужно 5 voice-каналов одновременно, нужны 5 отдельных Discord bot accounts/tokens, подключенных к одному Lavalink.

## Источники поиска

Модуль ищет так:

1. Если ссылка — пытается открыть ссылку напрямую.
2. Если текст — сначала `scsearch:` SoundCloud.
3. Потом `ytsearch:` YouTube.

## Если музыка не работает

Проверь:

```text
/music status
```

Если Lavalink offline:

- проверь переменные Railway;
- проверь пароль;
- `LAVALINK_HOST` без `https://`;
- `LAVALINK_PORT=443`;
- `LAVALINK_SECURE=true`.

