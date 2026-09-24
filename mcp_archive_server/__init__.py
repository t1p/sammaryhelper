"""MCP-сервер "справочник" по архивным данным Telegram (Sammaryhelper).

Отдаёт только на чтение данные, ранее закешированные приложением Sammaryhelper
в PostgreSQL (таблицы dialogs/messages/topics): список чатов, групп, каналов
и часть истории сообщений. Предназначен для того, чтобы ИИ-агент сначала
проверял этот архив (это дёшево и не требует обращения к живому Telegram),
и только при нехватке или устаревании данных шёл в реальный Telegram через
отдельный MCP-коннектор (например, тот, что работает поверх MTProto).
"""

# Ленивый импорт: `mcp_archive_server.db` (ArchiveConfig/ArchiveDB) должен
# быть импортируем сам по себе, без установленного SDK `mcp` — им пользуются
# и другие независимые инструменты (например, fastgpt_exporter), которым
# сам MCP-сервер не нужен.
__all__ = ["mcp"]


def __getattr__(name):
    if name == "mcp":
        from .server import mcp as _mcp

        return _mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
