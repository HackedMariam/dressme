"""
Copy every table from one database to another - typically the SQLite file to PostgreSQL.

    cd backend
    venv/Scripts/python migrate_db.py --target postgresql://redundancy:PASSWORD@localhost:5433/purchase_redundancy
    (--source defaults to data/redundancy.db; add --replace to overwrite a non-empty target)

Then set DATABASE_URL to the target in .env and restart the API. The source is never modified.
"""

import argparse
import logging
import sys

from sqlalchemy import Integer, create_engine, func, inspect, select, text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")

BATCH = 500


def _normalize(url: str) -> str:
    if url.startswith(("postgresql://", "postgres://")):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    return url


def migrate(source_url: str, target_url: str, replace: bool = False) -> dict:
    from models import Base

    source = create_engine(_normalize(source_url))
    target = create_engine(_normalize(target_url))
    Base.metadata.create_all(target)

    source_tables = set(inspect(source).get_table_names())
    copied = {}
    with source.connect() as src, target.begin() as dst:
        for table in Base.metadata.sorted_tables:  # parents before children (foreign keys)
            if table.name not in source_tables:
                continue
            existing = dst.execute(select(func.count()).select_from(table)).scalar()
            if existing and not replace:
                raise SystemExit(f"Target table {table.name} already has {existing} rows - use --replace to overwrite")
            if existing:
                dst.execute(table.delete())

        for table in Base.metadata.sorted_tables:
            if table.name not in source_tables:
                continue
            # Old SQLite files may miss recent columns: copy the ones both sides have
            source_columns = {c["name"] for c in inspect(source).get_columns(table.name)}
            columns = [c for c in table.columns if c.name in source_columns]
            rows = src.execute(select(*[table.c[c.name] for c in columns])).mappings()
            count, batch = 0, []
            for row in rows:
                batch.append(dict(row))
                if len(batch) >= BATCH:
                    dst.execute(table.insert(), batch)
                    count += len(batch)
                    batch = []
            if batch:
                dst.execute(table.insert(), batch)
                count += len(batch)
            copied[table.name] = count
            logger.info(f"{table.name}: {count} rows")

        if target.dialect.name == "postgresql":  # integer ids inserted explicitly -> move the sequences past them
            for table in Base.metadata.sorted_tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and isinstance(pk[0].type, Integer):
                    dst.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                        f"COALESCE((SELECT MAX({pk[0].name}) FROM {table.name}), 0) + 1, false)"))
    return copied


def main(argv=None) -> int:
    from config import DATABASE_PATH

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=f"sqlite:///{(DATABASE_PATH / 'redundancy.db').as_posix()}")
    parser.add_argument("--target", required=True)
    parser.add_argument("--replace", action="store_true", help="empty the target tables first")
    args = parser.parse_args(argv)
    if _normalize(args.source) == _normalize(args.target):
        parser.error("source and target are the same database")

    copied = migrate(args.source, args.target, args.replace)
    logger.info(f"✅ Migrated {sum(copied.values())} rows in {len(copied)} tables. "
                f"Now set DATABASE_URL={args.target.split('@')[0].split(':')[0]}://...@{args.target.split('@')[-1]} in .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
