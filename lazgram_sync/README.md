# lazgram_sync

Обновляет архив Sammaryhelper (та же PostgreSQL, что и `mcp_archive_server`/
`fastgpt_exporter`) через живой Telegram-аккаунт, подключённый как MCP-
коннектор [LazGram](https://github.com/t1p/lazgram-node) — вместо
собственного Telethon-клиента Sammaryhelper. Синк — это MCP-*клиент*: сам
поднимает `lazgram-mcp.mjs` по stdio, читает список чатов и историю
сообщений по конфигу (список чатов + дата "с какого числа") и пишет их
через `Sammaryhelper.db_handler.DatabaseHandler.cache_dialogs()`/
`cache_messages()` — тот же путь записи, что использует сам Sammaryhelper,
без второй, расходящейся со временем схемы.

## Ограничения (важно прочитать перед использованием)

- **Имена отправителей не резолвятся.** LazGram отдаёт только `senderId`
  (число) — `sender_name` в БД будет строкой из этого id, а не именем.
  Резолвинг имён потребовал бы отдельного инструмента у LazGram, которого
  сейчас нет.
- **Папки (Telegram folders) не приходят от LazGram.** Если чат уже был
  закеширован раньше (например, через GUI Sammaryhelper) и там была папка —
  синк её сохранит. Для нового чата папка будет `null`.
- **Список чатов ограничен 200** (максимум `lazgram_chats`). Если у чата,
  заданного по `chat_id`, нет соответствия в этом списке (аккаунт с >200
  чатов, архивный чат и т.п.), диалог будет закеширован с временным именем
  `Chat <id>` — сообщения при этом всё равно синхронизируются корректно.
- **`account_id` в конфиге — это НЕ id аккаунта LazGram.** Это ключ
  партиционирования в таблицах `dialogs`/`messages` (обычно телефон или
  username Telegram-аккаунта — то, что уже лежит в столбце `account_id`
  у существующих строк). Если указать другое значение, синк создаст
  отдельный, не связанный со старым архивом раздел данных для того же
  реального аккаунта. Проверить, что уже есть в архиве:
  `python -m mcp_archive_server` → инструмент `list_accounts`, либо
  `SELECT DISTINCT account_id FROM dialogs;` напрямую. При расхождении
  синк печатает предупреждение, но не блокирует запуск.
- **Пагинация истории ограничена `max_pages`** (по умолчанию 200 страниц
  по 100 сообщений = до 20000 сообщений на чат за прогон) — защита от
  ухода в историю чата на дату, которой в нём никогда не было. При
  достижении лимита в сводке будет пометка, что нужно перезапустить синк
  ещё раз (последняя полученная страница станет стартовой точкой при
  следующем запуске, если поднять `since` до даты последнего сообщения).

## Настройка подключения

БД — те же переменные, что у `mcp_archive_server`/`fastgpt_exporter`:
`TG_ARCHIVE_DB_HOST/PORT/NAME/USER/PASSWORD` или `TG_ARCHIVE_DB_CONFIG_FILE`.

LazGram:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `LAZGRAM_SYNC_NODE_BIN` | путь до `node` | `node` |
| `LAZGRAM_SYNC_MCP_SCRIPT` | путь до `lazgram-node/src/interface/mcp/lazgram-mcp.mjs` | обязателен |
| `LAZGRAM_SYNC_ACCOUNT` | id аккаунта LazGram (напр. `prod`) — сервис этого аккаунта должен уже быть запущен (`systemctl --user status lazgram@<id>`) | обязателен |
| `LAZGRAM_SYNC_INITIATOR` | что попадёт в audit-log LazGram | `sammaryhelper-sync` |
| `LAZGRAM_SYNC_TIMEOUT_MS` | таймаут запроса к LazGram | `30000` |

Синк всегда запрашивает у LazGram политику `read-only` для аккаунта —
писать/отправлять сообщения он не может и не должен.

## Конфиг чатов (`--config chats.json`)

```json
{
  "account_id": "+79990001122",
  "since": "2026-09-01T00:00:00",
  "max_pages": 200,
  "chats": [
    { "chat_id": -1001234567890 },
    { "username": "some_channel" },
    { "chat_id": 123456789, "since": "2026-09-10T00:00:00" }
  ]
}
```

- `account_id` — см. предупреждение выше.
- `since` — глобальная дата "с какого числа тянуть сообщения" (ISO-8601,
  без сообщений старше неё). Можно переопределить на уровне отдельного
  чата.
- `chats[]` — каждый элемент задаёт чат по `chat_id` **или** `username`
  (не оба сразу — `username` резолвится в `chat_id` самим LazGram).

Пример — `chats.example.json` в этой же папке.

## Установка и запуск

```bash
cd lazgram_sync
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Запускать из корня репозитория (нужен доступ к `Sammaryhelper.db_handler`
и `mcp_archive_server.db`):

```bash
export TG_ARCHIVE_DB_CONFIG_FILE=/путь/до/Sammaryhelper/configs/config_0707.py
export LAZGRAM_SYNC_MCP_SCRIPT=/путь/до/lazgram-node/src/interface/mcp/lazgram-mcp.mjs
export LAZGRAM_SYNC_ACCOUNT=prod

python -m lazgram_sync.cli --config lazgram_sync/chats.example.json --dry-run -v
python -m lazgram_sync.cli --config lazgram_sync/chats.example.json
```

`--dry-run` реально обращается к LazGram (нужно знать, что было бы
синхронизировано), но не пишет в БД.

## Периодический запуск

Планировщик (cron/systemd timer) на том же хосте, где живёт нужный
`lazgram@<account>.service`. Пример cron (каждый час):

```
0 * * * * cd /path/to/sammaryhelper && LAZGRAM_SYNC_MCP_SCRIPT=... LAZGRAM_SYNC_ACCOUNT=prod TG_ARCHIVE_DB_CONFIG_FILE=... venv/bin/python -m lazgram_sync.cli --config lazgram_sync/chats.json >> lazgram_sync.log 2>&1
```

Держите `since` в конфиге не сильно в прошлом (например, «последние 2
дня») для регулярных прогонов — так каждый запуск быстрый, а
`cache_messages`/`cache_dialogs` идемпотентны (upsert по id), так что
повторная синхронизация уже виденных сообщений безвредна.
