# Vaalikone Core Infra Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core infrastructure — project setup, database models, Docker environment, Alembic migrations, eduskunta connector, and CLI skeleton — so that we can ingest real Finnish parliament data.

**Architecture:** Python monorepo with FastAPI backend, PostgreSQL+pgvector database, Celery+Redis task queue. This plan covers foundational layers only: models, database, Docker Compose, the eduskunta data connector, and a basic CLI. Query pipeline, MCP server, and Keycloak come in later plans.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16 + pgvector, Celery, Redis, Click, httpx, trafilatura, LiteLLM, Docker Compose, pytest, ruff

**Eduskunta API reference:**
- Base URL: `https://avoindata.eduskunta.fi`
- No auth required. JSON responses with `rowData` as array-of-arrays matching `columnNames`.
- Key tables: `MemberOfParliament` (personId PK), `SaliDBAanestys` (AanestysId PK), `SaliDBAanestysEdustaja` (EdustajaId PK)
- Bulk download: `/api/v1/tables/{table}/batch?pkName={pk}&pkStartValue={val}&perPage=100`, paginate via `pkLastValue` until `hasMore=false`
- Note: API retiring end of 2026, new API at eduskunta.fi/avoin-data — build connector against current API but keep it isolated for easy swap.

---

## Task 1: Project scaffolding + pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `src/vaalikone/__init__.py`
- Create: `src/vaalikone/core/__init__.py`
- Create: `src/vaalikone/models/__init__.py`
- Create: `src/vaalikone/api/__init__.py`
- Create: `src/vaalikone/cli/__init__.py`
- Create: `src/vaalikone/ingest/__init__.py`
- Create: `src/vaalikone/ingest/connectors/__init__.py`
- Create: `src/vaalikone/query/__init__.py`
- Create: `src/vaalikone/workers/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `config/parties.yaml`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vaalikone"
version = "0.1.0"
description = "Finnish political data database and AI query service"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pgvector>=0.3.0",
    "celery[redis]>=5.4.0",
    "click>=8.1.0",
    "httpx>=0.27.0",
    "trafilatura>=1.12.0",
    "pymupdf>=1.24.0",
    "litellm>=1.50.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "pyyaml>=6.0.0",
    "python-multipart>=0.0.12",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.7.0",
    "httpx>=0.27.0",
]

[project.scripts]
vaalikone = "vaalikone.cli.main:cli"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["src/vaalikone"]
```

- [ ] **Step 2: Create package __init__.py files**

All `__init__.py` files are empty:

```
src/vaalikone/__init__.py
src/vaalikone/core/__init__.py
src/vaalikone/models/__init__.py
src/vaalikone/api/__init__.py
src/vaalikone/cli/__init__.py
src/vaalikone/ingest/__init__.py
src/vaalikone/ingest/connectors/__init__.py
src/vaalikone/query/__init__.py
src/vaalikone/workers/__init__.py
tests/__init__.py
```

- [ ] **Step 3: Create .gitignore**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
*.egg
.env
.venv/
venv/
*.db
*.sqlite3
.ruff_cache/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
```

- [ ] **Step 4: Create .env.example**

```env
DATABASE_URL=postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone
REDIS_URL=redis://localhost:6382/0
OPENAI_API_KEY=sk-your-key-here
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_LLM_MODEL=gpt-4o
DEFAULT_EMBED_MODEL=text-embedding-3-small
KEYCLOAK_ENABLED=false
KEYCLOAK_URL=http://localhost:8083
```

- [ ] **Step 5: Create config/parties.yaml**

```yaml
parties:
  # Eduskuntapuolueet
  - name: "Suomen Sosiaalidemokraattinen Puolue"
    abbreviation: "SDP"
    website: "https://www.sdp.fi"
    ideology: "Sosialidemokratia"
    founded: 1899

  - name: "Kansallinen Kokoomus"
    abbreviation: "KOK"
    website: "https://www.kokoomus.fi"
    ideology: "Konservatismi, liberalismi"
    founded: 1918

  - name: "Perussuomalaiset"
    abbreviation: "PS"
    website: "https://www.perussuomalaiset.fi"
    ideology: "Kansalliskonservatismi, populismi"
    founded: 1995

  - name: "Suomen Keskusta"
    abbreviation: "KESK"
    website: "https://www.keskusta.fi"
    ideology: "Keskustalaisuus, agraariliberalismi"
    founded: 1906

  - name: "Vihreä liitto"
    abbreviation: "VIHR"
    website: "https://www.vihreat.fi"
    ideology: "Vihreä politiikka"
    founded: 1987

  - name: "Vasemmistoliitto"
    abbreviation: "VAS"
    website: "https://www.vasemmisto.fi"
    ideology: "Demokraattinen sosialismi"
    founded: 1990

  - name: "Svenska folkpartiet i Finland"
    abbreviation: "RKP"
    website: "https://www.sfp.fi"
    ideology: "Liberalismi, kielivähemmistön oikeudet"
    founded: 1906

  - name: "Kristillisdemokraatit"
    abbreviation: "KD"
    website: "https://www.kd.fi"
    ideology: "Kristillisdemokratia"
    founded: 1958

  - name: "Liike Nyt"
    abbreviation: "LIIK"
    website: "https://www.liikenyt.fi"
    ideology: "Liberalismi"
    founded: 2018

  # Pienpuolueet
  - name: "Piraattipuolue"
    abbreviation: "PIR"
    website: "https://www.piraattipuolue.fi"
    ideology: "Digitaalinen vapaus"
    founded: 2008

  - name: "Eläinoikeuspuolue"
    abbreviation: "EOP"
    website: "https://www.elainoikeuspuolue.fi"
    ideology: "Eläinoikeudet"
    founded: 2015

  - name: "Feministinen puolue"
    abbreviation: "FP"
    website: "https://www.feministinenpuolue.fi"
    ideology: "Feminismi"
    founded: 2016

  - name: "Valta kuuluu kansalle"
    abbreviation: "VKK"
    website: "https://www.valtakuuluukansalle.fi"
    ideology: "Kansalliskonservatismi"
    founded: 2021

  - name: "Suomen Kommunistinen Puolue"
    abbreviation: "SKP"
    website: "https://www.skp.fi"
    ideology: "Kommunismi"
    founded: 1994

  - name: "Liberaalipuolue"
    abbreviation: "LIB"
    website: "https://www.liberaalipuolue.fi"
    ideology: "Klassinen liberalismi"
    founded: 2016

  - name: "Sinimusta Liike"
    abbreviation: "SML"
    website: "https://www.sinimustaliike.fi"
    ideology: "Kansallismielisyys"
    founded: 2019
