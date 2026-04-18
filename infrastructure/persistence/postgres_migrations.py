"""Minimal Postgres schema migration runner for lineage persistence."""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def apply_postgres_migrations(*, connection_string: str, schema_name: str = "public") -> None:
    """Apply all tracked Postgres migrations into one schema."""
    migrations_dir = Path(__file__).with_name("postgres_migrations")
    resolved_schema = schema_name.strip() or "public"
    with psycopg.connect(connection_string, row_factory=dict_row) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(resolved_schema))
        )
        connection.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(resolved_schema))
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        applied_migrations = {
            row["migration_name"]
            for row in connection.execute(
                "SELECT migration_name FROM schema_migrations ORDER BY migration_name ASC"
            ).fetchall()
        }
        for migration_path in sorted(migrations_dir.glob("*.sql")):
            migration_name = migration_path.name
            if migration_name in applied_migrations:
                continue
            connection.execute(migration_path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
                (migration_name,),
            )

