"""CLI: python -m lazgram_sync.cli --config chats.json [флаги]

Запускать там, где виден LazGram (Node, лежит рядом с lazgram-node) и
доступна архивная Postgres (TG_ARCHIVE_DB_* / TG_ARCHIVE_DB_CONFIG_FILE).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import LazgramConfig, SyncJobConfig
from .sync import run_sync


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Синк архива Sammaryhelper с LazGram")
    parser.add_argument("--config", required=True, help="Путь к JSON-конфигу чатов (см. chats.example.json)")
    parser.add_argument("--node-bin", default=None, help="Путь до node (по умолчанию 'node')")
    parser.add_argument("--mcp-script", default=None, help="Путь до lazgram-node/src/interface/mcp/lazgram-mcp.mjs")
    parser.add_argument("--account", default=None, help="Id аккаунта LazGram (напр. 'prod')")
    parser.add_argument("--dry-run", action="store_true", help="Не писать в БД, только показать, что было бы синхронизировано")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def render_summary(summary) -> str:
    lines = [f"Аккаунт архива: {summary.account_id}" + (" (dry-run)" if summary.dry_run else "")]
    if summary.account_id_warning:
        lines.append(f"ВНИМАНИЕ: {summary.account_id_warning}")
    for r in summary.results:
        status = f"ошибка: {r.error}" if r.error else f"{r.messages_fetched} сообщений, {r.pages_fetched} страниц"
        extra = " [чат не найден в lazgram_chats — карточка неполная]" if not r.dialog_found_in_chats_list else ""
        cap = " [достигнут max_pages, история могла обрезаться раньше `since`]" if r.hit_max_pages else ""
        lines.append(f"  {r.label} (chat_id={r.chat_id}): {status}{extra}{cap}")
    lines.append(f"Итого сообщений: {summary.total_messages}")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        job = SyncJobConfig.load_file(args.config)
        lazgram_config = LazgramConfig.load(
            cli_overrides={"node_bin": args.node_bin, "mcp_script": args.mcp_script, "account": args.account}
        )
        summary = asyncio.run(run_sync(job, lazgram_config, dry_run=args.dry_run))
    except (ValueError, FileNotFoundError) as e:
        print(f"Ошибка конфигурации: {e}", file=sys.stderr)
        return 1

    print(render_summary(summary))
    return 0 if not any(r.error for r in summary.results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
