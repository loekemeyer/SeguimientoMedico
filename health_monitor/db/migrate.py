"""Reconciliación liviana de esquema (sin Alembic todavía).

``create_all`` crea las tablas que faltan, pero NO agrega columnas ni índices a
tablas que ya existen. En una base de producción que se creó con un esquema más
viejo, eso deja columnas nuevas (p. ej. ``usuarios.plan_tipo``) ausentes y
cualquier consulta sobre esa tabla revienta.

Esta función compara el modelo ORM con la base real y agrega, de forma idempotente
y defensiva, las columnas e índices que falten. Es un puente hasta adoptar Alembic
(ver docs/ARQUITECTURA_ESCALA.md §3.1); por eso es conservadora: sólo AGREGA, nunca
borra ni altera tipos.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def _literal_default(arg) -> str | None:
    """Representa un default simple como literal SQL; None si no es trivial."""
    if callable(arg):
        return None
    if isinstance(arg, bool):
        return "true" if arg else "false"
    if isinstance(arg, (int, float)):
        return str(arg)
    if isinstance(arg, str):
        return "'" + arg.replace("'", "''") + "'"
    return None


def apply_safe_migrations(engine) -> None:
    """Agrega columnas e índices que el modelo define pero la base no tiene."""
    from health_monitor.db.models import Base

    try:
        insp = inspect(engine)
        existing = set(insp.get_table_names())
    except Exception as exc:
        logger.warning("No se pudo inspeccionar la base para migrar: %s", exc)
        return

    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # create_all ya la crea entera (con sus columnas e índices)

        # --- columnas faltantes ---
        try:
            db_cols = {c["name"] for c in insp.get_columns(table.name)}
        except Exception:
            continue
        for col in table.columns:
            if col.name in db_cols:
                continue
            try:
                coltype = col.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}'
                default = getattr(col.default, "arg", None) if col.default is not None else None
                lit = _literal_default(default) if default is not None else None
                if lit is not None:
                    ddl += f" DEFAULT {lit}"
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                logger.warning("Migración: columna agregada %s.%s", table.name, col.name)
            except Exception as exc:
                logger.error("Migración: no se pudo agregar %s.%s: %s", table.name, col.name, exc)

        # --- índices faltantes ---
        try:
            db_idx = {i["name"] for i in insp.get_indexes(table.name)}
        except Exception:
            db_idx = set()
        for idx in table.indexes:
            if idx.name in db_idx:
                continue
            try:
                idx.create(bind=engine)
                logger.warning("Migración: índice creado %s", idx.name)
            except Exception as exc:
                logger.error("Migración: no se pudo crear índice %s: %s", idx.name, exc)
