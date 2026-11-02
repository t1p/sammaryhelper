# Step 7 — Acceptance Criteria: Deploy & Acceptance (LazGram Cache)

## Prerequisites
- Миграции 003 и 003_down применены на x200
- PostgreSQL на x200 доступен с роли tg_map_rw
- pg_hba.conf содержит запись для tg_map_rw (если потребовалась)
- LAZGRAM_CACHE_ENABLED в окружении установлена как needed

---

## Test 1: Миграция 003 идемпотентна

### Command
```bash
psql -v ON_ERROR_STOP=1 -d telegram_summarizer -f migrations/003_tg_map_message_cache.sql
psql -v ON_ERROR_STOP=1 -d telegram_summarizer -f migrations/003_tg_map_message_cache.sql  # повторно
```

### Expected
- Обе команды завершаются успешно без ошибок
- Таблица `tg_map.message_cache` существует
- Индексы на `(account_key, chat_id)` и `(sent_at)` существуют

### Verification
```sql
-- На суперюзере или tg_archive_ro:
SELECT EXISTS (SELECT 1 FROM information_schema.tables 
    WHERE table_schema='tg_map' AND table_name='message_cache') AS table_exists;
-- ожидаем: table_exists = true

SELECT indexname FROM pg_indexes 
    WHERE schemaname='tg_map' AND tablename='message_cache';
-- ожидаем: message_cache_account_chat_idx, message_cache_sent_at_idx
```

---

## Test 2: LAZGRAM_CACHE_ENABLED=false → Backward Compatibility

### Command
```bash
export LAZGRAM_CACHE_ENABLED=false
python -m lazgram_sync.cli --config chats.example.json --dry-run
```

### Expected
- Синк работает без ошибок
- Логируется предупреждение: "LAZGRAM_CACHE_ENABLED=false: синк работает в режиме совместимости"
- В tg_map.message_cache ничего не записывается
- В public.dialogs/messages данные не пишутся (dry-run)

### Verification
```sql
SELECT COUNT(*) FROM tg_map.message_cache;
-- ожидаем: 0 (или столько же, сколько было до синка)
```

---

## Test 3: LAZGRAM_CACHE_ENABLED=true → Cache Write

### Command
```bash
export LAZGRAM_CACHE_ENABLED=true
python -m lazgram_sync.cli --config chats.example.json
```

### Expected
- Синк завершается успешно
- Логируется: "LAZGRAM_CACHE_ENABLED=true: кэшируем сообщения в tg_map.message_cache"
- В tg_map.chat, tg_map.chat_alias, tg_map.message_cache записаны данные
- В tg_map.sync_run записана запись о прогоне

### Verification
```sql
-- Счётчики tg_map:
SELECT 
    (SELECT COUNT(*) FROM tg_map.chat) AS chats,
    (SELECT COUNT(*) FROM tg_map.chat_alias) AS aliases,
    (SELECT COUNT(*) FROM tg_map.message_cache) AS cached_messages,
    (SELECT COUNT(*) FROM tg_map.sync_run) AS sync_runs;

-- Структура сообщения в кэше:
SELECT account_key, chat_id, message_id, sender_id, sent_at, cached_at
    FROM tg_map.message_cache LIMIT 1;
-- ожидаем: все поля заполнены, cached_at ~ now()

-- Запись в sync_run:
SELECT source, started_at, finished_at, rows_seen, rows_written, status
    FROM tg_map.sync_run ORDER BY started_at DESC LIMIT 1;
-- ожидаем: source='lazgram_sync', status='success', rows_written > 0
```

---

## Test 4: Cache-Hit in MCP Server

### Command
```bash
export LAZGRAM_CACHE_ENABLED=true
python -c "
import asyncio
from mcp_archive_server.db import ArchiveDB

async def test_cache_hit():
    db = ArchiveDB()
    await db.connect()
    
    # Предполагаем, что в tg_map.message_cache есть сообщения для чата -1001234567890
    result = await db.get_recent_messages(dialog_id=-1001234567890)
    
    print(f'Coverage: {result[\"coverage\"]}')
    print(f'Messages count: {len(result[\"messages\"])}')
    if result['coverage'] == 'cached':
        print(f'Cache hit! cached_at: {result.get(\"cached_at\")}')
    
    await db.close()

asyncio.run(test_cache_hit())
"
```

### Expected
- Если в кэше есть сообщения: `coverage='cached'`, сообщения возвращены из tg_map.message_cache
- Если кэша нет: `coverage='archive'` или `coverage='none'`, сообщения из public.messages или подсказка

### Verification
```python
# Проверка в коде:
assert result['coverage'] in ('cached', 'archive', 'none')
assert isinstance(result['messages'], list)
```

---

## Test 5: Role-Based Access Control

### Verification
```bash
# Проверить, что tg_map_rw может писать в message_cache:
PGPASSFILE=~/.pgpass psql \
  "host=localhost user=tg_map_rw dbname=telegram_summarizer" \
  -c "INSERT INTO tg_map.message_cache 
      (account_key, chat_id, message_id, sender_id, text, sent_at) 
      VALUES ('igor', 100, 1, 200, 'test', now())"
# ожидаем: успех

# Проверить, что tg_archive_ro может читать, но не писать:
PGPASSFILE=~/.pgpass psql \
  "host=localhost user=tg_archive_ro dbname=telegram_summarizer" \
  -c "SELECT COUNT(*) FROM tg_map.message_cache"
# ожидаем: успех (SELECT)

PGPASSFILE=~/.pgpass psql \
  "host=localhost user=tg_archive_ro dbname=telegram_summarizer" \
  -c "DELETE FROM tg_map.message_cache LIMIT 1"
# ожидаем: ошибка permission denied
```

