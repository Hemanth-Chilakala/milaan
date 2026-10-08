import pytest
from packaging.version import InvalidVersion, Version

from milaan.db import PersonalConnection


def version(value):
    connection = object.__new__(PersonalConnection)
    connection.login_info = {"releaseVersion": value}
    return connection.exasol_db_version


def test_nano_release_transport_feature_detection():
    assert version("2026.2.0-nano.3") == Version("2026.2.0")
    assert version("8.32.0") == Version("8.32.0")
    with pytest.raises(InvalidVersion):
        version("unknown-release")
