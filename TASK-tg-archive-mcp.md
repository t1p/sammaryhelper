# Задание: MCP-справочник Telegram-архива + приведение доступа к Postgres в порядок

Исполнитель: Claude Code, запущенный локально на x200 в `/home/voyager/dev/github/Sammaryhelper`.
Автор задания: агент Cowork (доступ был ограничен изолированной VM, отсюда передача работы).
Дата составления: 2026-09-16.

Заказчик — Игорь. Стиль работы: по существу, без лишних подтверждений там, где решение уже принято,
но с обязательной остановкой на границах, явно отмеченных ниже как **СТОП**.

---

## 0. Контекст: что уже разведано (перепроверять не нужно)

Всё ниже проверено запросами к живой системе 2026-09-15. Если что-то разошлось с реальностью —
это важный сигнал, сообщи и остановись.

### Репозиторий
- `/home/voyager/dev/github/Sammaryhelper`, remote `https://github.com/t1p/sammaryhelper.git`.
- Рабочее дерево на `master`. Ветка задачи — `claude/telegram-archive-mcp-21goj9` (коммит `82b4ab9`,
  «feat: MCP-сервер-справочник по архиву чатов/каналов Telegram»), уже зафетчена как
  `origin/claude/telegram-archive-mcp-21goj9`. Один коммит, 645 строк:
  `mcp_archive_server/{__init__,db,server}.py`, `requirements.txt`, `README.md`, правка корневого README.
- `venv/` — Python **3.13.1**, внутри уже есть **asyncpg 0.30.0** и Telethon 1.38. Нет пакета `mcp`.
- `Sammaryhelper/configs/` в `.gitignore` — секреты в git не утекли, проверено.

### База
- PostgreSQL **18.4**, `data_directory=/var/lib/postgres/data`, `hba_file=/var/lib/postgres/data/pg_hba.conf`,
  `config_file=/var/lib/postgres/data/postgresql.conf`, сокет `/run/postgresql`, `listen_addresses=localhost`,
  `port=5432`, `ssl=off`, `password_encryption=scram-sha-256`.
- База архива называется **`telegram_summarizer`** (не `sammary_helper`), 55 МБ. Соседи в кластере:
  `infosoft` (2218 МБ), `infosoft_mai` (2027 МБ), `maymunai` (9 МБ), `postgres`.
- Схема только `public`. Таблицы и владельцы:
  | таблица | строк | владелец |
  |---|---|---|
  | `dialogs` | 2010 | postgres |
  | `messages` | 49 607 (46 МБ) | telegram_user |
  | `topics` | 221 | telegram_user |
  | `ai_requests` / `ai_responses` | лог промптов | postgres |
- Индексов, кроме первичных ключей, **нет**. PK: `dialogs(id)`, `messages(id, dialog_id)`, `topics(id, dialog_id)`.
- Один аккаунт: `dialogs.account_id = '79253010707'` (1267 «Личка», 505 «Канал», 238 «Чат»).
- Снапшот старый: `max(dialogs.updated_at)` = 2025-07-07, `max(messages.date)` = 2025-05-19.
- Сообщения есть только для **130 диалогов из 2010**. У пяти видны потолки синхронизации
  (10000, 10000, 2002, 1000, 1000) — данные заведомо неполные.
- 71 группа диалогов с неуникальными именами — поиск по имени без id принципиально неоднозначен.

### Связь с Lazgram
- `/home/voyager/dev/lazgram` — Node-сервис TDLib, systemd `--user` юнит `lazgram@<account>.service`,
  NDJSON поверх unix-сокета `$XDG_RUNTIME_DIR/lazgram/<account>.sock`, MCP-адаптер
  `src/interface/mcp/lazgram-mcp.mjs`, регистратор `scripts/install-mcp.mjs`. Аккаунты: `prod`, `test`.
- **ID-конвенции совпадают**: архив хранит bot-API-нотацию (`-100…` для каналов/супергрупп,
  положительные для личек) — ровно ту же, что отдаёт TDLib. Проверено на живых данных:
  `-1001372152834` в архиве «🔥StoicStrategy: стоицизм в XXI в», сейчас в Telegram
  «🔥Сергей Сухов (стоицизм, развитие, ИИ)»; `232547433` — «Кирилл Гребнев» в обоих.
  То есть join по `chat_id` работает без трансляции, **а названия разошлись** — в этом и ценность:
  архив даёт исторические имена, которых в живом Telegram уже нет.
- Аккаунт в архиве обозначен телефоном `79253010707`, в Lazgram — ключом `prod`. Нужен маппинг,
  иначе агент подставит `account_id="prod"` и молча получит ноль строк.

