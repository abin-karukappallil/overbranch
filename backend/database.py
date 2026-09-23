"""
backend/database.py — Asynchronous Database Engine & Session Management for OverBranch
======================================================================================
Provides an asynchronous SQLAlchemy connection pool to the shared PostgreSQL database
(used by Next.js Drizzle ORM and Better Auth).
"""

from __future__ import annotations

import os
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# Load environment variables (from backend/ or workspace root)
load_dotenv(override=False)
workspace_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(workspace_env):
    load_dotenv(workspace_env, override=False)

logger = logging.getLogger("database")

Base = declarative_base()

_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def format_async_database_url(url: str) -> tuple[str, dict]:
    """
    Normalizes PostgreSQL URL for asyncpg:
    - Replaces postgresql:// or postgres:// with postgresql+asyncpg://
    - Normalizes sslmode parameter for asyncpg compatibility
    - Returns (normalized_url, connect_args)
    """
    connect_args: dict = {
        # Supabase connection pooler (pgbouncer) requires statement_cache_size=0
        "statement_cache_size": 0,
    }

    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # asyncpg expects ssl parameter in connect_args or query rather than sslmode=require
    if "sslmode" in query_params:
        mode = query_params.pop("sslmode")[0]
        if mode in ("require", "verify-ca", "verify-full"):
            connect_args["ssl"] = True

    new_query = urlencode(query_params, doseq=True)
    clean_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))

    return clean_url, connect_args


def get_engine() -> AsyncEngine:
    """Returns the singleton AsyncEngine instance."""
    global _async_engine
    if _async_engine is None:
        raw_url = os.getenv("DATABASE_URL")
        if not raw_url:
            raise RuntimeError(
                "DATABASE_URL is not set in environment. "
                "Please configure DATABASE_URL to connect to PostgreSQL."
            )

        async_url, connect_args = format_async_database_url(raw_url)

        pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "300"))

        _async_engine = create_async_engine(
            async_url,
            connect_args=connect_args,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
            echo=os.getenv("SQL_ECHO", "false").lower() in ("true", "1", "yes"),
        )
        logger.info("Initialized async SQLAlchemy database engine")

    return _async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Returns the singleton async sessionmaker."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an asynchronous SQLAlchemy database session.
    Automatically handles commit/rollback and ensures session cleanup.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """Closes and disposes the database engine pool during application shutdown."""
    global _async_engine, _async_session_factory
    if _async_engine is not None:
        logger.info("Disposing async database engine pool...")
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
        logger.info("Database engine pool disposed.")