```

- [ ] **Step 6: Create tests/conftest.py**

```python
import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    url = "postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone_test"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
```

- [ ] **Step 7: Commit**

```bash
git init
git add pyproject.toml src/ tests/ .gitignore .env.example config/
git commit -m "feat: project scaffolding with pyproject.toml and package structure"
```

---

## Task 2: Core config + database setup

**Files:**
- Create: `src/vaalikone/core/config.py`
- Create: `src/vaalikone/core/database.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test for config**

Create `tests/test_config.py`:

```python
from vaalikone.core.config import Settings


def test_settings_defaults():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5435/db",
        REDIS_URL="redis://localhost:6382/0",
    )
    assert settings.DEFAULT_LLM_MODEL == "gpt-4o"
    assert settings.DEFAULT_EMBED_MODEL == "text-embedding-3-small"
    assert settings.KEYCLOAK_ENABLED is False
    assert settings.OLLAMA_BASE_URL == "http://localhost:11434"


def test_settings_custom_values():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5435/db",
        REDIS_URL="redis://localhost:6382/0",
        DEFAULT_LLM_MODEL="ollama/llama3",
        KEYCLOAK_ENABLED=True,
    )
    assert settings.DEFAULT_LLM_MODEL == "ollama/llama3"
    assert settings.KEYCLOAK_ENABLED is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/teroronkko/code/vaalikone && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vaalikone.core.config'`

- [ ] **Step 3: Implement config**

Create `src/vaalikone/core/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6382/0"

    OPENAI_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    DEFAULT_EMBED_MODEL: str = "text-embedding-3-small"

    KEYCLOAK_ENABLED: bool = False
    KEYCLOAK_URL: str = "http://localhost:8083"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Implement database module**

Create `src/vaalikone/core/database.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vaalikone.core.config import get_settings


def create_engine():
    settings = get_settings()
    return create_async_engine(settings.DATABASE_URL, echo=False)


def create_session_factory(engine=None):
    if engine is None:
        engine = create_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session():
    factory = create_session_factory()
    async with factory() as session:
        yield session
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/teroronkko/code/vaalikone && pip install -e ".[dev]" && python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/vaalikone/core/config.py src/vaalikone/core/database.py tests/test_config.py
git commit -m "feat: core config with pydantic-settings and async database setup"
```

---

## Task 3: SQLAlchemy models

**Files:**
- Create: `src/vaalikone/models/base.py`
- Create: `src/vaalikone/models/party.py`
- Create: `src/vaalikone/models/representative.py`
- Create: `src/vaalikone/models/source.py`
- Create: `src/vaalikone/models/document.py`
- Create: `src/vaalikone/models/embedding.py`
- Create: `src/vaalikone/models/vote.py`
- Create: `src/vaalikone/models/query_log.py`
- Modify: `src/vaalikone/models/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for models**

Create `tests/test_models.py`:

```python
import uuid

from sqlalchemy import select

from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source, SourceType, SourceStatus
from vaalikone.models.document import Document, ContentType
from vaalikone.models.vote import Vote, VoteChoice


async def test_create_party(db_session):
    party = Party(
        name="Testipuolue",
        abbreviation="TEST",
        website="https://test.fi",
    )
    db_session.add(party)
    await db_session.flush()

    result = await db_session.execute(select(Party).where(Party.abbreviation == "TEST"))
    fetched = result.scalar_one()
    assert fetched.name == "Testipuolue"
    assert fetched.id is not None


async def test_create_representative_with_party(db_session):
    party = Party(name="Testipuolue2", abbreviation="TS2")
    db_session.add(party)
    await db_session.flush()

    rep = Representative(
        party_id=party.id,
        first_name="Matti",
        last_name="Meikäläinen",
        constituency="Helsinki",
    )
    db_session.add(rep)
    await db_session.flush()

    result = await db_session.execute(
        select(Representative).where(Representative.last_name == "Meikäläinen")
    )
    fetched = result.scalar_one()
    assert fetched.party_id == party.id
    assert fetched.first_name == "Matti"


async def test_create_source(db_session):
    source = Source(
        source_type=SourceType.WEBSITE,
        url="https://sdp.fi/vaaliohjelma",
        title="SDP Vaaliohjelma",
        status=SourceStatus.PENDING,
    )
    db_session.add(source)
    await db_session.flush()
    assert source.id is not None
    assert source.status == SourceStatus.PENDING


async def test_create_document(db_session):
    source = Source(
        source_type=SourceType.WEBSITE,
        url="https://test.fi/doc",
        title="Test doc",
        status=SourceStatus.INDEXED,
    )
    db_session.add(source)
    await db_session.flush()

    doc = Document(
        source_id=source.id,
        title="Test Document",
        content_text="Tämä on testidokumentti.",
        content_type=ContentType.MUU,
    )
    db_session.add(doc)
    await db_session.flush()
    assert doc.id is not None


async def test_create_vote(db_session):
    party = Party(name="Testipuolue3", abbreviation="TS3")
    db_session.add(party)
    await db_session.flush()

    rep = Representative(party_id=party.id, first_name="Liisa", last_name="Testaaja")
    db_session.add(rep)
    await db_session.flush()

    vote = Vote(
        representative_id=rep.id,
        session="2026",
        subject="Testi äänestys",
        vote=VoteChoice.JAA,
    )
    db_session.add(vote)
    await db_session.flush()
    assert vote.vote == VoteChoice.JAA
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create base model**

Create `src/vaalikone/models/base.py`:

```python
import uuid

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
```

- [ ] **Step 4: Create Party model**

Create `src/vaalikone/models/party.py`:

```python
from sqlalchemy import Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class Party(UUIDMixin, Base):
    __tablename__ = "parties"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    abbreviation: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    founded: Mapped[int | None] = mapped_column(Integer)
    ideology: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)

    representatives = relationship("Representative", back_populates="party")
    sources = relationship("Source", back_populates="party")
    documents = relationship("Document", back_populates="party")
```

- [ ] **Step 5: Create Representative model**

Create `src/vaalikone/models/representative.py`:

```python
import uuid

from sqlalchemy import Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class Representative(UUIDMixin, Base):
    __tablename__ = "representatives"

    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("parties.id"))
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    constituency: Mapped[str | None] = mapped_column(Text)
    elected_year: Mapped[int | None] = mapped_column(Integer)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    email: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    social_media: Mapped[dict | None] = mapped_column(JSONB)

    party = relationship("Party", back_populates="representatives")
    votes = relationship("Vote", back_populates="representative")
    sources = relationship("Source", back_populates="representative")
    documents = relationship("Document", back_populates="representative")
```

- [ ] **Step 6: Create Source model**

Create `src/vaalikone/models/source.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class SourceType(str, enum.Enum):
    WEBSITE = "website"
    PDF = "pdf"
    SOCIAL_MEDIA = "social_media"
    API = "api"
    MANUAL = "manual"


class SourceStatus(str, enum.Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"


class Source(UUIDMixin, Base):
    __tablename__ = "sources"

    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False))
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False), default=SourceStatus.PENDING
    )
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parties.id"), nullable=True
    )
    representative_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("representatives.id"), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    party = relationship("Party", back_populates="sources")
    representative = relationship("Representative", back_populates="sources")
    documents = relationship("Document", back_populates="source")
```

- [ ] **Step 7: Create Document model**

Create `src/vaalikone/models/document.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class ContentType(str, enum.Enum):
    VAALIOHJELMA = "vaaliohjelma"
    BLOGIKIRJOITUS = "blogikirjoitus"
    SOME_POSTAUS = "some_postaus"
    PUHEENVUORO = "puheenvuoro"
    AANESTYS = "äänestys"
    KIRJALLINEN_KYSYMYS = "kirjallinen_kysymys"
    ALOITE = "aloite"
    MUU = "muu"


class Document(UUIDMixin, Base):
    __tablename__ = "documents"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"))
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parties.id"), nullable=True
    )
    representative_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("representatives.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, native_enum=False), default=ContentType.MUU
    )
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    language: Mapped[str] = mapped_column(Text, default="fi")
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_topics: Mapped[dict | None] = mapped_column(JSONB)
    ai_sentiment: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    source = relationship("Source", back_populates="documents")
    party = relationship("Party", back_populates="documents")
    representative = relationship("Representative", back_populates="documents")
    embeddings = relationship("Embedding", back_populates="document")
```

- [ ] **Step 8: Create Embedding model**

Create `src/vaalikone/models/embedding.py`:

```python
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class Embedding(UUIDMixin, Base):
    __tablename__ = "embeddings"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(1536))
    model_name: Mapped[str] = mapped_column(Text)

    document = relationship("Document", back_populates="embeddings")