### Доступ и безопасность (исходное состояние)
- `pg_hba.conf`: `local all all trust`, `host all all 127.0.0.1/32 trust`, `host all all ::1/128 trust`
  (+ такие же строки для `replication`).
- Роли и наличие пароля (`pg_authid`):
  | роль | login | super | пароль |
  |---|---|---|---|
  | `postgres` | да | **да** | **NULL — пароля нет вообще** |
  | `voyager` | да | нет | **NULL — пароля нет** |
  | `telegram_user` | да | нет | scram |
  | `infosoft` | да | нет | scram |
  | `maymun` | да | нет | scram |
  | `replicator` | да | нет (replication) | scram |
- То есть `postgres/postgres` из `Sammaryhelper/configs/*.json` и `config_0707.py` — **фикция**:
  сервер пароль не проверял, пускал `trust`. «Устранить пароль postgres/postgres» означает:
  задать роли `postgres` настоящий сильный пароль и вычистить строку `postgres` из конфигов приложения.
- Репликации нет: `pg_replication_slots` и `pg_stat_replication` пусты. Роль `replicator` не используется.
- Сейчас в кластере живут 6 idle-соединений роли `infosoft` с `::1`. **Нельзя определить, шлёт ли
  её приложение пароль** — при `trust` это неотличимо. Отсюда требование поэтапного включения scram.
- Изолированная Linux-VM Cowork видит хостовый Postgres как `10.0.2.2:5432`, а сервер видит её как
  `127.0.0.1`. Значит правило `host all all 127.0.0.1/32 trust` давало любому агенту в этой VM
  суперюзерский доступ ко всем пяти базам без пароля. Это и есть причина фазы E.

---

## 1. Правила работы

1. Работать в ветке задачи: `git switch -c claude/telegram-archive-mcp-21goj9 --track origin/claude/telegram-archive-mcp-21goj9`.
   `master` не трогать. В `origin` **не пушить** без явного разрешения Игоря.
2. Коммиты атомарные, по фазам, сообщения на русском, в стиле существующей истории.
3. Секреты: `~/.config/tg-archive/db.env` (`chmod 600`) и `~/.pgpass` (`chmod 600`). В репозиторий
   не попадает ни один пароль — проверить `git diff --cached` перед каждым коммитом.
4. Весь SQL — идемпотентными файлами `migrations/NNN_*.sql` в репозитории, применять через
   `psql -v ON_ERROR_STOP=1 -f`. Никакого SQL «руками мимо файлов». **К каждой миграции в том же
   коммите пишется парный откат `migrations/down/NNN_*.sql`.** Миграция без отката не считается готовой.
5. Схему `public` не менять: никаких `ALTER TABLE`, `CREATE INDEX`, `CREATE EXTENSION` на
   `dialogs`/`messages`/`topics` в этой работе. Индексы — отдельная фаза после замеров (см. §7).
6. **Перед первой правкой снять точку отката целиком — §7.1.** Перед каждым необратимым шагом —
   дополнительный бэкап (конкретика в фазах).
7. После каждой фазы прогонять `scripts/check-archive-mcp.sh` (§7.7). Красная проверка означает
   откат текущей фазы, а не переход к следующей.
8. Откат каждой фазы проверяется **до** перехода к следующей, а не сочиняется в момент аварии.
9. Фаза E выполняется **только после** явного «да» от Игоря на месте.

---

## 2. Фаза A — доступ к БД: read-only роль и схема маппинга

Цель: MCP-сервер физически не может писать в архив, а накапливаемый нами маппинг живёт в своей
схеме со своей пишущей ролью.

### A1. `migrations/001_tg_archive_ro.sql`

Применять от суперюзера (`sudo -u postgres psql -v ON_ERROR_STOP=1 -v ro_pw="$RO_PW" -f ...`).

- Создать (идемпотентно) роль `tg_archive_ro LOGIN PASSWORD :'ro_pw'`.
- `ALTER ROLE tg_archive_ro SET default_transaction_read_only = on;`
- `ALTER ROLE tg_archive_ro SET statement_timeout = '10s';`
- `ALTER ROLE tg_archive_ro SET idle_in_transaction_session_timeout = '30s';`
- `GRANT CONNECT ON DATABASE telegram_summarizer TO tg_archive_ro;`
- В базе `telegram_summarizer`: `GRANT USAGE ON SCHEMA public`, `GRANT SELECT ON public.dialogs,
  public.messages, public.topics`.
