import re
from contextlib import contextmanager
from pathlib import Path

import pyexasol
from packaging.version import InvalidVersion, Version

from milaan.config import settings


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
        yield connection
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def statements(path: Path) -> list[str]:
    text = path.read_text()
    if "CREATE OR REPLACE PYTHON3" in text.upper():
        return [text.rsplit("\n/", 1)[0].strip()]
    return [part.strip() for part in text.split(";") if part.strip()]


def execute_file(connection, path: Path) -> list:
    return [connection.execute(statement) for statement in statements(path)]


def query(sql: str, parameters: dict | None = None) -> list[dict]:
    with connect() as connection:
        return connection.execute(sql, parameters or {}).fetchall()
