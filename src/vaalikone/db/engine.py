"""Shared async engine factory.

SQLite (default): loads the sqlite-vec extension on every connection,
enables WAL + foreign keys. PostgreSQL: plain asyncpg engine.
"""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_db_engine(url: str, **kwargs):
    if is_sqlite(url):
        kwargs.setdefault("connect_args", {})
        engine = create_async_engine(url, **kwargs)

        @sa.event.listens_for(engine.sync_engine, "connect")
        def _load_sqlite_extensions(dbapi_conn, _record):
            import sqlite_vec

            # aiosqlite käärii natiivin yhteyden: päästään käsiksi sqlite3.Connectioniin
            raw = dbapi_conn
            if hasattr(raw, "_connection"):
                raw = raw._connection._conn
            raw.enable_load_extension(True)
            sqlite_vec.load(raw)
            raw.enable_load_extension(False)
            raw.execute("PRAGMA journal_mode=WAL")
            raw.execute("PRAGMA foreign_keys=ON")
            raw.execute("PRAGMA busy_timeout=30000")

        return engine
    return create_async_engine(url, **kwargs)