- **`ai_requests` и `ai_responses` не выдавать** — это логи промптов и ответов LLM, к справочнику
  чатов отношения не имеют, а утечь через агента могут.

Пароль: `openssl rand -base64 24`, сохранить в `~/.config/tg-archive/db.env` как `TG_ARCHIVE_DB_PASSWORD`
и строкой в `~/.pgpass` (`localhost:5432:telegram_summarizer:tg_archive_ro:<pw>`).

### A2. `migrations/002_tg_map.sql`

Схема `tg_map` в той же базе — намеренно не отдельная БД: так архив и маппинг джойнятся одним SQL,
а `public` Sammaryhelper остаётся нетронутым.

```sql
CREATE SCHEMA IF NOT EXISTS tg_map;
-- роль-писатель, ею пользуется только будущий sync-джоб, не MCP-сервер
CREATE ROLE tg_map_rw LOGIN PASSWORD :'map_pw';   -- идемпотентно
GRANT CONNECT ON DATABASE telegram_summarizer TO tg_map_rw;
GRANT USAGE, CREATE ON SCHEMA tg_map TO tg_map_rw;
GRANT USAGE ON SCHEMA tg_map TO tg_archive_ro;    -- MCP только читает
```

Таблицы:

- `tg_map.account(account_key text PK, archive_account_id text UNIQUE, lazgram_account text UNIQUE,
  tg_user_id bigint, note text, updated_at timestamptz default now())`.
  Сид: `('igor', '79253010707', 'prod')`.
- `tg_map.chat(account_key text NOT NULL REFERENCES tg_map.account, chat_id bigint NOT NULL,
  chat_type text, username text, title_live text, title_archive text,
  in_archive boolean NOT NULL DEFAULT false, is_live boolean NOT NULL DEFAULT false,
  first_seen timestamptz NOT NULL DEFAULT now(), last_seen timestamptz, source text NOT NULL,
  PRIMARY KEY (account_key, chat_id))`.
  `chat_type` хранить в TDLib-нотации (`private|group|supergroup|channel`), русские значения архива
  (`Личка|Чат|Канал`) конвертировать при загрузке.
- `tg_map.chat_alias(account_key, chat_id, alias text, source text, seen_at timestamptz default now(),
  PRIMARY KEY (account_key, chat_id, alias), FK на tg_map.chat ON DELETE CASCADE)`
  плюс `CREATE INDEX ... ON tg_map.chat_alias (lower(alias))`. Это индекс в **нашей** схеме — разрешён.
- `tg_map.sync_run(id bigserial PK, source text, started_at, finished_at, rows_seen int,
  rows_written int, status text, error text)` — без журнала через месяц никто не скажет, откуда
  в маппинге взялась строка.

Бэкфилл из архива (единственная массовая запись, ~2010 строк + алиасы):
`INSERT INTO tg_map.chat` из `public.dialogs` с `in_archive=true`, `source='archive'`,
`title_archive=name`, `last_seen=updated_at`; в `chat_alias` — то же имя с `source='archive'`.
Обязательно `ON CONFLICT DO NOTHING`/`DO UPDATE`, файл должен переприменяться без ошибок.

Вью `tg_map.v_chat` — единственная точка, куда ходит MCP: `tg_map.chat` LEFT JOIN `tg_map.account`
LEFT JOIN `public.dialogs` (по `chat_id` + `archive_account_id`), отдаёт
`title = coalesce(title_live, title_archive)`, оба названия по отдельности, `in_archive`, `is_live`,
`folder_id`, `archive_updated_at`.

**Важно: не тащить в эту вью статистику по сообщениям.** `count(*)` по `public.messages` без индекса
по `dialog_id` — seq scan 46 МБ на каждую строку вью. Статистика сообщений считается только точечно,
по одному запрошенному чату. Это же и есть место, где потом понадобится индекс (см. §7).

Гранты в конце: `GRANT SELECT ON ALL TABLES IN SCHEMA tg_map TO tg_archive_ro;` +
`ALTER DEFAULT PRIVILEGES IN SCHEMA tg_map GRANT SELECT ON TABLES TO tg_archive_ro;`

### A3. Проверка фазы A

```
psql "host=localhost user=tg_archive_ro dbname=telegram_summarizer" -c "SELECT count(*) FROM tg_map.v_chat;"
psql "host=localhost user=tg_archive_ro dbname=telegram_summarizer" -c "INSERT INTO tg_map.sync_run(source) VALUES ('x');"   # ДОЛЖНО упасть
psql "host=localhost user=tg_archive_ro dbname=telegram_summarizer" -c "SELECT * FROM ai_requests LIMIT 1;"                  # ДОЛЖНО упасть (нет прав)
```

