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
    assert got.json()["programacion"]["nivel_insistencia"] == 2  # default


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


def test_rutina_y_contactos():
    headers = _register("full@test.com")
    pid = client.post("/pacientes", json={
        "nombre": "Con Datos", "telefono_whatsapp": "+5491131181594",
    }, headers=headers).json()["id"]

    item = client.post(f"/pacientes/{pid}/rutina",
                       json={"tipo": "medicamento", "nombre": "Losartán 50mg",
                             "frecuencia": "1 vez al día", "horario": "08:00", "dias": [0, 2, 4]},
                       headers=headers)
    assert item.status_code == 201
    rutina = client.get(f"/pacientes/{pid}/rutina", headers=headers).json()
    assert rutina[0]["nombre"] == "Losartán 50mg"
    assert rutina[0]["tipo"] == "medicamento"
    assert rutina[0]["dias"] == [0, 2, 4]
    assert rutina[0]["aviso"] == "mensaje"  # default (WhatsApp)

    con = client.post(f"/pacientes/{pid}/contactos",
                      json={"nombre": "Thomas", "telefono": "+5491162521635", "relacion": "hijo"},
                      headers=headers)
    assert con.status_code == 201
    contactos = client.get(f"/pacientes/{pid}/contactos", headers=headers).json()
    assert contactos[0]["telefono"] == "+5491162521635"
    assert contactos[0]["relacion"] == "hijo"


def test_suscripcion_vencida_bloquea_escritura_pero_permite_lectura():
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from health_monitor.db.models import Usuario
    from health_monitor.db.session import get_session

    headers = _register("vencido@test.com")

    # Vencer la suscripción del usuario directamente en la base.
    db = next(get_session())
    try:
        u = db.scalar(select(Usuario).where(Usuario.email == "vencido@test.com"))
        u.suscripcion_vence = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    # La lectura sigue permitida (puede ver sus datos y renovar).
    assert client.get("/pacientes", headers=headers).status_code == 200
    # La escritura se bloquea con 402 Payment Required.
    r = client.post(
        "/pacientes",
        json={"nombre": "X", "telefono_whatsapp": "+5490000000001"},
        headers=headers,
    )
    assert r.status_code == 402, r.text


def test_twilio_voice_no_lo_tapa_el_frontend():
    """Regresión: el frontend montado en '/' no debe tapar los endpoints de la API.

    Si el StaticFiles se monta antes que /twilio/voice, el POST de Twilio rebota
    con 405 Method Not Allowed (el frontend solo acepta GET). Debe responder el
    TwiML (200) con el <Stream>.
    """
    r = client.post("/twilio/voice?paciente_id=1")
    assert r.status_code == 200, f"esperaba 200 con el TwiML, vino {r.status_code}"
    assert "<Stream" in r.text and "media-stream" in r.text


def test_whatsapp_incoming_sin_conversacion_responde_204():
    """El webhook de WhatsApp responde 204 si no hay conversación activa (ruta viva)."""
    r = client.post(
        "/whatsapp/incoming",
        data={"From": "whatsapp:+5490000000099", "Body": "hola"},
    )
    assert r.status_code == 204
