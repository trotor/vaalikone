"""Dialect-portable column types.

PostgreSQL: native UUID / pgvector.Vector / JSONB / TIMESTAMP.
SQLite: CHAR(32) GUID / float32 BLOB vector (sqlite-vec) / JSON / DateTime.
"""

import struct
import uuid

from sqlalchemy import CHAR, JSON, DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP as PG_TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

try:
    from pgvector.sqlalchemy import Vector as PG_Vector
except ImportError:  # pragma: no cover
    PG_Vector = None


class GUID(TypeDecorator):
    """UUID on PostgreSQL, CHAR(32) hex on SQLite."""

    impl = PG_UUID
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return value.hex if isinstance(value, uuid.UUID) else uuid.UUID(str(value)).hex

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


class VectorType(TypeDecorator):
    """Embedding vector: pgvector.Vector on PostgreSQL, float32 BLOB on SQLite."""

    impl = PG_Vector if PG_Vector is not None else JSON
    cache_ok = True

    def __init__(self, dim: int | None = None):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PG_Vector is not None:
            return dialect.type_descriptor(PG_Vector(self.dim))
        from sqlalchemy import BLOB
        return dialect.type_descriptor(BLOB())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return struct.pack(f"<{len(value)}f", *value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        return list(struct.unpack(f"<{len(value) // 4}f", value))


class JSONType(TypeDecorator):
    """JSONB on PostgreSQL, JSON on SQLite."""

    impl = PG_JSONB
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


class TimestampType(TypeDecorator):
    """TIMESTAMP(timezone=True) on PostgreSQL, DateTime on SQLite."""

    impl = PG_TIMESTAMP
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_TIMESTAMP(timezone=True))
        return dialect.type_descriptor(DateTime(timezone=True))
