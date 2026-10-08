import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    dsn: str
    user: str
    password: str = field(repr=False)


def settings() -> Settings:
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    required = ["EXASOL_DSN", "EXASOL_USER", "EXASOL_PASSWORD"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("Configure .env first; missing: " + ", ".join(missing))
    return Settings(*(values[key] for key in required))
