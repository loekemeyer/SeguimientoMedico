"""Test de la reconciliación de esquema (puente hasta Alembic).

Simula una base 'vieja' a la que le falta una columna nueva del modelo y verifica
que apply_safe_migrations la agrega sin romper, de forma idempotente.
"""
from sqlalchemy import create_engine, inspect, text

from health_monitor.db.migrate import apply_safe_migrations


def test_agrega_columna_faltante(tmp_path):
    url = f"sqlite:///{tmp_path}/old.db"
    eng = create_engine(url)
    # Tabla 'usuarios' vieja: SIN la columna plan_tipo (que el modelo sí define).
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE usuarios ("
            "id INTEGER PRIMARY KEY, email VARCHAR(255), password_hash TEXT, "
            "nombre VARCHAR(120), tipo_cuenta VARCHAR(16), obra_social VARCHAR(120), "
            "nro_afiliado_enc TEXT, afiliacion_validada BOOLEAN, plan VARCHAR(32), "
            "suscripcion_vence TIMESTAMP, activo BOOLEAN, created_at TIMESTAMP)"
        ))
        c.execute(text("INSERT INTO usuarios (id, email, plan) VALUES (1, 'a@b.com', 'trial')"))

    cols_antes = {col["name"] for col in inspect(eng).get_columns("usuarios")}
    assert "plan_tipo" not in cols_antes

    apply_safe_migrations(eng)

    cols_despues = {col["name"] for col in inspect(eng).get_columns("usuarios")}
    assert "plan_tipo" in cols_despues  # se agregó

    # la fila vieja sigue ahí
    with eng.begin() as c:
        assert c.execute(text("SELECT email FROM usuarios WHERE id=1")).scalar() == "a@b.com"

    # idempotente: correr de nuevo no rompe
    apply_safe_migrations(eng)
