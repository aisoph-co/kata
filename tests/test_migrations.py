"""Alembic migrations must apply on SQLite, not just Postgres:
`Base.metadata.create_all` (every other test's fixture) never exercises this
path — only a real alembic run does.
"""

from __future__ import annotations

import os

from alembic import command
from alembic.config import Config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_alembic_upgrade_head_applies_on_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "migrations_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    config = Config(os.path.join(ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(ROOT, "migrations"))

    command.upgrade(config, "head")
    command.downgrade(config, "base")