---

## 3. Фаза B — правки MCP-сервера

Код ветки рабочий, но в нём три места, из-за которых агент будет систематически ошибаться.
Правки обязательны, не косметика.

### B1. Свежесть переписать честно
Сейчас `STALE_AFTER_HOURS=24` и булев `is_stale`. Архиву 14 месяцев → `is_stale=true` всегда,
и агент научится игнорировать флаг. Заменить на структуру вида:
```json
{"source": "archive", "snapshot_date": "2025-07-07", "age_days": 436,
 "confidence": {"chat_id": "high", "title": "low", "messages": "partial"}}
```
Разная семантика для разных полей: `chat_id` из архива не устаревает практически никогда,
название — часто, полнота сообщений — гарантированно частичная (130 диалогов из 2010).

### B2. Новый основной инструмент `resolve_chat(query, account="prod")`
Принимает что угодно — id, `@username`, точное или частичное название, старое название.
Порядок разрешения: числовой id → `username` → точный `lower(alias)` из `tg_map.chat_alias` →
`ILIKE` по `title_live`/`title_archive`. Возвращает список кандидатов, каждый с `match_kind`
(`id|username|alias_exact|title_ilike`) и полями вью. При единственном точном совпадении —
явный флаг `unambiguous: true`. Это главный вход; `search_chats`/`list_chats`/`get_chat` остаются,
но в инструкциях перестают быть первым выбором.

### B3. Алиасы аккаунтов
Переменная `TG_ARCHIVE_ACCOUNTS="prod:79253010707"` (список через запятую). Любой инструмент
принимает `account` в нотации Lazgram (`prod`) и сам переводит в `account_id` архива.
Если передан неизвестный ключ — внятная ошибка, а не пустой список.

### B4. Честное покрытие в `get_recent_messages`
Если для `chat_id` в `messages` нет ни одной строки — вернуть
`{"coverage": "none", "hint": "чат есть в архиве, но его сообщения не выкачивались; бери историю через lazgram_history"}`,
а не пустой массив, который агент прочтёт как «сообщений не было».

### B5. Инструкции сервера (`FastMCP(instructions=...)`)
Переписать под реальную связку:
> Архив — снапшот Telegram на 2025 год, один аккаунт. Он надёжен для `chat_id` и для **исторических**
> названий чатов; текущие названия и свежие сообщения бери в `lazgram`. Порядок: `resolve_chat` →
> получить `chat_id` → точечный вызов `lazgram_history`/`lazgram_chats` с этим id. Массовые обходы
> живого аккаунта не нужны и опасны (rate-limit).

### B6. Fail-fast по правам
На старте выполнить `SHOW default_transaction_read_only`; если `off` — значит сервер запущен не под
`tg_archive_ro`. Писать в лог предупреждение и продолжать в read-only режиме на уровне кода.
Пароль читать из env, при его отсутствии — из `~/.config/tg-archive/db.env`; дефолт
`user=postgres, password=''` из `db.py` убрать совсем.

### B7. Тесты
В проекте есть `pytest.ini` и `tests/`. Добавить юнит-тесты: `normalize_chat_type`, разбор
`TG_ARCHIVE_ACCOUNTS`, формирование блока свежести, порядок разрешения в `resolve_chat`
(на фейковом слое БД). Интеграционный тест против живой базы — отдельным маркером, не в дефолтном прогоне.

---

## 4. Фаза C — зависимости и smoke-тест

**Отдельное окружение, не рабочий `venv` приложения.** В `venv/` Sammaryhelper уже стоят `anyio 4.8`,
`httpx`, `pydantic` под клиент OpenAI; пакет `mcp` тянет собственные версии тех же зависимостей, и pip
молча обновит их — приложение сломается, а `pip uninstall mcp` прежние версии не вернёт. Поэтому:

```
cd /home/voyager/dev/github/Sammaryhelper
python3 -m venv .venv-archive-mcp
.venv-archive-mcp/bin/pip install "mcp>=1.9,<2" "asyncpg>=0.29"
.venv-archive-mcp/bin/pip freeze > mcp_archive_server/requirements.lock.txt
```

Добавить `.venv-archive-mcp/` в `.gitignore`. Откат этой фазы — `rm -rf .venv-archive-mcp`,
рабочий `venv/` при этом не затронут вообще. Путь к интерпретатору в конфигах MCP-клиентов (§5)
указывать на `.venv-archive-mcp/bin/python`.
Smoke-тест без MCP-клиента: подать на stdin сервера `initialize`, затем `tools/list`, убедиться, что
в ответе есть все инструменты и что `resolve_chat` отвечает на реальном запросе (например,
`resolve_chat("стоицизм")` должен вернуть `-1001372152834` с архивным названием
«🔥StoicStrategy: стоицизм в XXI в»). Результат прогона приложить в отчёт.

