"""Engine y sesiones de SQLAlchemy hacia PostgreSQL."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from health_monitor.db.models import Base
from shared.config import get_settings

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _init() -> None:
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        # Algunos hosts (ej. Render) entregan la URL como postgres://; SQLAlchemy 2.0
        # exige el esquema postgresql://.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        # SQLite con FastAPI corre los endpoints en varios hilos: hay que permitir
        # usar la conexión entre hilos. En PostgreSQL no aplica.
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def create_all() -> None:
    """Crea las tablas si no existen (útil en desarrollo; en prod usar migraciones)."""
    _init()
    Base.metadata.create_all(_engine)


def recreate_all() -> None:
    """Borra y recrea todas las tablas (para demos / entornos descartables)."""
    _init()
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)


def get_session() -> Iterator[Session]:
    """Dependencia FastAPI que entrega una sesión y la cierra al terminar."""
    _init()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