```

- [ ] **Step 9: Create Vote model**

Create `src/vaalikone/models/vote.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaalikone.models.base import Base, UUIDMixin


class VoteChoice(str, enum.Enum):
    JAA = "jaa"
    EI = "ei"
    TYHJA = "tyhjä"
    POISSA = "poissa"


class Vote(UUIDMixin, Base):
    __tablename__ = "votes"

    representative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("representatives.id")
    )
    session: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    vote: Mapped[VoteChoice] = mapped_column(Enum(VoteChoice, native_enum=False))
    voted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    document_url: Mapped[str | None] = mapped_column(Text)

    representative = relationship("Representative", back_populates="votes")
```

- [ ] **Step 10: Create QueryLog model**

Create `src/vaalikone/models/query_log.py`:

```python
from datetime import datetime

from sqlalchemy import Text, Integer
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from vaalikone.models.base import Base, UUIDMixin


class QueryLog(UUIDMixin, Base):
    __tablename__ = "query_log"

    user_id: Mapped[str | None] = mapped_column(Text)
    query_text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(Text)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="now()"
    )
```

- [ ] **Step 11: Update models __init__.py**

Modify `src/vaalikone/models/__init__.py`:

```python
from vaalikone.models.base import Base
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source, SourceType, SourceStatus
from vaalikone.models.document import Document, ContentType
from vaalikone.models.embedding import Embedding
from vaalikone.models.vote import Vote, VoteChoice
from vaalikone.models.query_log import QueryLog

__all__ = [
    "Base",
    "Party",
    "Representative",
    "Source",
    "SourceType",
    "SourceStatus",
    "Document",
    "ContentType",
    "Embedding",
    "Vote",
    "VoteChoice",
    "QueryLog",
]
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (requires running PostgreSQL — see Task 4)

- [ ] **Step 13: Commit**

```bash
git add src/vaalikone/models/ tests/test_models.py
git commit -m "feat: SQLAlchemy models for parties, representatives, sources, documents, votes"
```

---

## Task 4: Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `Dockerfile`
- Create: `docker/postgres/init.sql`

- [ ] **Step 1: Create PostgreSQL init script**

Create `docker/postgres/init.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE vaalikone_test;
\c vaalikone_test
CREATE EXTENSION IF NOT EXISTS vector;
```

- [ ] **Step 2: Create Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/
COPY alembic/ alembic/
COPY alembic.ini .

RUN pip install --no-cache-dir .

EXPOSE 8003

CMD ["uvicorn", "vaalikone.api.app:app", "--host", "0.0.0.0", "--port", "8003"]
```

- [ ] **Step 3: Create docker-compose.yml**

Create `docker-compose.yml`:

```yaml
services:
  api:
    build: .
    ports:
      - "8003:8003"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./config:/app/config:ro

  worker:
    build: .
    command: celery -A vaalikone.workers.tasks worker --loglevel=info
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./config:/app/config:ro

  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5435:5432"
    environment:
      POSTGRES_USER: vaalikone
      POSTGRES_PASSWORD: vaalikone
      POSTGRES_DB: vaalikone
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vaalikone"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6382:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    ports:
      - "8083:8080"
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
    command: start-dev
    profiles:
      - auth

volumes:
  pgdata:
```

- [ ] **Step 4: Create .env from example**

```bash
cp .env.example .env
```

- [ ] **Step 5: Start services and verify**

```bash
docker compose up -d postgres redis
docker compose ps
```

Expected: postgres and redis running, healthy.

- [ ] **Step 6: Run model tests against real DB**

```bash
python -m pytest tests/test_models.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml Dockerfile docker/ .env.example
git commit -m "feat: Docker Compose with PostgreSQL+pgvector, Redis, and Keycloak"
```

---

## Task 5: Alembic migrations

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`

- [ ] **Step 1: Initialize Alembic**

```bash
cd /Users/teroronkko/code/vaalikone
alembic init alembic
```

- [ ] **Step 2: Configure alembic.ini**

Edit `alembic.ini` — set the sqlalchemy.url line:

```ini
sqlalchemy.url = postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone
```

- [ ] **Step 3: Configure alembic/env.py for async + our models**

Replace `alembic/env.py` with:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from vaalikone.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(config.get_main_option("sqlalchemy.url"))
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Generate initial migration**

```bash
alembic revision --autogenerate -m "initial schema"
```

- [ ] **Step 5: Run migration**

```bash
alembic upgrade head
```

Expected: Tables created in PostgreSQL.

- [ ] **Step 6: Verify tables exist**

```bash
docker exec -it $(docker ps -qf "name=postgres") psql -U vaalikone -c "\dt"
```

Expected: parties, representatives, sources, documents, embeddings, votes, query_log tables.

- [ ] **Step 7: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: Alembic migration setup with initial schema"
```

---

## Task 6: CLI skeleton + party seeding

**Files:**
- Create: `src/vaalikone/cli/main.py`
- Create: `src/vaalikone/cli/seed.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing test for CLI**

Create `tests/test_cli.py`:

