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


def test_registro_privado_por_default():
    headers = _register("priv@test.com")
    me = client.get("/auth/me", headers=headers).json()
    assert me["tipo_cuenta"] == "privado"


def test_registro_por_obra_social_valida_y_se_vincula():
    r = client.post("/auth/register", json={
        "email": "afiliado@test.com", "password": "secret123", "nombre": "Afi",
        "tipo_cuenta": "obra_social", "obra_social": "OSDE", "nro_afiliado": "123456789",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get("/auth/me", headers=headers).json()
    assert me["tipo_cuenta"] == "obra_social"
    assert me["obra_social"] == "OSDE"
    assert me["afiliacion_validada"] is True


def test_obra_social_sin_numero_no_valida():
    r = client.post("/auth/register", json={
        "email": "sinnro@test.com", "password": "secret123",
        "tipo_cuenta": "obra_social", "obra_social": "Swiss Medical", "nro_afiliado": "12",
    })
    assert r.status_code == 201
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/me", headers=headers).json()["afiliacion_validada"] is False


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


def test_programacion_dias_y_pausa_se_guardan():
    headers = _register("prog@test.com")
    pid = client.post("/pacientes", json={
        "nombre": "Prog", "telefono_whatsapp": "+5490000000055",
    }, headers=headers).json()["id"]
    body = {
        "nombre": "Prog", "telefono_whatsapp": "+5490000000055",
        "programacion": {"llamada_activa": False, "llamada_dias": [0, 2, 4], "llamada_hora": "09:00"},
    }
    r = client.put(f"/pacientes/{pid}", json=body, headers=headers)
    assert r.status_code == 200, r.text
    prog = r.json()["programacion"]
    assert prog["llamada_activa"] is False
    assert prog["llamada_dias"] == [0, 2, 4]
    assert prog["llamada_hora"] == "09:00"


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

    # Se puede quitar el contacto (gestión completa de la lista de avisos).
    cid = contactos[0]["id"]
    assert client.delete(f"/pacientes/{pid}/contactos/{cid}", headers=headers).status_code == 204
    assert client.get(f"/pacientes/{pid}/contactos", headers=headers).json() == []
    # Un tercero no puede borrar contactos de este paciente.
    otro = _register("contacto_intruso@test.com")
    assert client.delete(f"/pacientes/{pid}/contactos/999", headers=otro).status_code == 404


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


def test_auditoria_registra_alta_y_edicion():
    headers = _register("audit@test.com")
    payload = {"nombre": "Audit", "telefono_whatsapp": "+5490000000088"}
    pid = client.post("/pacientes", json=payload, headers=headers).json()["id"]
    # Editar (mismo payload alcanza para generar el evento).
    client.put(f"/pacientes/{pid}", json=payload, headers=headers)

    auditoria = client.get(f"/pacientes/{pid}/auditoria", headers=headers)
    assert auditoria.status_code == 200
    acciones = [a["accion"] for a in auditoria.json()]
    assert "crear" in acciones
    assert "actualizar" in acciones
    # El detalle no debe filtrar PII (solo descripciones).
    assert all("Audit" not in a["detalle"] for a in auditoria.json())

    # Otro usuario no ve la auditoría de este paciente.
    intruso = _register("audit_intruso@test.com")
    assert client.get(f"/pacientes/{pid}/auditoria", headers=intruso).status_code == 404


def test_fhir_export_de_la_ultima_evolucion():
    from health_monitor.db.models import EvolucionDiaria
    from health_monitor.db.session import get_session

    headers = _register("fhir@test.com")
    pid = client.post("/pacientes", json={
        "nombre": "FHIR", "telefono_whatsapp": "+5490000000077",
    }, headers=headers).json()["id"]

    # Sin evoluciones todavía: 404.
    assert client.get(f"/pacientes/{pid}/fhir", headers=headers).status_code == 404

    # Insertamos una evolución (la crea el sistema, no la API) con métricas.
    db = next(get_session())
    try:
        db.add(EvolucionDiaria(
            paciente_id=pid, nivel_alerta="AMARILLA",
            readout={"paciente_id": pid, "presion_sistolica": 140,
                     "presion_diastolica": 90, "peso": 80.0},
        ))
        db.commit()
    finally:
        db.close()

    r = client.get(f"/pacientes/{pid}/fhir", headers=headers)
    assert r.status_code == 200, r.text
    bundle = r.json()
    assert bundle["resourceType"] == "Bundle"
    codes = {c["code"] for e in bundle["entry"] for c in e["resource"]["code"]["coding"]}
    assert "85354-9" in codes  # panel de presión
    assert "29463-7" in codes  # peso

    # Otro usuario no puede exportar este paciente.
    intruso = _register("fhir_intruso@test.com")
    assert client.get(f"/pacientes/{pid}/fhir", headers=intruso).status_code == 404


def test_trace_id_en_la_respuesta():
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")  # se genera uno por request
    # Si el cliente manda su propio id, se respeta (correlación end-to-end).
    r2 = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r2.headers.get("X-Request-ID") == "trace-abc-123"


def test_twilio_voice_no_lo_tapa_el_frontend():
    """Regresión: el frontend montado en '/' no debe tapar los endpoints de la API.

    Si el StaticFiles se monta antes que /twilio/voice, el POST de Twilio rebota
    con 405 Method Not Allowed (el frontend solo acepta GET). Debe responder el
    TwiML (200) con el <Stream>.
    """
    r = client.post("/twilio/voice?paciente_id=1")
    assert r.status_code == 200, f"esperaba 200 con el TwiML, vino {r.status_code}"
    assert "<Stream" in r.text and "media-stream" in r.text


def test_sugerencias_y_notificaciones_se_listan():
    headers = _register("panel@test.com")
    pid = client.post("/pacientes", json={
        "nombre": "Panel", "telefono_whatsapp": "+5490000000066",
    }, headers=headers).json()["id"]
    s = client.get(f"/pacientes/{pid}/sugerencias", headers=headers)
    assert s.status_code == 200 and isinstance(s.json(), list)
    n = client.get(f"/pacientes/{pid}/notificaciones", headers=headers)
    assert n.status_code == 200 and n.json() == []


def test_pwa_manifest_y_service_worker_se_sirven():
    """La PWA necesita que el manifest y el service worker se sirvan en la raíz."""
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200, "el manifest debe servirse para que la app sea instalable"
    assert '"icons"' in m.text and "standalone" in m.text
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "addEventListener" in sw.text  # es un service worker de verdad


def test_whatsapp_incoming_sin_conversacion_responde_204():
    """El webhook de WhatsApp responde 204 si no hay conversación activa (ruta viva)."""
    r = client.post(
        "/whatsapp/incoming",
        data={"From": "whatsapp:+5490000000099", "Body": "hola"},
    )
    assert r.status_code == 204
