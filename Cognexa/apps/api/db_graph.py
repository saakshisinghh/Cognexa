"""
apps/api/db_graph.py

Purpose
-------
Neo4j driver singleton + session/context helpers for the Knowledge Graph
module introduced in Phase 3. Mirrors the existing db.py (Postgres) and
weaviate_client.py (vector) patterns used in Phase 1/2 so the codebase
stays architecturally consistent.

Dependencies
------------
- neo4j (official Python driver) — add to pyproject.toml: neo4j = "^5.22.0"
- apps/api/config.py (Settings — NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD)

This file is NEW. It does not modify any Phase 1/2 file's behavior.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from neo4j import Driver, GraphDatabase, Session
from neo4j.exceptions import ServiceUnavailable, AuthError

from apps.api.config import settings

logger = logging.getLogger("indusmind.graph.driver")

_driver: Optional[Driver] = None


def get_neo4j_driver() -> Driver:
    """
    Returns a process-wide singleton Neo4j driver.
    Connection pooling is handled internally by the driver itself
    (max_connection_pool_size defaults to 100, which is fine for a monolith).
    """
    global _driver
    if _driver is None:
        logger.info("Initializing Neo4j driver at %s", settings.NEO4J_URI)
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            max_connection_lifetime=3600,
            max_connection_pool_size=100,
            connection_acquisition_timeout=30,
        )
    return _driver


def close_neo4j_driver() -> None:
    """Call from FastAPI shutdown event in main.py (one-line addition)."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")


@contextmanager
def neo4j_session(database: Optional[str] = None) -> Generator[Session, None, None]:
    """
    Context-managed Neo4j session for use in repository methods.

    Usage:
        with neo4j_session() as session:
            session.run("MATCH (a:Asset) RETURN a LIMIT 1")
    """
    driver = get_neo4j_driver()
    session = driver.session(database=database or settings.NEO4J_DATABASE)
    try:
        yield session
    finally:
        session.close()


def check_neo4j_health() -> dict:
    """
    Used by GET /api/v1/graph/health.
    Returns a structured dict instead of raising, so the router can decide
    the HTTP status code (200 vs 503) based on `connected`.
    """
    try:
        with neo4j_session() as session:
            result = session.run("RETURN 1 AS ok")
            record = result.single()
            ok = record is not None and record["ok"] == 1
            return {"connected": ok, "database": settings.NEO4J_DATABASE, "error": None}
    except AuthError as exc:
        logger.error("Neo4j auth error: %s", exc)
        return {"connected": False, "database": settings.NEO4J_DATABASE, "error": "authentication_failed"}
    except ServiceUnavailable as exc:
        logger.error("Neo4j unavailable: %s", exc)
        return {"connected": False, "database": settings.NEO4J_DATABASE, "error": "service_unavailable"}
    except Exception as exc:  # noqa: BLE001 — health check must never raise
        logger.exception("Unexpected Neo4j health check failure")
        return {"connected": False, "database": settings.NEO4J_DATABASE, "error": str(exc)}
