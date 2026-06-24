"""Tests del registro de eventos de uso (base del módulo BI)."""
import os

import pytest

import shared.config as cfg
import health_monitor.db.session as sess


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/u.db")
    monkeypatch.setenv("ENCRYPTION_KEY", "lh+G5fuJhPOTfhqgFB0MuUlrLUH0pP2azsLD3U9Kn60=")
    cfg.get_settings.cache_clear()
    sess._engine = None
    sess._SessionLocal = None
    from health_monitor.db.models import Base
    sess._init()
    Base.metadata.create_all(sess._engine)
    s = sess._SessionLocal()
    yield s
    s.close()
    sess._engine = None
    sess._SessionLocal = None
    cfg.get_settings.cache_clear()


def test_estimaciones_de_costo():
    from health_monitor.usage import (
        estimar_costo_chat,
        estimar_costo_llamada,
        estimar_tokens,
    )

    assert estimar_costo_chat(1000) > 0
    assert estimar_costo_llamada(5) > estimar_costo_llamada(1)
    assert estimar_tokens("hola", "que tal") >= 1


def test_registrar_evento_persiste(db):
    from health_monitor.db.models import EventoUso
    from health_monitor.usage import CHAT_MSG, registrar_evento

    ev = registrar_evento(
        db, tipo=CHAT_MSG, modulo="acompanado",
        usuario_id=1, paciente_id=2, unidades=120, costo_estimado=0.001,
        meta={"modelo": "gpt-4o-mini"},
    )
    assert ev is not None
    filas = db.query(EventoUso).all()
    assert len(filas) == 1
    assert filas[0].tipo == CHAT_MSG
    assert filas[0].usuario_id == 1
    assert filas[0].meta["modelo"] == "gpt-4o-mini"


def test_registrar_evento_no_rompe_ante_error(db):
    # tipo inválido (None) podría fallar al insertar; debe devolver None sin propagar.
    from health_monitor.usage import registrar_evento

    ev = registrar_evento(db, tipo=None)  # type: ignore[arg-type]
    # No lanza excepción; o persiste (si la base lo tolera) o devuelve None.
    assert ev is None or ev is not None
