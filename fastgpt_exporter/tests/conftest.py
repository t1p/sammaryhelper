"""Фикстуры для e2e-тестов: временный локальный Postgres + HTTP-стаб FastGPT.

Тесты, зависящие от них, скипаются (не падают), если в окружении нет
asyncpg/initdb/psql — чтобы не ломать общий прогон pytest там, где их нет.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import pytest

pg_bin_candidates = [
    "/usr/lib/postgresql/16/bin",
    "/usr/lib/postgresql/15/bin",
    "/usr/lib/postgresql/14/bin",
    "/usr/local/pgsql/bin",
]


def _find_pg_bin_dir() -> str | None:
    for candidate in pg_bin_candidates:
        if os.path.exists(os.path.join(candidate, "initdb")):
            return candidate
    for name in ("initdb",):
        found = shutil.which(name)
        if found:
            return os.path.dirname(found)
    return None


@pytest.fixture(scope="session")
def pg_bin_dir():
    bin_dir = _find_pg_bin_dir()
    if not bin_dir:
        pytest.skip("PostgreSQL (initdb) не найден в окружении")
    return bin_dir


@pytest.fixture(scope="session")
def pg_run_user():
    """Возвращает имя ОС-пользователя, от которого можно запускать postgres.

    initdb/postgres отказываются работать от root. Если текущий процесс не
    root — используем его напрямую. Если root — пробуем завести временного
    пользователя; если это невозможно (нет прав/useradd), тест скипается.
    """
    if os.geteuid() != 0:
        yield None  # None => команды выполняются от текущего пользователя напрямую
        return

    username = f"pgtest_{uuid.uuid4().hex[:8]}"
    created = subprocess.run(["useradd", "-m", username], capture_output=True)
    if created.returncode != 0:
        pytest.skip(f"Не удалось создать временного пользователя для Postgres: {created.stderr.decode()}")
    try:
        yield username
    finally:
        subprocess.run(["userdel", "-r", username], capture_output=True)


def _run_as(user: str | None, cmd: list[str], **kwargs):
    if user is None:
        return subprocess.run(cmd, **kwargs)
    return subprocess.run(["su", user, "-c", " ".join(cmd)], **kwargs)


@pytest.fixture(scope="session")
def temp_postgres(pg_bin_dir, pg_run_user):
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        pytest.skip("asyncpg не установлен")

    import shutil as _shutil
    import tempfile

    # Не используем tmp_path_factory: pytest создаёт свой базовый каталог с
    # правами 0700 для текущего пользователя, и su-пользователь не сможет в
    # него зайти, даже если сам data_dir перечислен. Заводим независимый
    # каталог с открытым обходом до самого data_dir.
    base_dir = tempfile.mkdtemp(prefix="fastgpt_exporter_pgtest_")
    os.chmod(base_dir, 0o711)
    data_dir_path = os.path.join(base_dir, "pgdata")
    os.makedirs(data_dir_path)
    data_dir = data_dir_path
    if pg_run_user:
        subprocess.run(["chown", "-R", f"{pg_run_user}:{pg_run_user}", base_dir], check=True)
        subprocess.run(["chmod", "700", base_dir], check=True)
        subprocess.run(["chmod", "700", str(data_dir)], check=True)

    initdb = os.path.join(pg_bin_dir, "initdb")
    result = _run_as(pg_run_user, [initdb, "-D", str(data_dir), "-U", "postgres", "--auth=trust"], capture_output=True)
    if result.returncode != 0:
        pytest.skip(f"initdb завершился с ошибкой: {result.stderr}")

    port = 5433
    pg_ctl = os.path.join(pg_bin_dir, "pg_ctl")
    log_file = str(data_dir) + ".log"
    pg_opts = f"-k /tmp -h 127.0.0.1 -p {port}"
    if pg_run_user is None:
        start = subprocess.run(
            [pg_ctl, "-D", str(data_dir), "-l", log_file, "-o", pg_opts, "start"],
            capture_output=True,
        )
    else:
        start = subprocess.run(
            ["su", pg_run_user, "-c", f"{pg_ctl} -D {data_dir} -l {log_file} -o '{pg_opts}' start"],
            capture_output=True,
        )
    if start.returncode != 0:
        pytest.skip(f"Не удалось запустить временный Postgres: {start.stderr}")

    time.sleep(1.5)

    psql = os.path.join(pg_bin_dir, "psql")
    seed_sql = os.path.join(os.path.dirname(__file__), "seed.sql")
    _run_as(pg_run_user, [psql, "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-f", seed_sql], check=True)

    try:
        yield {"host": "127.0.0.1", "port": port, "database": "telegram_summarizer", "user": "postgres", "password": ""}
    finally:
        _run_as(pg_run_user, [pg_ctl, "-D", str(data_dir), "stop"], capture_output=True)
        _shutil.rmtree(base_dir, ignore_errors=True)


@pytest.fixture()
def stub_fastgpt(monkeypatch=None):
    from .stub_fastgpt_server import StubFastGPTServer

    server = StubFastGPTServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()
