"""Tests del panel BI del dueño: gating por OWNER_EMAIL y agregados."""
import base64
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bi.db"
os.environ["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()
os.environ["JWT_SECRET"] = "test-secret"
os.environ["OWNER_EMAIL"] = "dueno@test.com"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shared.config import get_settings  # noqa: E402

get_settings.cache_clear()

from health_monitor.db.session import create_all  # noqa: E402
from health_monitor.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _db():
    import health_monitor.db.session as sess
    os.environ["DATABASE_URL"] = "sqlite:///./test_bi.db"
    os.environ["OWNER_EMAIL"] = "dueno@test.com"
    get_settings.cache_clear()
    sess._engine = None
    sess._SessionLocal = None
    if os.path.exists("test_bi.db"):
        os.remove("test_bi.db")
    create_all()
    yield
    if os.path.exists("test_bi.db"):
        os.remove("test_bi.db")
    sess._engine = None
    sess._SessionLocal = None
    get_settings.cache_clear()


def _auth(email: str, pw: str = "secret123") -> dict:
    r = client.post("/auth/register", json={"email": email, "password": pw, "nombre": "T"})
    if r.status_code not in (200, 201):
        r = client.post("/auth/login", json={"email": email, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_bi_niega_a_no_dueno():
    h = _auth("cliente@test.com")
    assert client.get("/bi/resumen", headers=h).status_code == 403
    assert client.get("/bi/clientes", headers=h).status_code == 403


def test_bi_resumen_para_dueno():
    h = _auth("dueno@test.com")
    r = client.get("/bi/resumen", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("ingreso_mensual_ars", "costo_periodo_ars", "margen_ars", "clientes_total"):
        assert k in j
    assert j["clientes_total"] >= 1


def test_bi_clientes_es_lista_ordenada():
    h = _auth("dueno@test.com")
    r = client.get("/bi/clientes", headers=h)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert isinstance(filas, list)
    # ordenado por margen ascendente (lo que da pérdida primero)
    margenes = [f["margen_ars"] for f in filas]
    assert margenes == sorted(margenes)


def test_bi_asesor_devuelve_recomendaciones():
    h = _auth("dueno@test.com")
    r = client.get("/bi/asesor", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert isinstance(j["recomendaciones"], list) and len(j["recomendaciones"]) >= 1
    assert "configurado" in j


def test_bi_asesor_niega_a_no_dueno():
    h = _auth("cliente2@test.com")
    assert client.get("/bi/asesor", headers=h).status_code == 403


def test_bi_sin_owner_email_niega_a_todos(monkeypatch):
    # Si OWNER_EMAIL no está configurado, el panel se cierra (seguro por defecto).
    monkeypatch.setenv("OWNER_EMAIL", "")
    get_settings.cache_clear()
    h = _auth("dueno@test.com")
    assert client.get("/bi/resumen", headers=h).status_code == 403
    monkeypatch.setenv("OWNER_EMAIL", "dueno@test.com")
    get_settings.cache_clear()