---

## 5. Фаза D — регистрация MCP-сервера

Написать `scripts/install-archive-mcp.py` (или `.mjs`) по образцу `/home/voyager/dev/lazgram/scripts/install-mcp.mjs`:
идемпотентно правит только свою запись, остальное в конфиге сохраняет, кладёт рядом `.bak-<timestamp>`,
поддерживает `--dry-run` и `--targets`, выставляет `chmod 600`. **Обязателен режим `--uninstall`:**
удаляет из конфига только ключ `tg-archive`, не трогая `lazgram` и прочее, и так же делает `.bak`.
Откат через `.bak` — запасной путь, штатный — `--uninstall`.

Ключ сервера: **`tg-archive`**. Цели (все четыре, как решил Игорь):
- `~/.config/Claude/claude_desktop_config.json` (Claude Desktop / Cowork),
- `~/.claude.json` (claude-code),
- `~/.config/{Code,Code - OSS,VSCodium,Cursor}/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json` (Roo),
- `~/.cursor/mcp.json`.

Запись:
```json
{"command": "/home/voyager/dev/github/Sammaryhelper/.venv-archive-mcp/bin/python",
 "args": ["-m", "mcp_archive_server.server"],
 "env": {"PYTHONPATH": "/home/voyager/dev/github/Sammaryhelper",
         "TG_ARCHIVE_DB_HOST": "localhost", "TG_ARCHIVE_DB_PORT": "5432",
         "TG_ARCHIVE_DB_NAME": "telegram_summarizer", "TG_ARCHIVE_DB_USER": "tg_archive_ro",
         "TG_ARCHIVE_ACCOUNTS": "prod:79253010707",
         "PGPASSFILE": "/home/voyager/.pgpass"}}
```
**Пароль в конфиги клиентов не писать** — брать из `~/.pgpass` через `PGPASSFILE` (asyncpg его поддерживает).
Конфиги MCP-клиентов читаются разными приложениями, пароль в четырёх местах — лишний риск.

После установки Игорю нужно перезапустить Claude Desktop; в сессиях Cowork инструменты появятся
как `mcp__remote-devices__tg-archive__*` рядом с `mcp__remote-devices__lazgram__*`.

---

## 6. Фаза E — доступ к Postgres: пароли и scram **(СТОП — выполнять только после «да» Игоря)**

Цель: убрать `trust` на loopback, не уронив при этом `infosoft`, `maymunai` и Sammaryhelper.
Главная опасность — роли без паролей и приложения, о которых мы не знаем.

### E1. Инвентаризация (до единой правки)
- `grep -rIl --exclude-dir={node_modules,.git,venv} -E "(password|PGPASSWORD|postgres(ql)?://|dbname=)" ~/dev ~/app ~/.config 2>/dev/null`
  — собрать список приложений и их конфигов, сопоставить роль → приложение → файл.
- `sudo -u postgres psql -c "select datname,usename,client_addr,application_name,state from pg_stat_activity where backend_type='client backend'"`.
- `systemctl --user list-units | grep -Ei 'infosoft|maymun|neuro|lazgram'` и то же без `--user`.
- Особое внимание: кто такой `infosoft` (6 idle-коннектов по `::1`, база 2.2 ГБ) и `maymun`.
  Пока их приложения не найдены — их пароли **не менять**.
- Результат — таблица в отчёте. Без неё дальше не идти.

### E2. Бэкапы
```
mkdir -p ~/backup/pg-$(date +%F)
sudo cp /var/lib/postgres/data/pg_hba.conf ~/backup/pg-$(date +%F)/
sudo -u postgres pg_dumpall --globals-only > ~/backup/pg-$(date +%F)/globals.sql
sudo -u postgres pg_dump telegram_summarizer -Fc -f ~/backup/pg-$(date +%F)/telegram_summarizer.dump
```

### E3. Пароли ролям, у которых их нет
`openssl rand -base64 24` для `postgres`, `voyager`, `tg_archive_ro`, `tg_map_rw`.
`ALTER ROLE ... PASSWORD '...'` (кодировка scram обеспечивается настройкой `password_encryption`).
Всё — в `~/.pgpass` (`chmod 600`) и `~/.config/tg-archive/db.env`. В git не попадает ничего.

