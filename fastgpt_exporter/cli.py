"""CLI: python -m fastgpt_exporter.cli [флаги]

Запускать из корня репозитория (как и mcp_archive_server), чтобы пакет
mcp_archive_server был доступен для импорта как соседний top-level пакет.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from mcp_archive_server.db import ArchiveConfig

from .config import FastGPTConfig
from .exporter import render_summary, run_export


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Экспорт справочника Telegram-чатов в FastGPT")
    parser.add_argument("--account-id", default=None, help="Ограничить одним Telegram-аккаунтом")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Не обращаться к FastGPT")
    parser.add_argument("--state-file", default=None, help="Путь к файлу состояния")
    parser.add_argument("--batch-size", type=int, default=None, help="Размер пачки pushData (<=200)")
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument("--dataset-intro", default=None)
    parser.add_argument("--collection-name", default=None)
    parser.add_argument("--base-url", default=None, help="Адрес инстанса FastGPT")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cli_overrides = {
        "dry_run": args.dry_run,
        "state_file": args.state_file,
        "batch_size": args.batch_size,
        "dataset_name": args.dataset_name,
        "dataset_intro": args.dataset_intro,
        "collection_name": args.collection_name,
        "base_url": args.base_url,
        "api_key": args.api_key,
    }
    cli_overrides = {k: v for k, v in cli_overrides.items() if v is not None}

    try:
        fastgpt_config = FastGPTConfig.load(cli_overrides=cli_overrides)
        db_config = ArchiveConfig.load()
        summary = asyncio.run(run_export(db_config, fastgpt_config, account_id=args.account_id))
    except ValueError as e:
        print(f"Ошибка конфигурации: {e}", file=sys.stderr)
        return 1

    print(render_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
