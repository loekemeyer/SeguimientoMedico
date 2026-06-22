"""Tests de la API SaaS: autenticación y CRUD multi-usuario con aislamiento."""
import base64
import os

# Entorno de test: SQLite y claves propias, ANTES de importar la app.
os.environ["DATABASE_URL"] = "sqlite:///./test_api.db"
os.environ["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()
os.environ["JWT_SECRET"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shared.config import get_settings  # noqa: E402

get_settings.cache_clear()  # descarta config cacheada por otros tests

from health_monitor.db.session import create_all  # noqa: E402
from health_monitor.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _db():
    if os.path.exists("test_api.db"):
        os.remove("test_api.db")
    create_all()
    yield
    if os.path.exists("test_api.db"):
        os.remove("test_api.db")


def _register(email: str, password: str = "secret123") -> dict:
    r = client.post("/auth/register", json={"email": email, "password": password, "nombre": "T"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_registro_login_y_me():
    headers = _register("user1@test.com")
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "user1@test.com"
    assert me.json()["plan"] == "trial"

    login = client.post("/auth/login", json={"email": "user1@test.com", "password": "secret123"})
    assert login.status_code == 200
    assert login.json()["access_token"]


def test_email_duplicado_rechazado():
    _register("dup@test.com")
    r = client.post("/auth/register", json={"email": "dup@test.com", "password": "secret123"})
    assert r.status_code == 409


def test_login_incorrecto():
    _register("user2@test.com")
    r = client.post("/auth/login", json={"email": "user2@test.com", "password": "malisima"})
    assert r.status_code == 401


def test_sin_token_no_autorizado():
    assert client.get("/pacientes").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_crear_y_leer_paciente():
    headers = _register("caregiver@test.com")
    payload = {
        "nombre": "Alejandro Damián Loekemeyer",
        "telefono_whatsapp": "+5491131181594",
        "consentimiento_firmado": True,
        "patologias": ["I10"],
        "limites": {"sistolica_max": 140},
    }
    r = client.post("/pacientes", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["nombre"] == "Alejandro Damián Loekemeyer"

    got = client.get(f"/pacientes/{pid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["telefono_whatsapp"] == "+5491131181594"
    assert got.json()["patologias"] == ["I10"]


def test_aislamiento_entre_usuarios():
    h1 = _register("owner@test.com")
    h2 = _register("intruso@test.com")
    pid = client.post("/pacientes", json={
        "nombre": "Paciente Privado", "telefono_whatsapp": "+5490000000000",
    }, headers=h1).json()["id"]

    # El otro usuario no puede verlo.
    assert client.get(f"/pacientes/{pid}", headers=h2).status_code == 404
    # Y no aparece en su listado.
    assert client.get("/pacientes", headers=h2).json() == []


def test_medicacion_y_contactos():
    headers = _register("full@test.com")
    pid = client.post("/pacientes", json={
        "nombre": "Con Datos", "telefono_whatsapp": "+5491131181594",
    }, headers=headers).json()["id"]

    med = client.post(f"/pacientes/{pid}/medicacion",
                      json={"nombre": "Losartán 50mg", "frecuencia": "1 por día"}, headers=headers)
    assert med.status_code == 201
    assert client.get(f"/pacientes/{pid}/medicacion", headers=headers).json()[0]["nombre"] == "Losartán 50mg"

    con = client.post(f"/pacientes/{pid}/contactos",
                      json={"nombre": "Thomas", "telefono": "+5491162521635", "relacion": "hijo"},
                      headers=headers)
    assert con.status_code == 201
    contactos = client.get(f"/pacientes/{pid}/contactos", headers=headers).json()
    assert contactos[0]["telefono"] == "+5491162521635"
    assert contactos[0]["relacion"] == "hijo"
