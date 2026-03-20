"""
migrations/migrate.py — Lightweight versioned SQL migration runner.

How it works:
  - Maintains a `schema_migrations` table in Supabase that tracks which
    migration files have already been applied.
  - On each run, discovers *.sql files in this directory, sorts them by
    filename (which must start with a zero-padded integer version), and
    applies only the ones not yet recorded.
  - Each migration runs inside a transaction so a partial failure is
    automatically rolled back and the migration table is not updated.

Naming convention for migration files:
    0001_initial_schema.sql
    0002_add_paused_column.sql
    0003_add_alert_notes_column.sql

Usage:
    python migrations/migrate.py            # apply pending migrations
    python migrations/migrate.py --dry-run  # list pending, don't apply
    python migrations/migrate.py --status   # show all migrations and their status
"""

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path

import asyncpg

# Allow running as a standalone script from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import configure_logging, settings

configure_logging()
logger = logging.getLogger("migrate")

MIGRATIONS_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER      PRIMARY KEY,
    filename    TEXT         NOT NULL,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
"""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_migrations() -> list[tuple[int, Path]]:
    """
    Return all *.sql files in MIGRATIONS_DIR, sorted by version number.
    Raises ValueError on invalid filenames.
    """
    found: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _VERSION_RE.match(path.name)
        if not m:
            raise ValueError(
                f"Migration filename '{path.name}' must match the pattern "
                "<version>_<description>.sql  e.g. 0001_initial_schema.sql"
            )
        found.append((int(m.group(1)), path))
    found.sort(key=lambda t: t[0])

    # Check for duplicate version numbers
    versions = [v for v, _ in found]
    if len(versions) != len(set(versions)):
        raise ValueError("Duplicate migration version numbers detected.")

    return found


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_migrations(dry_run: bool = False, status_only: bool = False) -> None:
    all_migrations = discover_migrations()

    conn: asyncpg.Connection = await asyncpg.connect(
        settings.supabase_db_url, ssl="require"
    )
    try:
        await conn.execute(_BOOTSTRAP_SQL)

        applied: set[int] = {
            row["version"]
            for row in await conn.fetch("SELECT version FROM schema_migrations")
        }

        pending = [(v, p) for v, p in all_migrations if v not in applied]

        if status_only:
            _print_status(all_migrations, applied)
            return

        if not pending:
            logger.info("All %d migration(s) already applied. Nothing to do.", len(all_migrations))
            return

        logger.info(
            "%d of %d migration(s) pending.",
            len(pending), len(all_migrations),
        )

        if dry_run:
            for version, path in pending:
                logger.info("[DRY-RUN] Would apply: %s", path.name)
            return

        for version, path in pending:
            sql = path.read_text(encoding="utf-8").strip()
            if not sql:
                logger.warning("Skipping empty migration file: %s", path.name)
                continue

            logger.info("Applying migration %04d: %s ...", version, path.name)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, filename) VALUES ($1, $2)",
                    version, path.name,
                )
            logger.info("  ✓ Applied %s", path.name)

        logger.info("Migration complete. %d new migration(s) applied.", len(pending))

    finally:
        await conn.close()


def _print_status(
    all_migrations: list[tuple[int, Path]],
    applied: set[int],
) -> None:
    print(f"\n{'VERSION':<10}  {'STATUS':<12}  FILENAME")
    print("-" * 60)
    for version, path in all_migrations:
        status = "✓ applied" if version in applied else "✗ pending"
        print(f"{version:<10}  {status:<12}  {path.name}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending migrations without applying them",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the status of all migrations and exit",
    )
    args = parser.parse_args()

    asyncio.run(run_migrations(dry_run=args.dry_run, status_only=args.status))
