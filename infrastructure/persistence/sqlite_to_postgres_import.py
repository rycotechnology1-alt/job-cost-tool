"""SQLite to Postgres lineage import helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql

from infrastructure.persistence.postgres_migrations import apply_postgres_migrations


TABLE_IMPORT_ORDER = [
    "organizations",
    "users",
    "template_artifacts",
    "trusted_profiles",
    "trusted_profile_versions",
    "trusted_profile_drafts",
    "profile_snapshots",
    "source_documents",
    "processing_runs",
    "run_records",
    "review_sessions",
    "reviewed_record_edits",
    "export_artifacts",
    "trusted_profile_observations",
]

BOOLEAN_COLUMNS = {
    "organizations": {"is_seeded"},
    "users": {"is_active"},
    "trusted_profile_observations": {"is_resolved"},
}


def import_sqlite_lineage_to_postgres(
    *,
    sqlite_database_path: str | Path,
    postgres_connection_string: str,
    schema_name: str = "public",
    migration_connection_string: str | None = None,
    truncate_existing: bool = False,
) -> dict[str, int]:
    """Copy all current lineage tables from SQLite into Postgres, preserving stable IDs."""
    apply_postgres_migrations(
        connection_string=migration_connection_string or postgres_connection_string,
        schema_name=schema_name,
    )
    with sqlite3.connect(str(sqlite_database_path)) as sqlite_connection:
        sqlite_connection.row_factory = sqlite3.Row
        with psycopg.connect(postgres_connection_string) as postgres_connection:
            postgres_connection.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name))
            )
            if truncate_existing:
                postgres_connection.execute(
                    sql.SQL("TRUNCATE TABLE {} CASCADE").format(
                        sql.SQL(", ").join(sql.Identifier(table_name) for table_name in reversed(TABLE_IMPORT_ORDER))
                    )
                )
            imported_counts: dict[str, int] = {}
            for table_name in TABLE_IMPORT_ORDER:
                rows = sqlite_connection.execute(f"SELECT * FROM {table_name}").fetchall()
                imported_counts[table_name] = len(rows)
                if not rows:
                    continue
                column_names = list(rows[0].keys())
                insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table_name),
                    sql.SQL(", ").join(sql.Identifier(column_name) for column_name in column_names),
                    sql.SQL(", ").join(sql.Placeholder() for _ in column_names),
                )
                with postgres_connection.cursor() as cursor:
                    cursor.executemany(
                        insert_sql.as_string(postgres_connection),
                        [
                            tuple(
                                _normalize_sqlite_value(table_name, column_name, row[column_name])
                                for column_name in column_names
                            )
                            for row in rows
                        ],
                    )
            return imported_counts


def _normalize_sqlite_value(table_name: str, column_name: str, value):
    if value is None:
        return None
    if column_name in BOOLEAN_COLUMNS.get(table_name, set()):
        return bool(value)
    return value
