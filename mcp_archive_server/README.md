# telegram-archive MCP-сервер

MCP-сервер только для чтения, который отдаёт агенту архивные данные о
чатах, группах и каналах Telegram — те, что приложение
[Sammaryhelper](../README.md) когда-то закешировало в PostgreSQL
(таблицы `dialogs`, `messages`, `topics`, см. `Sammaryhelper/db_handler.py`).

Идея: у вас уже есть отдельный MCP-коннектор к живому Telegram-аккаунту
(через MTProto/Telethon-based клиент). Дёргать его на каждый вопрос
"а что это за чат такой-то" — дорого и медленно. Этот сервер работает как
справочник: агент сначала ищет чат здесь (мгновенно, без сети до
Telegram), получает `id`, тип, папку и историческую сводку — и только
затем, если нужно, идёт в живой Telegram-коннектор точечно, уже зная,
что именно спрашивать.

Данные в архиве могут быть устаревшими (это снапшот на момент последней
работы Sammaryhelper). Каждый ответ содержит `cached_at` и `is_stale` —
ориентир для агента, стоит ли перепроверять чат вживую.

## Инструменты

| Инструмент | Назначение |
|---|---|
| `list_accounts` | какие Telegram-аккаунты вообще есть в архиве |
| `search_chats(query, chat_type?, account_id?, limit?)` | найти чат/группу/канал по части названия |
| `list_chats(chat_type?, account_id?, limit?, offset?)` | постранично весь список |
| `get_chat(dialog_id? , name?, account_id?)` | карточка чата + статистика по сообщениям |
| `get_recent_messages(dialog_id, account_id?, limit?)` | последние закешированные сообщения чата |
| `search_messages(query, dialog_id?, account_id?, limit?)` | поиск по тексту закешированных сообщений |
| `get_archive_stats` | сводка по всему архиву (сколько чатов/сообщений, свежесть) |

`chat_type` принимает `channel` / `group` / `private` (а также русские
`Канал` / `Чат` / `Личка` — так, как реально хранит Sammaryhelper).

## Установка

```bash
cd mcp_archive_server
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка подключения к БД

Сервер не создаёт и не меняет таблицы — только читает то, что уже
насчитал Sammaryhelper. Подключение настраивается переменными окружения:

```bash
export TG_ARCHIVE_DB_HOST=x200          # хост/IP компьютера с Postgres
export TG_ARCHIVE_DB_PORT=5432
export TG_ARCHIVE_DB_NAME=telegram_summarizer   # имя БД sammaryhelper
export TG_ARCHIVE_DB_USER=postgres
export TG_ARCHIVE_DB_PASSWORD=...
```

Если сервер запускается на том же компьютере (x200), где уже настроен
сам Sammaryhelper, можно вместо переменных окружения указать путь к его
конфигу и взять `host/port/database/user/password` прямо оттуда:

```bash
export TG_ARCHIVE_DB_CONFIG_FILE=/path/to/Sammaryhelper/configs/config_0707.py
```

(Явные `TG_ARCHIVE_DB_*` переменные всегда имеют приоритет над файлом.)

По умолчанию считаем данные устаревшими через 24 часа без синхронизации —
это настраивается через `TG_ARCHIVE_STALE_AFTER_HOURS`.

## Запуск и подключение к MCP-клиенту

Сервер общается по stdio, как обычный MCP-сервер:

```bash
python -m mcp_archive_server.server
```

Пример конфигурации (Claude Desktop / любой MCP-клиент со stdio-транспортом),
рядом с уже настроенным коннектором к живому Telegram-аккаунту:

```json
{
  "mcpServers": {
    "telegram-archive": {
      "command": "/path/to/mcp_archive_server/venv/bin/python",
      "args": ["-m", "mcp_archive_server.server"],
      "env": {
        "TG_ARCHIVE_DB_HOST": "x200",
        "TG_ARCHIVE_DB_PORT": "5432",
        "TG_ARCHIVE_DB_NAME": "telegram_summarizer",
        "TG_ARCHIVE_DB_USER": "postgres",
        "TG_ARCHIVE_DB_PASSWORD": "..."
      }
    },
    "telegram-live": {
      "command": "...",
      "args": ["..."]
    }
  }
}
```

Если Postgres слушает только на `localhost` компьютера x200, а MCP-клиент
работает на другой машине, потребуется SSH-туннель или проброс порта —
это уже вопрос сетевой топологии, не самого сервера.

## Рекомендуемый промпт/инструкция для агента

Сам сервер уже отдаёт MCP-клиенту `instructions` с этой логикой, но если
нужно продублировать в системном промпте агента:

> При любом запросе про Telegram-чат сначала используй инструменты
> `telegram-archive` (search_chats/get_chat), чтобы дёшево получить id,
> тип и контекст. Обращайся к живому Telegram-коннектору только если чат
> не найден в архиве или его данные помечены `is_stale: true`.
