"""CLI for importing compatibility lineage data from SQLite into Postgres."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from infrastructure.persistence.sqlite_to_postgres_import import import_sqlite_lineage_to_postgres


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-db", required=True, help="Path to the source SQLite lineage database.")
    parser.add_argument("--postgres-url", required=True, help="Target Postgres connection string.")
    parser.add_argument(
        "--migration-postgres-url",
        help="Optional direct/admin Postgres connection string for applying schema migrations.",
    )
    parser.add_argument("--schema", default="public", help="Target Postgres schema name.")
    parser.add_argument(
        "--truncate-existing",
        action="store_true",
        help="Truncate the target lineage tables before importing.",
    )
    args = parser.parse_args()

    imported_counts = import_sqlite_lineage_to_postgres(
        sqlite_database_path=args.sqlite_db,
        postgres_connection_string=args.postgres_url,
        schema_name=args.schema,
        migration_connection_string=args.migration_postgres_url,
        truncate_existing=args.truncate_existing,
    )
    print(json.dumps(imported_counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
