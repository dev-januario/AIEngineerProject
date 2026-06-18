"""
Test Fixtures & Configuration
==============================
Setup do ambiente de testes com SQLite assíncrono (sem necessidade de PostgreSQL).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# SQLite em memória para testes (sem dependência de PostgreSQL)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

TestAsyncSession = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Cria todas as tabelas antes dos testes e destrói depois."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session():
    """Sessão de banco de dados isolada por teste (rollback automático)."""
    async with TestAsyncSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Cliente HTTP assíncrono com banco de dados de teste injetado."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def sample_lead_payload():
    return {
        "name": "Carlos Mendes",
        "email": "carlos.mendes@techcorp.com.br",
        "phone": "+5511991234567",
        "company": "TechCorp Brasil",
        "role": "CISO",
        "company_size": "500-1000",
        "sector": "Financeiro",
        "linkedin_url": "https://linkedin.com/in/carlos-mendes",
        "lgpd_consent": True,
    }


@pytest.fixture
def sample_lead_payload_no_consent():
    return {
        "name": "Ana Lima",
        "email": "ana.lima@empresa.com",
        "lgpd_consent": False,
    }