```python
from click.testing import CliRunner

from vaalikone.cli.main import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Vaalikone" in result.output


def test_cli_seed_parties_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["seed", "parties", "--help"])
    assert result.exit_code == 0
    assert "parties.yaml" in result.output or "puolueet" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI main**

Create `src/vaalikone/cli/main.py`:

```python
import click

from vaalikone.cli.seed import seed


@click.group()
def cli():
    """Vaalikone — Suomen poliittisen datan työkalu."""
    pass


cli.add_command(seed)


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Implement seed command**

Create `src/vaalikone/cli/seed.py`:

```python
import asyncio
from pathlib import Path

import click
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.models.party import Party


async def _seed_parties(config_path: str):
    path = Path(config_path)
    if not path.exists():
        click.echo(f"Config file not found: {path}")
        return

    with open(path) as f:
        data = yaml.safe_load(f)

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        count = 0
        for party_data in data.get("parties", []):
            result = await session.execute(
                select(Party).where(Party.abbreviation == party_data["abbreviation"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                click.echo(f"  Exists: {party_data['abbreviation']}")
                continue

            party = Party(
                name=party_data["name"],
                abbreviation=party_data["abbreviation"],
                website=party_data.get("website"),
                ideology=party_data.get("ideology"),
                founded=party_data.get("founded"),
            )
            session.add(party)
            count += 1
            click.echo(f"  Added: {party_data['abbreviation']}")

        await session.commit()
        click.echo(f"\nSeeded {count} new parties.")

    await engine.dispose()


@click.group()
def seed():
    """Seed database with initial data."""
    pass


@seed.command()
@click.option(
    "--config",
    default="config/parties.yaml",
    help="Path to parties.yaml config file.",
)
def parties(config: str):
    """Seed puolueet config/parties.yaml -tiedostosta."""
    click.echo("Seeding parties...")
    asyncio.run(_seed_parties(config))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 6: Test party seeding against real DB**

```bash
vaalikone seed parties
```

Expected: 16 parties added.

- [ ] **Step 7: Commit**

```bash
git add src/vaalikone/cli/ tests/test_cli.py
git commit -m "feat: CLI skeleton with party seeding from parties.yaml"
```

---

## Task 7: Eduskunta connector — representatives

**Files:**
- Create: `src/vaalikone/ingest/connectors/eduskunta.py`
- Create: `tests/test_eduskunta.py`

- [ ] **Step 1: Write failing test for API client**

Create `tests/test_eduskunta.py`:

```python
import pytest

from vaalikone.ingest.connectors.eduskunta import EduskuntaClient


@pytest.fixture
def client():
    return EduskuntaClient()


async def test_fetch_table_page(client):
    """Fetch one page from MemberOfParliament table."""
    result = await client.fetch_table_page("MemberOfParliament", page=0, per_page=5)
    assert result["tableName"] == "MemberOfParliament"
    assert len(result["rowData"]) <= 5
    assert "columnNames" in result
    assert "personId" in result["columnNames"]


async def test_parse_rows(client):
    """Parse raw API response into list of dicts."""
    result = await client.fetch_table_page("MemberOfParliament", page=0, per_page=3)
    rows = client.parse_rows(result)
    assert len(rows) <= 3
    assert all("personId" in row for row in rows)
    assert all("firstname" in row for row in rows)
    assert all("lastname" in row for row in rows)


async def test_fetch_all_representatives(client):
    """Fetch a small batch of representatives and parse them."""
    reps = await client.fetch_representatives(max_pages=1, per_page=10)
    assert len(reps) > 0
    assert len(reps) <= 10
    first = reps[0]
    assert "personId" in first
    assert "firstname" in first
    assert "lastname" in first
    assert "party" in first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eduskunta.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement EduskuntaClient**

Create `src/vaalikone/ingest/connectors/eduskunta.py`:

```python
import httpx


BASE_URL = "https://avoindata.eduskunta.fi"


class EduskuntaClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url

    async def fetch_table_page(
        self, table: str, page: int = 0, per_page: int = 100
    ) -> dict:
        url = f"{self.base_url}/api/v1/tables/{table}/rows"
        params = {"page": page, "perPage": per_page}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def fetch_table_batch(
        self, table: str, pk_name: str, pk_start: int = 0, per_page: int = 100
    ) -> dict:
        url = f"{self.base_url}/api/v1/tables/{table}/batch"
        params = {"pkName": pk_name, "pkStartValue": pk_start, "perPage": per_page}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    def parse_rows(self, response: dict) -> list[dict]:
        columns = response["columnNames"]
        return [dict(zip(columns, row)) for row in response["rowData"]]

    async def fetch_representatives(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        all_reps = []
        page = 0
        while True:
            result = await self.fetch_table_page("MemberOfParliament", page=page, per_page=per_page)
            rows = self.parse_rows(result)
            all_reps.extend(rows)

            if not result.get("hasMore", False):
                break
            page += 1
            if max_pages and page >= max_pages:
                break

        return all_reps

    async def fetch_votes(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        all_votes = []
        page = 0
        while True:
            result = await self.fetch_table_page(
                "SaliDBAanestysEdustaja", page=page, per_page=per_page
            )
            rows = self.parse_rows(result)
            all_votes.extend(rows)

            if not result.get("hasMore", False):
                break
            page += 1
            if max_pages and page >= max_pages:
                break

        return all_votes

    async def fetch_vote_summaries(
        self, max_pages: int | None = None, per_page: int = 100
    ) -> list[dict]:
        all_summaries = []
        page = 0
        while True:
            result = await self.fetch_table_page(
                "SaliDBAanestys", page=page, per_page=per_page
            )
            rows = self.parse_rows(result)
            all_summaries.extend(rows)

            if not result.get("hasMore", False):
                break
            page += 1
            if max_pages and page >= max_pages:
                break

        return all_summaries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_eduskunta.py -v`
