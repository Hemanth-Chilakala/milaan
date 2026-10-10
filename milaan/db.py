import re
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from pathlib import Path

import pyexasol
from packaging.version import InvalidVersion, Version

from milaan.config import settings

_scope = ContextVar("reconciliation_scope", default="month")


def current_scope():
    return _scope.get()


@contextmanager
def scope(name):
    if name not in {"month", "day"}:
        raise ValueError("Choose month or day")
    token = _scope.set(name)
    try:
        yield
    finally:
        _scope.reset(token)


def scoped_sql(sql, name):
    if name == "day":
        for schema in ("CORE", "RES", "AUDIT"):
            sql = sql.replace(f"MILAAN_{schema}.", f"MILAAN_DAY_{schema}.")
    return sql


class ScopedConnection:
    def __init__(self, connection, name):
        self.connection, self.name = connection, name

    def execute(self, sql, *args, **kwargs):
        return self.connection.execute(scoped_sql(sql, self.name), *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.connection, name)


class PersonalConnection(pyexasol.ExaConnection):
    """Handle Nano's non-PEP-440 release suffix for pyexasol's transport feature check."""

    @property
    def exasol_db_version(self):
        try:
            return super().exasol_db_version
        except InvalidVersion:
            raw = self.login_info.get("releaseVersion", "")
            match = re.fullmatch(r"(\d+\.\d+\.\d+)-nano[.]\d+", raw)
            if not match:
                raise
            return Version(match.group(1))


@contextmanager
def connect():
    config = settings()
    connection = PersonalConnection(
        dsn=config.dsn,
        user=config.user,
        password=config.password,
        encryption=True,
        autocommit=False,
        connection_timeout=15,
        fetch_dict=True,
    )
    try:
        yield ScopedConnection(connection, current_scope())
    except BaseException:
        with suppress(Exception):
            connection.rollback()
        raise
    finally:
        with suppress(Exception):
            connection.close()


def statements(path: Path) -> list[str]:
    text = path.read_text()
    if re.search(r"CREATE\s+OR\s+REPLACE\s+(?:PYTHON3|LUA)\s+(?:SCALAR|SET)\s+SCRIPT", text, re.I):
        return [text.rsplit("\n/", 1)[0].strip()]
    parts, start, quoted, index = [], 0, False, 0
    while index < len(text):
        if text[index] == "'":
            if quoted and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif text[index] == ";" and not quoted:
            if text[start:index].strip():
                parts.append(text[start:index].strip())
            start = index + 1
        index += 1
    if text[start:].strip():
        parts.append(text[start:].strip())
    return parts


def execute_file(connection, path: Path) -> list:
    return [connection.execute(statement) for statement in statements(path)]


def query(sql: str, parameters: dict | None = None) -> list[dict]:
    with connect() as connection:
        return connection.execute(sql, parameters or {}).fetchall()