`telegram_user`, `infosoft`, `maymun` — пароли уже заданы (scram). Их не менять: хеш необратим,
а новый пароль надо будет прописать в приложения, которых мы можем не знать.
`replicator` не используется (слотов и standby нет) — предложить Игорю `ALTER ROLE replicator NOLOGIN`,
но не делать без ответа.

Откат этого шага: `ALTER ROLE <роль> PASSWORD NULL;` возвращает роль в исходное беспарольное состояние
(именно так сейчас живут `postgres` и `voyager`). То есть шаг обратим, но откатывать его имеет смысл
только вместе с откатом `pg_hba` — без `trust` беспарольная роль не войдёт вообще.

### E4. Sammaryhelper переводится на `telegram_user`
Сейчас приложение ходит под `postgres` с фиктивным паролем. После E5 это сломается.
- Дать `telegram_user` права на объекты, принадлежащие `postgres`:
  `GRANT ALL ON public.dialogs, public.ai_requests, public.ai_responses TO telegram_user;`
  плюс `GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO telegram_user;` (миграция `003_*.sql`).
- **Сначала** `cp -a Sammaryhelper/configs ~/backup/pg-$(date +%F)/configs-before/` — файлы не в git,
  восстановить их больше неоткуда.
- В `Sammaryhelper/configs/db_config.json`, `config_0707.py`, `config_0707.json` привести подключение
  к одному виду: `user=telegram_user`, пароль из существующего `config_0707.json`
  (он там уже есть и рабочий). Строку `"password": "postgres"` вычистить отовсюду.
- Проверить, что GUI приложения запускается и читает диалоги. Это единственная проверка,
  которую, возможно, придётся попросить сделать Игоря.

### E5. Включение scram **по одной роли за раз**
В `pg_hba.conf` **выше** общих `trust`-строк добавлять пары строк на роль и делать
`SELECT pg_reload_conf()` (перезагрузка конфигурации, **не** `restart` — рвать 6 живых соединений
`infosoft` незачем; уже открытые сессии продолжают работать в любом случае):

```
host    all     tg_archive_ro   127.0.0.1/32    scram-sha-256
host    all     tg_archive_ro   ::1/128         scram-sha-256
```
Порядок ролей: сначала `tg_archive_ro` и `tg_map_rw` (наши, ничего не сломают), затем `telegram_user`
(проверить Sammaryhelper), затем `maymun`, затем `infosoft` — после каждой роли убедиться, что её
приложение живо. Если приложение падает — снять две строки, `pg_reload_conf()`, разбираться с конфигом
приложения, и только потом возвращать.

**Перед каждым reload** проверять синтаксис: `SELECT line_number, type, error FROM pg_hba_file_rules WHERE error IS NOT NULL;`
— в PG 18 это показывает ошибки разбора **до** применения. Пустой результат — можно перезагружать.

Когда все роли покрыты — заменить общие строки:
```
local   all     all             peer
host    all     all             127.0.0.1/32    scram-sha-256
host    all     all             ::1/128         scram-sha-256
```
`local ... peer` оставляет рабочий аварийный вход: `sudo -u postgres psql` без пароля.
Строки для `replication` привести к тому же виду (или удалить, раз репликации нет).

### E6. Верификация закрытия дыры
- `psql "host=127.0.0.1 user=postgres dbname=postgres"` без пароля → **отказ**. Это и была цель.
- `psql "host=localhost user=tg_archive_ro dbname=telegram_summarizer"` с `~/.pgpass` → работает.
- `sudo -u postgres psql -c "select 1"` → работает (аварийный вход цел).
- Сообщить Игорю: после этого шага агенты в Cowork-VM теряют суперюзерский доступ к кластеру,
  MCP-сервер `tg-archive` продолжает работать, потому что ходит с паролем под read-only ролью.

### E7. Откат фазы E
Быстрый, полный: `sudo cp ~/backup/pg-<дата>/pg_hba.conf /var/lib/postgres/data/ && sudo -u postgres psql -c "select pg_reload_conf()"`.
Занимает секунды, возвращает ровно исходное состояние. Пошаговый откат по одной роли и откат
остальных шагов фазы — §7.6.

---

## 7. Откат

Правило: **каждая фаза обратима независимо**, откат идёт строго в обратном порядке E → D → C → B → A,
и проверяется до того, как понадобится. Необратимых шагов в этой работе нет — при условии, что §7.1 выполнен.

### 7.1. Точка отката (до первой правки, одной пачкой)