Expected: PASS (requires internet connection)

- [ ] **Step 5: Commit**

```bash
git add src/vaalikone/ingest/connectors/eduskunta.py tests/test_eduskunta.py
git commit -m "feat: Eduskunta API client for representatives and votes"
```

---

## Task 8: Eduskunta ingest command — save representatives to DB

**Files:**
- Create: `src/vaalikone/cli/ingest.py`
- Modify: `src/vaalikone/cli/main.py`
- Create: `tests/test_ingest_eduskunta.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_ingest_eduskunta.py`:

```python
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from vaalikone.cli.main import cli


def test_ingest_eduskunta_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "eduskunta" in result.output.lower() or "ingest" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest_eduskunta.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ingest CLI commands**

Create `src/vaalikone/cli/ingest.py`:

```python
import asyncio

import click
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.ingest.connectors.eduskunta import EduskuntaClient
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative
from vaalikone.models.source import Source, SourceType, SourceStatus
from vaalikone.models.vote import Vote, VoteChoice


# Maps eduskunta API party abbreviations to our abbreviations
PARTY_MAP = {
    "sd": "SDP",
    "kok": "KOK",
    "ps": "PS",
    "kesk": "KESK",
    "vihr": "VIHR",
    "vas": "VAS",
    "r": "RKP",
    "kd": "KD",
    "liik": "LIIK",
    "sin": "SML",
}


def _map_vote(api_vote: str) -> VoteChoice:
    mapping = {
        "Jaa": VoteChoice.JAA,
        "Ei": VoteChoice.EI,
        "Tyhjaa": VoteChoice.TYHJA,
        "Tyhjää": VoteChoice.TYHJA,
        "Poissa": VoteChoice.POISSA,
    }
    return mapping.get(api_vote, VoteChoice.POISSA)


async def _get_session():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, async_session


async def _find_party(session: AsyncSession, api_party: str) -> Party | None:
    abbr = PARTY_MAP.get(api_party.lower(), api_party.upper())
    result = await session.execute(select(Party).where(Party.abbreviation == abbr))
    return result.scalar_one_or_none()


async def _ingest_representatives():
    client = EduskuntaClient()
    click.echo("Fetching representatives from eduskunta API...")
    reps = await client.fetch_representatives()
    click.echo(f"Fetched {len(reps)} representatives from API.")

    engine, async_session = await _get_session()

    async with async_session() as session:
        # Register source
        source = Source(
            source_type=SourceType.API,
            url="https://avoindata.eduskunta.fi/api/v1/tables/MemberOfParliament/rows",
            title="Eduskunta - Kansanedustajat",
            status=SourceStatus.INDEXED,
        )
        session.add(source)

        added = 0
        skipped = 0
        for rep_data in reps:
            person_id = rep_data.get("personId", "")
            first_name = rep_data.get("firstname", "")
            last_name = rep_data.get("lastname", "")

            if not first_name or not last_name:
                skipped += 1
                continue

            # Check if already exists
            result = await session.execute(
                select(Representative).where(
                    Representative.first_name == first_name,
                    Representative.last_name == last_name,
                )
            )
            if result.scalar_one_or_none():
                skipped += 1
                continue

            party = await _find_party(session, rep_data.get("party", ""))

            representative = Representative(
                first_name=first_name,
                last_name=last_name,
                party_id=party.id if party else None,
                social_media={"eduskunta_person_id": person_id},
            )
            session.add(representative)
            added += 1

        await session.commit()
        click.echo(f"Added {added} representatives, skipped {skipped}.")

    await engine.dispose()


async def _ingest_votes(max_pages: int | None = None):
    client = EduskuntaClient()
    click.echo("Fetching votes from eduskunta API...")
    votes = await client.fetch_votes(max_pages=max_pages)
    click.echo(f"Fetched {len(votes)} vote records from API.")

    engine, async_session = await _get_session()

    async with async_session() as session:
        source = Source(
            source_type=SourceType.API,
            url="https://avoindata.eduskunta.fi/api/v1/tables/SaliDBAanestysEdustaja/rows",
            title="Eduskunta - Äänestykset",
            status=SourceStatus.INDEXED,
        )
        session.add(source)

        added = 0
        skipped = 0
        for vote_data in votes:
            first_name = vote_data.get("EdustajaEtunimi", "")
            last_name = vote_data.get("EdustajaSukunimi", "")

            result = await session.execute(
                select(Representative).where(
                    Representative.first_name == first_name,
                    Representative.last_name == last_name,
                )
            )
            rep = result.scalar_one_or_none()
            if not rep:
                skipped += 1
                continue

            vote = Vote(
                representative_id=rep.id,
                session=vote_data.get("IstuntoVPVuosi", ""),
                subject=vote_data.get("AanestysId", ""),
                vote=_map_vote(vote_data.get("EdustajaAanestys", "Poissa")),
            )
            session.add(vote)
            added += 1

        await session.commit()
        click.echo(f"Added {added} votes, skipped {skipped}.")

    await engine.dispose()