---

## Test 6: pg_hba.conf Validation

### Verification
```bash
# На x200:
sudo -u postgres psql -c "SELECT line_number, type, database, user_name, auth_method \
    FROM pg_hba_file_rules WHERE user_name='tg_map_rw' ORDER BY line_number"

# ожидаем: запись вроде:
# line_number | type  | database | user_name | auth_method
#    N        | local | all      | tg_map_rw | md5 (или scram-sha-256)
```

### Expected
- Запись tg_map_rw в pg_hba.conf существует и позволяет подключение
- Если новая запись добавлена, сделан `SELECT pg_reload_conf()` (без restart!)

---

## Test 7: Smoke Test — resolve_chat()

### Command
```bash
export LAZGRAM_CACHE_ENABLED=true
python -c "
import asyncio
from mcp_archive_server.db import ArchiveDB

async def smoke_test():
    db = ArchiveDB()
    await db.connect()
    
    # Ожидаемый результат: resolve_chat('стоицизм') -> chat_id=-1001372152834
    result = await db.resolve_chat('стоицизм', '79253010707')
    
    if result['candidates']:
        print(f'✅ resolve_chat found: {result[\"candidates\"][0]}')
    else:
        print(f'❌ resolve_chat returned empty')
    
    await db.close()

asyncio.run(smoke_test())
"
```

### Expected
- `resolve_chat('стоицизм', '79253010707')` возвращает список candidates
- Первый кандидат имеет `chat_id=-1001372152834` (или близкое значение)
- `unambiguous=True`, если это единственный результат

---

## Test 8: Check Script Green

### Command
```bash
scripts/check-archive-mcp.sh
```

### Expected Output
```
=== Роли ===
  OK: роль tg_archive_ro существует
  OK: роль tg_map_rw существует

=== Гранты read-only роли ===
  OK: tg_archive_ro: default_transaction_read_only=on

=== tg_map.v_chat отвечает ===
  OK: tg_map.v_chat: NNNN строк

=== Запись отклоняется ===
  OK: запись отклонена

=== ai_requests/ai_responses недоступны ===
  OK: ai_requests недоступен

=== Счётчики архива ===
  OK: dialogs|messages|topics = 2010|49607|221

=== MCP-сервер поднимается (.venv-archive-mcp) ===
  OK: resolve_chat('стоицизм') отработал

...

=== ИТОГ: ЗЕЛЁНЫЙ ===
```

---

## Test 9: Integration — Full Flow

### Command
```bash
#!/bin/bash
set -e

export LAZGRAM_CACHE_ENABLED=true

# Пагинированный синк 3 чатов
python -m lazgram_sync.cli --config chats_test.json

# Проверить, что сообщения кэшированы
psql -d telegram_summarizer -c "SELECT COUNT(*) as cached_messages FROM tg_map.message_cache;"

# Запустить MCP, проверить cache-hit
python -c "
import asyncio
from mcp_archive_server.db import ArchiveDB

async def e2e_test():
    db = ArchiveDB()
    await db.connect()
    
    # Получить любой чат из кэша
    rows = await db.connection_pool.fetch('SELECT DISTINCT chat_id FROM tg_map.message_cache LIMIT 1')
    if rows:
        chat_id = rows[0]['chat_id']
        result = await db.get_recent_messages(chat_id)
        assert result['coverage'] == 'cached', f'Expected cached, got {result[\"coverage\"]}'
        print(f'✅ Cache hit for chat {chat_id}')
    
    await db.close()

asyncio.run(e2e_test())
"

echo "✅ All integration tests passed"
```

### Expected
- Синк завершается успешно
- В tg_map.message_cache > 0 строк
- get_recent_messages() возвращает coverage='cached' для кэшированных чатов

---

## Summary Table

| Критерий | Статус | Дата | Ответственный |
|----------|--------|------|----------------|
| Миграция 003 идемпотентна | ☐ | | |
| LAZGRAM_CACHE_ENABLED=false работает | ☐ | | |
| LAZGRAM_CACHE_ENABLED=true пишет в кэш | ☐ | | |
| Cache-hit работает в MCP | ☐ | | |
| Role-based access контролируется | ☐ | | |
| pg_hba.conf настроен | ☐ | | |
| resolve_chat('стоицизм') работает | ☐ | | |
| check-archive-mcp.sh зелёный | ☐ | | |
| Full integration flow работает | ☐ | | |

---

## Deployment Checklist

- [ ] Прочитал контракт и все acceptance criteria
- [ ] Миграции 003 и 003_down готовы и протестированы locally
- [ ] Feature flag LAZGRAM_CACHE_ENABLED задокументирован
- [ ] Все unit тесты проходят (pytest)
- [ ] check-archive-mcp.sh готов к запуску на x200
- [ ] pg_hba.conf предварительно проверен (нужна ли запись tg_map_rw?)
- [ ] Готовы к откату (migrations/down/003_down.sql)
- [ ] Логирование покрывает все critical paths

---

## Notes for Codex

- При deployment на x200 необходимо:
  1. Применить миграции в порядке 001, 002, 003
  2. Убедиться, что pg_hba.conf содержит запись для tg_map_rw (или добавить + pg_reload_conf())
  3. Запустить check-archive-mcp.sh для валидации
  4. Выполнить smoke test resolve_chat('стоицизм')
  5. Запустить первый batch-синк с LAZGRAM_CACHE_ENABLED=true
  6. Проверить cache-hit в get_recent_messages()

- При необходимости отката: DROP TABLE IF EXISTS tg_map.message_cache CASCADE;
- Feature flag позволяет отключить кэш для совместимости: LAZGRAM_CACHE_ENABLED=false