```
RB=~/backup/tg-archive-$(date +%F_%H%M); mkdir -p $RB
cd /home/voyager/dev/github/Sammaryhelper
git rev-parse HEAD > $RB/git-head.txt
git tag tg-archive-before                              # метка исходного состояния
git status --porcelain > $RB/git-status-before.txt
venv/bin/pip freeze > $RB/venv-freeze-before.txt       # на случай, если venv всё же будет затронут
sudo cp /var/lib/postgres/data/pg_hba.conf $RB/
sudo -u postgres pg_dumpall --globals-only > $RB/globals.sql          # роли и их права
sudo -u postgres pg_dump telegram_summarizer -Fc -f $RB/telegram_summarizer.dump
cp -a Sammaryhelper/configs $RB/configs-before/        # не в git, восстановить больше неоткуда
for f in ~/.config/Claude/claude_desktop_config.json ~/.claude.json ~/.cursor/mcp.json; do
  [ -f "$f" ] && cp -a "$f" $RB/$(echo "$f" | tr / _); done
```

В `$RB/ROLLBACK.md` записать: путь `$RB`, sha исходного коммита, какие фазы применены и когда.
Этот файл — то, что читает человек в три часа ночи, а не история чата.

### 7.2. Откат фазы A (роль и схема)

Парные файлы `migrations/down/002_tg_map.sql` и `migrations/down/001_tg_archive_ro.sql`, применять
в этом порядке:

```sql
-- down/002: маппинг
DROP SCHEMA IF EXISTS tg_map CASCADE;     -- public не затрагивается
DROP OWNED BY tg_map_rw;                  -- выполнить в КАЖДОЙ базе, где роль получала права
DROP ROLE IF EXISTS tg_map_rw;

-- down/001: read-only роль
DROP OWNED BY tg_archive_ro;              -- снимает гранты; без этого DROP ROLE упадёт
DROP ROLE IF EXISTS tg_archive_ro;
```
Затем убрать строки этих ролей из `~/.pgpass` и `~/.config/tg-archive/db.env`.

Проверка, что архив цел (обязательна после отката):
```
sudo -u postgres psql telegram_summarizer -c "select (select count(*) from dialogs) dialogs,
  (select count(*) from messages) messages, (select count(*) from topics) topics;"
```
Должно быть ровно `2010 | 49607 | 221`. Любое расхождение — останавливаться и звать Игоря,
восстановление из `$RB/telegram_summarizer.dump` делать только с его ведома.

**Обратимость проверить заранее, на копии.** До применения миграций к рабочей базе:
```
sudo -u postgres createdb tg_rbtest
sudo -u postgres pg_restore -d tg_rbtest $RB/telegram_summarizer.dump
# прогнать на tg_rbtest: up 001,002 -> down 002,001 -> up 001,002 -> down
sudo -u postgres dropdb tg_rbtest
```
Цикл up→down→up без ошибок — единственное настоящее доказательство, что откат написан рабочим.

### 7.3. Откат фазы B (код)

Всё в git, `master` не тронут. Каждая фаза — отдельный коммит, поэтому откат точечный:
`git revert <sha>` для одной правки, `git reset --hard tg-archive-before` для возврата ветки в исходное.
Полный отказ от работы: `git switch master && git branch -D claude/telegram-archive-mcp-21goj9`
(в `origin` ничего не уходило — §7 «не пушить»).

### 7.4. Откат фазы C (зависимости)

`rm -rf .venv-archive-mcp`. Всё. Рабочий `venv/` не затрагивался — сверить с
`$RB/venv-freeze-before.txt`, вывод `diff` должен быть пустым.

### 7.5. Откат фазы D (регистрация MCP)

`scripts/install-archive-mcp.py --uninstall` по всем целям — удаляет только ключ `tg-archive`.
Запасной путь: восстановить `.bak-<timestamp>` рядом с каждым конфигом.
Проверка после отката: каждый файл — валидный JSON (`python3 -m json.tool <файл> >/dev/null`),
запись `lazgram` на месте, Claude Desktop после перезапуска поднимается без ошибок MCP.

### 7.6. Откат фазы E (доступ к Postgres) — поэтапный

Откатывать в порядке, обратном применению:

1. **Одна роль.** Если приложение упало сразу после включения scram для роли — удалить её две строки
   из `pg_hba.conf`, `sudo -u postgres psql -c "select pg_reload_conf()"`. Остальные роли не трогать:
   в этом и смысл построчного включения — радиус поражения равен одной роли.
2. **Общие строки.** Если сломалось после замены общих `trust` на `scram`/`peer` — вернуть
   `pg_hba.conf` из `$RB/`, `pg_reload_conf()`. 10 секунд, состояние ровно исходное.