@click.group()
def ingest():
    """Ingest data from various sources."""
    pass


@ingest.command()
def representatives():
    """Fetch and store representatives from eduskunta API."""
    asyncio.run(_ingest_representatives())


@ingest.command()
@click.option("--max-pages", default=None, type=int, help="Limit number of API pages to fetch.")
def votes(max_pages: int | None):
    """Fetch and store votes from eduskunta API."""
    asyncio.run(_ingest_votes(max_pages))
```

- [ ] **Step 4: Register ingest in CLI main**

Modify `src/vaalikone/cli/main.py`:

```python
import click

from vaalikone.cli.seed import seed
from vaalikone.cli.ingest import ingest


@click.group()
def cli():
    """Vaalikone — Suomen poliittisen datan työkalu."""
    pass


cli.add_command(seed)
cli.add_command(ingest)


if __name__ == "__main__":
    cli()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ingest_eduskunta.py tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 6: Test real ingestion**

```bash
# Seed parties first
vaalikone seed parties

# Ingest representatives
vaalikone ingest representatives

# Ingest a small batch of votes
vaalikone ingest votes --max-pages 2
```

Expected: Representatives and votes added to database.

- [ ] **Step 7: Commit**

```bash
git add src/vaalikone/cli/ tests/test_ingest_eduskunta.py
git commit -m "feat: CLI ingest commands for eduskunta representatives and votes"
```

---

## Task 9: Sources listing CLI

**Files:**
- Create: `src/vaalikone/cli/sources.py`
- Modify: `src/vaalikone/cli/main.py`
- Create: `tests/test_sources_cli.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_sources_cli.py`:

```python
from click.testing import CliRunner

from vaalikone.cli.main import cli


def test_sources_list_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["sources", "list", "--help"])
    assert result.exit_code == 0


def test_sources_stats_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["sources", "stats", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sources_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement sources CLI**

Create `src/vaalikone/cli/sources.py`:

```python
import asyncio

import click
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.core.config import get_settings
from vaalikone.models.party import Party
from vaalikone.models.source import Source


async def _list_sources(party_filter: str | None):
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        query = select(Source)
        if party_filter:
            query = (
                query.join(Party, Source.party_id == Party.id)
                .where(Party.abbreviation == party_filter.upper())
            )
        result = await session.execute(query)
        sources = result.scalars().all()

        if not sources:
            click.echo("No sources found.")
            return

        click.echo(f"{'ID':<38} {'Type':<14} {'Status':<10} {'Title'}")
        click.echo("-" * 100)
        for s in sources:
            click.echo(
                f"{str(s.id):<38} {s.source_type.value:<14} {s.status.value:<10} {s.title or s.url or '-'}"
            )
        click.echo(f"\nTotal: {len(sources)} sources")

    await engine.dispose()


async def _show_stats():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Source.source_type, Source.status, func.count(Source.id))
            .group_by(Source.source_type, Source.status)
        )
        rows = result.all()

        if not rows:
            click.echo("No sources in database.")
            return

        click.echo(f"{'Type':<14} {'Status':<10} {'Count'}")
        click.echo("-" * 40)
        total = 0
        for source_type, status, count in rows:
            click.echo(f"{source_type.value:<14} {status.value:<10} {count}")
            total += count
        click.echo(f"\nTotal: {total} sources")

    await engine.dispose()


@click.group()
def sources():
    """Manage and inspect data sources."""
    pass


@sources.command(name="list")
@click.option("--party", default=None, help="Filter by party abbreviation (e.g. SDP).")
def list_sources(party: str | None):
    """List all indexed sources."""
    asyncio.run(_list_sources(party))


@sources.command()
def stats():
    """Show source statistics."""
    asyncio.run(_show_stats())
```

- [ ] **Step 4: Register in CLI main**

Modify `src/vaalikone/cli/main.py`:

```python
import click

from vaalikone.cli.seed import seed
from vaalikone.cli.ingest import ingest
from vaalikone.cli.sources import sources


@click.group()
def cli():
    """Vaalikone — Suomen poliittisen datan työkalu."""
    pass


cli.add_command(seed)
cli.add_command(ingest)
cli.add_command(sources)


