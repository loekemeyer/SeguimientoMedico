"""Verifica que la versión sea única y quede expuesta para auditar el build."""
from fastapi.testclient import TestClient

from health_monitor import __version__
from health_monitor.main import app


def test_version_definida_y_semantica():
    assert isinstance(__version__, str)
    partes = __version__.split(".")
    assert len(partes) == 3 and all(p.isdigit() for p in partes)


def test_health_expone_la_version():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_app_usa_la_misma_version():
    assert app.version == __version__
