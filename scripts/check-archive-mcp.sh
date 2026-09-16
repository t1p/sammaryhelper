#!/usr/bin/env bash
# Воротный скрипт между фазами tg-archive-mcp (см. TASK-tg-archive-mcp.md §7.7).
# Красный результат = откат текущей фазы, а не переход к следующей.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

section() { echo; echo "=== $1 ==="; }
ok()   { echo "  OK: $1"; }
bad()  { echo "  FAIL: $1"; FAIL=1; }

section "Роли"
for role in tg_archive_ro tg_map_rw; do
  exists=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$role'" 2>/dev/null)
  if [ "$exists" = "1" ]; then ok "роль $role существует"; else bad "роль $role отсутствует"; fi
done

section "Гранты read-only роли"
ro_flag=$(sudo -u postgres psql -tAc "SELECT rolconfig::text FROM pg_db_role_setting s JOIN pg_roles r ON r.oid=s.setrole WHERE r.rolname='tg_archive_ro'" 2>/dev/null)
if echo "$ro_flag" | grep -q "default_transaction_read_only=on"; then
  ok "tg_archive_ro: default_transaction_read_only=on"
else
  bad "tg_archive_ro: default_transaction_read_only не найден/не on ($ro_flag)"
fi

section "tg_map.v_chat отвечает"
if PGPASSFILE=~/.pgpass psql "host=localhost user=tg_archive_ro dbname=telegram_summarizer" -tAc "SELECT count(*) FROM tg_map.v_chat" >/tmp/check-vchat.out 2>&1; then
  ok "tg_map.v_chat: $(cat /tmp/check-vchat.out) строк"
else
  bad "tg_map.v_chat недоступна: $(cat /tmp/check-vchat.out)"
fi

section "Запись отклоняется"
if PGPASSFILE=~/.pgpass psql "host=localhost user=tg_archive_ro dbname=telegram_summarizer" -c "INSERT INTO tg_map.sync_run(source) VALUES ('check')" >/tmp/check-write.out 2>&1; then
  bad "запись прошла (не должна была!)"
else
  ok "запись отклонена"
fi

section "ai_requests/ai_responses недоступны"
if PGPASSFILE=~/.pgpass psql "host=localhost user=tg_archive_ro dbname=telegram_summarizer" -c "SELECT * FROM ai_requests LIMIT 1" >/tmp/check-ai.out 2>&1; then
  bad "ai_requests доступен (не должен быть!)"
else
  ok "ai_requests недоступен"
fi

section "Счётчики архива"
counts=$(sudo -u postgres psql telegram_summarizer -tAc "SELECT (SELECT count(*) FROM dialogs)||'|'||(SELECT count(*) FROM messages)||'|'||(SELECT count(*) FROM topics)" 2>/dev/null)
if [ "$counts" = "2010|49607|221" ]; then
  ok "dialogs|messages|topics = $counts"
else
  bad "счётчики разошлись: $counts (ожидалось 2010|49607|221)"
fi

section "MCP-сервер поднимается (.venv-archive-mcp)"
VENV="$REPO_ROOT/.venv-archive-mcp/bin/python"
if [ -x "$VENV" ]; then
  if TG_ARCHIVE_DB_HOST=localhost TG_ARCHIVE_DB_PORT=5432 TG_ARCHIVE_DB_NAME=telegram_summarizer \
     TG_ARCHIVE_DB_USER=tg_archive_ro TG_ARCHIVE_ACCOUNTS="prod:79253010707" PGPASSFILE=~/.pgpass \
     PYTHONPATH="$REPO_ROOT" timeout 10 "$VENV" -c "
import asyncio
from mcp_archive_server.db import ArchiveDB
async def main():
    db = ArchiveDB(); await db.connect()
    r = await db.resolve_chat('стоицизм', '79253010707')
    assert r, 'resolve_chat вернул пустой список'
    await db.close()
asyncio.run(main())
" >/tmp/check-mcp.out 2>&1; then
    ok "resolve_chat('стоицизм') отработал"
  else
    bad "MCP/resolve_chat упал: $(tail -5 /tmp/check-mcp.out)"
  fi
else
  bad ".venv-archive-mcp не найден (фаза C не выполнена)"
fi

section "Записи в конфигах MCP-клиентов"
for f in ~/.config/Claude/claude_desktop_config.json ~/.claude.json ~/.cursor/mcp.json; do
  [ -f "$f" ] || { echo "  -- $f: нет файла"; continue; }
  if python3 -m json.tool "$f" >/dev/null 2>&1; then
    has_ta=$(python3 -c "import json; print('tg-archive' in json.load(open('$f')).get('mcpServers', {}))" 2>/dev/null)
    has_lz=$(python3 -c "import json; print('lazgram' in json.load(open('$f')).get('mcpServers', {}))" 2>/dev/null)
    echo "  $f: valid JSON, tg-archive=$has_ta, lazgram=$has_lz"
  else
    bad "$f: невалидный JSON"
  fi
done

section "pg_hba_file_rules"
sudo -u postgres psql -c "SELECT line_number, type, database, user_name, auth_method, error FROM pg_hba_file_rules ORDER BY line_number" 2>&1

echo
if [ "$FAIL" = "0" ]; then
  echo "=== ИТОГ: ЗЕЛЁНЫЙ ==="
else
  echo "=== ИТОГ: КРАСНЫЙ — откат текущей фазы, не переход к следующей ==="
fi
exit "$FAIL"