if __name__ == "__main__":
    cli()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_sources_cli.py -v`
Expected: PASS

- [ ] **Step 6: Test against real DB**

```bash
vaalikone sources list
vaalikone sources stats
```

Expected: Lists sources that were created during ingestion.

- [ ] **Step 7: Commit**

```bash
git add src/vaalikone/cli/sources.py src/vaalikone/cli/main.py tests/test_sources_cli.py
git commit -m "feat: CLI sources list and stats commands"
```

---

## Task 10: Minimal FastAPI app

**Files:**
- Create: `src/vaalikone/api/app.py`
- Create: `src/vaalikone/api/deps.py`
- Create: `src/vaalikone/api/routes/__init__.py`
- Create: `src/vaalikone/api/routes/parties.py`
- Create: `src/vaalikone/api/routes/representatives.py`
- Create: `src/vaalikone/api/routes/sources.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_api.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from vaalikone.api.app import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_list_parties(client):
    resp = await client.get("/api/v1/parties")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_representatives(client):
    resp = await client.get("/api/v1/representatives")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_sources(client):
    resp = await client.get("/api/v1/sources")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: Create deps.py**

Create `src/vaalikone/api/deps.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.core.database import create_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = create_session_factory()
    async with factory() as session:
        yield session
```

- [ ] **Step 4: Create party routes**

Create `src/vaalikone/api/routes/__init__.py` (empty file).

Create `src/vaalikone/api/routes/parties.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.party import Party

router = APIRouter(prefix="/api/v1/parties", tags=["parties"])


@router.get("/")
async def list_parties(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Party).order_by(Party.abbreviation))
    parties = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "abbreviation": p.abbreviation,
            "website": p.website,
            "ideology": p.ideology,
            "founded": p.founded,
        }
        for p in parties
    ]
```

- [ ] **Step 5: Create representative routes**

Create `src/vaalikone/api/routes/representatives.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.party import Party
from vaalikone.models.representative import Representative

router = APIRouter(prefix="/api/v1/representatives", tags=["representatives"])


@router.get("/")
async def list_representatives(
    party: str | None = Query(None, description="Filter by party abbreviation"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Representative)
    if party:
        query = query.join(Party).where(Party.abbreviation == party.upper())
    query = query.order_by(Representative.last_name)

    result = await db.execute(query)
    reps = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "first_name": r.first_name,
            "last_name": r.last_name,
            "party_id": str(r.party_id) if r.party_id else None,
            "constituency": r.constituency,
            "elected_year": r.elected_year,
        }
        for r in reps
    ]
```

- [ ] **Step 6: Create source routes**

Create `src/vaalikone/api/routes/sources.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaalikone.api.deps import get_db
from vaalikone.models.source import Source

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("/")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.fetched_at.desc().nulls_last()))
    sources = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "source_type": s.source_type.value,
            "url": s.url,
            "title": s.title,
            "status": s.status.value,
            "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
        }
        for s in sources
    ]


@router.get("/stats")
async def source_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Source.source_type, Source.status, func.count(Source.id))
        .group_by(Source.source_type, Source.status)
    )
    rows = result.all()
    return [
        {"source_type": st.value, "status": status.value, "count": count}
        for st, status, count in rows
    ]
```

- [ ] **Step 7: Create FastAPI app**

Create `src/vaalikone/api/app.py`:

```python
from fastapi import FastAPI

from vaalikone.api.routes.parties import router as parties_router
from vaalikone.api.routes.representatives import router as representatives_router
from vaalikone.api.routes.sources import router as sources_router

app = FastAPI(title="Vaalikone API", version="0.1.0")

app.include_router(parties_router)
app.include_router(representatives_router)
app.include_router(sources_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/vaalikone/api/ tests/test_api.py
git commit -m "feat: minimal FastAPI with parties, representatives, and sources endpoints"
```

---

## Task 11: End-to-end smoke test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write end-to-end test**

Create `tests/test_e2e.py`:

```python
"""
End-to-end smoke test: seed parties, verify via API.
Requires running PostgreSQL (docker compose up postgres).
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vaalikone.api.app import app
from vaalikone.models.party import Party


@pytest.fixture
async def seeded_db():
    """Seed a test party directly."""
    engine = create_async_engine(
        "postgresql+asyncpg://vaalikone:vaalikone@localhost:5435/vaalikone_test"
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        party = Party(name="E2E Testipuolue", abbreviation="E2E", website="https://e2e.fi")
        session.add(party)
        await session.commit()

    yield engine

    async with async_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(Party).where(Party.abbreviation == "E2E"))
        await session.commit()
    await engine.dispose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_full_flow(client):
    """Health check works and API returns lists."""
    health = await client.get("/health")
    assert health.status_code == 200

    parties = await client.get("/api/v1/parties")
    assert parties.status_code == 200
    assert isinstance(parties.json(), list)

    reps = await client.get("/api/v1/representatives")
    assert reps.status_code == 200

    sources = await client.get("/api/v1/sources")
    assert sources.status_code == 200
```

- [ ] **Step 2: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: end-to-end smoke test for full flow"
```

- [ ] **Step 4: Verify Docker build works**

```bash
docker compose build api
docker compose up -d
curl http://localhost:8003/health
curl http://localhost:8003/api/v1/parties
docker compose down
```

Expected: Health returns `{"status": "ok"}`, parties returns a list.

- [ ] **Step 5: Final commit — tag v0.1.0**

```bash
git tag v0.1.0
```
