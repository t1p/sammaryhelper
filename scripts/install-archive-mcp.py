#!/usr/bin/env python3
"""Регистрирует MCP-сервер tg-archive в клиентах на этой машине.

  scripts/install-archive-mcp.py
  scripts/install-archive-mcp.py --targets claude-desktop,claude-code --dry-run
  scripts/install-archive-mcp.py --uninstall

Идемпотентно: правит только ключ "tg-archive" в mcpServers, всё остальное
в файле сохраняется как есть. Перед изменением существующий файл
копируется в <файл>.bak-<timestamp>. --uninstall удаляет только ключ
"tg-archive", не трогая lazgram и прочее (образец: lazgram/scripts/install-mcp.mjs).

Пароль read-only роли в конфиги НЕ пишется — берётся из ~/.pgpass через
PGPASSFILE (asyncpg это поддерживает).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

SERVER_KEY = "tg-archive"

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGETS: dict[str, list[Path]] = {
    "claude-desktop": [Path.home() / ".config" / "Claude" / "claude_desktop_config.json"],
    "claude-code": [Path.home() / ".claude.json"],
    "roo": [
        Path.home() / ".config" / app / "User" / "globalStorage"
        / "rooveterinaryinc.roo-cline" / "settings" / "mcp_settings.json"
        for app in ("Code", "Code - OSS", "VSCodium", "Cursor")
    ],
    "cursor": [Path.home() / ".cursor" / "mcp.json"],
}


def build_server_entry(*, repo_root: Path, python_bin: Path, accounts: str) -> dict[str, Any]:
    return {
        "command": str(python_bin),
        "args": ["-m", "mcp_archive_server.server"],
        "env": {
            "PYTHONPATH": str(repo_root),
            "TG_ARCHIVE_DB_HOST": "localhost",
            "TG_ARCHIVE_DB_PORT": "5432",
            "TG_ARCHIVE_DB_NAME": "telegram_summarizer",
            "TG_ARCHIVE_DB_USER": "tg_archive_ro",
            "TG_ARCHIVE_ACCOUNTS": accounts,
            "PGPASSFILE": str(Path.home() / ".pgpass"),
        },
    }


def merge_config(existing: Optional[dict[str, Any]], entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Заменяет только запись SERVER_KEY; всё остальное в файле сохраняется."""
    config = dict(existing) if isinstance(existing, dict) else {}
    servers = dict(config.get("mcpServers")) if isinstance(config.get("mcpServers"), dict) else {}
    changed = servers.get(SERVER_KEY) != entry
    servers[SERVER_KEY] = entry
    config["mcpServers"] = servers
    return config, changed


def remove_from_config(existing: Optional[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    config = dict(existing) if isinstance(existing, dict) else {}
    servers = dict(config.get("mcpServers")) if isinstance(config.get("mcpServers"), dict) else {}
    if SERVER_KEY not in servers:
        return config, False
    del servers[SERVER_KEY]
    config["mcpServers"] = servers
    return config, True


def first_existing(candidates: list[Path]) -> Optional[Path]:
    for path in candidates:
        if path.exists():
            return path
    return None


def backup(path: Path) -> Path:
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    backup_path = path.with_name(f"{path.name}.bak-{ts}")
    shutil.copy2(path, backup_path)
    return backup_path


def write_target(
    name: str,
    candidates: list[Path],
    entry: dict[str, Any],
    *,
    dry_run: bool,
    create: bool,
    uninstall: bool,
) -> None:
    path = first_existing(candidates) or (candidates[0] if create else None)
    if path is None:
        print(f"  {name}: конфиг не найден (искал в {len(candidates)} местах); используйте --create")
        return

    existing: Optional[dict[str, Any]] = None
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  {name}: {path} — невалидный JSON ({exc}); не трогаю")
            return

    if uninstall:
        config, changed = remove_from_config(existing)
    else:
        config, changed = merge_config(existing, entry)

    if not changed:
        print(f"  {name}: уже в нужном состоянии ({path})")
        return
    if dry_run:
        action = "удалил бы запись tg-archive из" if uninstall else "обновил бы"
        print(f"  {name}: {action} {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    if existing is not None:
        backup_path = backup(path)
        print(f"  {name}: бэкап -> {backup_path}")

    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    action = "удалена запись tg-archive из" if uninstall else "обновлён"
    print(f"  {name}: {action} {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", help="через запятую: " + ",".join(TARGETS))
    parser.add_argument("--accounts", default="prod:79253010707", help="TG_ARCHIVE_ACCOUNTS, по умолчанию prod:79253010707")
    parser.add_argument("--python-bin", default=str(REPO_ROOT / ".venv-archive-mcp" / "bin" / "python"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--create", action="store_true", help="создавать конфиг, если файла нет")
    parser.add_argument("--uninstall", action="store_true", help="удалить только запись tg-archive")
    args = parser.parse_args()

    names = args.targets.split(",") if args.targets else list(TARGETS)
    for name in names:
        if name not in TARGETS:
            print(f"неизвестная цель: {name!r}; доступны: {', '.join(TARGETS)}", file=sys.stderr)
            sys.exit(1)

    entry = build_server_entry(
        repo_root=REPO_ROOT,
        python_bin=Path(args.python_bin),
        accounts=args.accounts,
    )

    action = "удаление" if args.uninstall else "регистрация"
    print(f"tg-archive MCP: {action}, targets={names}")
    for name in names:
        write_target(
            name,
            TARGETS[name],
            entry,
            dry_run=args.dry_run,
            create=args.create,
            uninstall=args.uninstall,
        )
    print("Перезапустите клиент, чтобы изменения применились.")


if __name__ == "__main__":
    main()