3. **Пароли.** `ALTER ROLE postgres PASSWORD NULL;` и `ALTER ROLE voyager PASSWORD NULL;` возвращают
   исходное беспарольное состояние. Делать только вместе с п. 2 — иначе роли не войдут вообще.
4. **Конфиги Sammaryhelper.** `cp -a $RB/configs-before/* Sammaryhelper/configs/`.
5. **Гранты `telegram_user`.** `migrations/down/003_*.sql`:
   `REVOKE ALL ON public.dialogs, public.ai_requests, public.ai_responses FROM telegram_user;`
   (учесть: `messages` и `topics` принадлежат `telegram_user` изначально, их не трогать).
6. **Аварийный вход, если закрылись сами.** `local all all peer` оставляет `sudo -u postgres psql`.
   Если и он не работает — правим `pg_hba.conf` от root и `sudo systemctl reload postgresql`;
   `reload` достаточно, `restart` не нужен даже здесь.

Отдельно: `pg_reload_conf()` не рвёт уже открытые соединения. Шесть idle-сессий `infosoft` переживут
и применение, и откат — ломается только установка **новых** соединений, что и делает откат дешёвым.

### 7.7. Ворота между фазами

`scripts/check-archive-mcp.sh` — один скрипт, печатающий текущее состояние: существуют ли роли,
какие у них гранты, отвечает ли `tg_map.v_chat`, отклоняется ли запись, поднимается ли MCP-сервер,
какие записи в конфигах клиентов, действующие строки `pg_hba_file_rules`. Прогонять после каждой фазы
и прикладывать вывод к отчёту. Красный результат — откат текущей фазы, а не переход к следующей.

---

## 8. Чего в этой работе не делать

- Не пушить ветку в `origin` и не открывать PR без просьбы.
- Не трогать `master` и не мержить.
- Не создавать индексы и расширения (`pg_trgm`, FTS) на `public.*`. Сначала замеры: время
  `resolve_chat` по 2010 чатам и `search_messages` (ILIKE) по 49 607 сообщениям. Цифры — в отчёт,
  решение об индексах Игорь примет по ним.
- Не выдавать никаких прав на `ai_requests` / `ai_responses`.
- Не менять пароли ролей `infosoft`, `maymun`, `telegram_user`.
- Не делать `systemctl restart postgresql` — только `reload`.
- Не писать пароли в репозиторий и в конфиги MCP-клиентов.
- Не ставить `mcp` в рабочий `venv/` Sammaryhelper (конфликт версий `anyio`/`httpx`/`pydantic`
  с клиентом OpenAI; это и необратимо в один шаг, и ломает работающее приложение).
- Не начинать фазу, пока не выполнен §7.1 и пока откат предыдущей фазы не проверен.
- Не реализовывать `tg_map.message_cache` и sync из Lazgram — это следующая фаза, схема под неё
  уже заложена.

---

## 9. Приёмка

Отчёт в конце работы должен содержать:

1. Что закоммичено, какими коммитами, в какой ветке.
2. Вывод трёх проверок из §A3 (чтение работает, запись отклонена, `ai_*` недоступны).
3. Вывод smoke-теста `resolve_chat("стоицизм")` с реальным `chat_id`.
4. Список файлов MCP-конфигов, которые изменены, и путь к их `.bak`.
5. Таблицу инвентаризации из E1 (роль → приложение → конфиг → шлёт ли пароль).
6. Результат E6 (три проверки доступа).
7. Замеры времени `resolve_chat` и `search_messages` — как основание для решения об индексах.
8. Подтверждение, что цикл up→down→up на `tg_rbtest` прошёл без ошибок (§7.2), и что после него
   контрольные счётчики архива равны `2010 | 49607 | 221`.
9. Путь к каталогу точки отката `$RB` и содержимое `$RB/ROLLBACK.md`.
10. Что осталось незакрытым и где именно потребуется решение Игоря.

## 10. Следующая фаза (не сейчас, для контекста)

Sync-джоб под ролью `tg_map_rw`: `lazgram_chats(limit 200)` → `tg_map.chat` (`title_live`, `is_live`,
`last_seen`) и `tg_map.chat_alias`, с записью в `tg_map.sync_run`; отчёт «сколько архивных чатов ещё
существуют, сколько переименованы, сколько исчезли». После него — `tg_map.message_cache`,
наполняемый из `lazgram_history` по обращению (read-through), и полнотекстовый поиск по объединению
«архив 2018–2025 + свежий кеш». Тогда слой перестаёт быть справочником и становится памятью переписки.
