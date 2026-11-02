"""Фикстуры: временный локальный Postgres (та же техника, что у
fastgpt_exporter/tests/conftest.py) + путь к стаб-серверу LazGram."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

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
    found = shutil.which("initdb")
    return os.path.dirname(found) if found else None


@pytest.fixture(scope="session")
def pg_bin_dir():
    bin_dir = _find_pg_bin_dir()
    if not bin_dir:
        pytest.skip("PostgreSQL (initdb) не найден в окружении")
    return bin_dir


@pytest.fixture(scope="session")
def pg_run_user():
    if os.geteuid() != 0:
        yield None
        return
    import uuid

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

    base_dir = tempfile.mkdtemp(prefix="lazgram_sync_pgtest_")
    os.chmod(base_dir, 0o711)
    data_dir = os.path.join(base_dir, "pgdata")
    os.makedirs(data_dir)
    if pg_run_user:
        subprocess.run(["chown", "-R", f"{pg_run_user}:{pg_run_user}", base_dir], check=True)
        subprocess.run(["chmod", "700", base_dir], check=True)
        subprocess.run(["chmod", "700", data_dir], check=True)

    initdb = os.path.join(pg_bin_dir, "initdb")
    result = _run_as(pg_run_user, [initdb, "-D", data_dir, "-U", "postgres", "--auth=trust"], capture_output=True)
    if result.returncode != 0:
        pytest.skip(f"initdb завершился с ошибкой: {result.stderr}")

    port = 5434
    pg_ctl = os.path.join(pg_bin_dir, "pg_ctl")
    log_file = data_dir + ".log"
    pg_opts = f"-k /tmp -h 127.0.0.1 -p {port}"
    if pg_run_user is None:
        start = subprocess.run([pg_ctl, "-D", data_dir, "-l", log_file, "-o", pg_opts, "start"], capture_output=True)
    else:
        start = subprocess.run(
            ["su", pg_run_user, "-c", f"{pg_ctl} -D {data_dir} -l {log_file} -o '{pg_opts}' start"],
            capture_output=True,
        )
    if start.returncode != 0:
        pytest.skip(f"Не удалось запустить временный Postgres: {start.stderr}")

    time.sleep(1.5)

    psql = os.path.join(pg_bin_dir, "psql")
    seed_sql = os.path.join(os.path.dirname(__file__), "seed_schema.sql")
    _run_as(pg_run_user, [psql, "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-f", seed_sql], check=True)

    try:
        yield {"host": "127.0.0.1", "port": port, "database": "telegram_summarizer", "user": "postgres", "password": ""}
    finally:
        _run_as(pg_run_user, [pg_ctl, "-D", data_dir, "stop"], capture_output=True)
        shutil.rmtree(base_dir, ignore_errors=True)


@pytest.fixture()
def lazgram_fixture_file(tmp_path):
    def _write(fixture: dict):
        path = tmp_path / "lazgram_fixture.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        return str(path)

    return _write


@pytest.fixture()
def stub_mcp_script():
    return os.path.join(os.path.dirname(__file__), "stub_lazgram_server.py")
