"""Tests del módulo Acompañante: clave rotativa de 2 dígitos + login del paciente."""
import base64
import os

# Entorno de test: SQLite y claves propias, ANTES de importar la app.
os.environ["DATABASE_URL"] = "sqlite:///./test_acompanante.db"
os.environ["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()
os.environ["JWT_SECRET"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from shared.config import get_settings  # noqa: E402

get_settings.cache_clear()

from health_monitor.acompanante import (  # noqa: E402
    VENTANA_SEG,
    clave_rotativa,
    clave_valida,
    segundos_restantes,
)
from health_monitor.db.session import create_all  # noqa: E402
from health_monitor.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _db():
    import health_monitor.db.session as sess
    os.environ["DATABASE_URL"] = "sqlite:///./test_acompanante.db"
    get_settings.cache_clear()
    sess._engine = None
    sess._SessionLocal = None
    if os.path.exists("test_acompanante.db"):
        os.remove("test_acompanante.db")
    create_all()
    yield
    if os.path.exists("test_acompanante.db"):
        os.remove("test_acompanante.db")


# --- Clave rotativa (funciones puras) ---

def test_clave_rotativa_2_digitos_y_deterministica():
    t = 1_700_000_010.0  # comienzo de ventana (t % 30 == 0)
    assert t % VENTANA_SEG == 0
    c1 = clave_rotativa("123456", ahora=t)
    assert len(c1) == 2 and c1.isdigit()
    assert clave_rotativa("123456", ahora=t + 5) == c1           # misma ventana
    t2 = t + VENTANA_SEG                                          # ventana siguiente
    c2 = clave_rotativa("123456", ahora=t2)
    assert clave_valida("123456", c2, ahora=t2)                  # la actual siempre vale
    # tolerancia de borde: la clave anterior sólo vale los primeros segundos
    assert clave_valida("123456", c1, ahora=t2 + 2)              # dentro de la gracia
    assert not clave_valida("123456", c1, ahora=t2 + 10)         # fuera de la gracia


def test_clave_valida_rechaza_incorrectas():
    t = 1_700_000_000.0
    assert not clave_valida("123456", "", ahora=t)
    assert not clave_valida("123456", "zz", ahora=t)
    assert clave_valida("123456", clave_rotativa("123456", ahora=t), ahora=t)


def test_segundos_restantes_en_rango():
    assert 1 <= segundos_restantes(ahora=1_700_000_000.0) <= VENTANA_SEG


# --- Flujo completo: familiar crea paciente; paciente entra con código + clave ---

_n = 0


def _crear_paciente_y_codigo():
    global _n
    _n += 1
    r = client.post("/auth/register", json={
        "email": f"fam{_n}@acomp.com", "password": "secret123", "nombre": "Fam"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    p = client.post("/pacientes", headers=headers, json={
        "nombre": "Rosa", "telefono_whatsapp": "+5491100000000", "consentimiento_firmado": True})
    assert p.status_code == 201, p.text
    return headers, p.json()["id"], p.json()["codigo_acceso"]


def test_login_paciente_con_codigo_y_clave():
    headers, pid, codigo = _crear_paciente_y_codigo()

    rc = client.get(f"/pacientes/{pid}/codigo-rotativo", headers=headers)
    assert rc.status_code == 200
    clave = rc.json()["clave"]
    assert len(clave) == 2 and 1 <= rc.json()["segundos"] <= VENTANA_SEG

    login = client.post("/acompanante/login", json={"codigo_acceso": codigo, "clave": clave})
    assert login.status_code == 200, login.text
    assert login.json()["nombre"] == "Rosa"
    token = login.json()["token"]

    me = client.get("/acompanante/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["nombre"] == "Rosa"

    # clave imposible (no numérica) => 401; código inexistente => 401
    assert client.post("/acompanante/login",
                       json={"codigo_acceso": codigo, "clave": "zz"}).status_code == 401
    assert client.post("/acompanante/login",
                       json={"codigo_acceso": "000000", "clave": clave}).status_code == 401


def test_token_paciente_no_sirve_para_seccion_del_familiar():
    headers, pid, codigo = _crear_paciente_y_codigo()
    clave = client.get(f"/pacientes/{pid}/codigo-rotativo", headers=headers).json()["clave"]
    token = client.post("/acompanante/login",
                        json={"codigo_acceso": codigo, "clave": clave}).json()["token"]
    # el token del paciente NO debe servir para la sección del familiar
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_chat_gateado_por_suscripcion_de_la_familia():
    headers, pid, codigo = _crear_paciente_y_codigo()
    clave = client.get(f"/pacientes/{pid}/codigo-rotativo", headers=headers).json()["clave"]
    token = client.post("/acompanante/login",
                        json={"codigo_acceso": codigo, "clave": clave}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    # Apertura (mensaje vacío) siempre gratis.
    assert client.post("/acompanante/chat", headers=h, json={"mensaje": "", "historial": []}).status_code == 200

    # Con el trial vigente, un mensaje real NO cae en el gate de pago.
    r1 = client.post("/acompanante/chat", headers=h, json={"mensaje": "hola", "historial": []})
    assert r1.status_code == 200
    assert "avisale a tu familia" not in r1.json()["respuesta"]

    # Cancelamos la suscripción de la familia: el mensaje real queda gateado (sin gastar API).
    import health_monitor.db.session as sess
    from health_monitor.db.models import Paciente, Usuario
    s = sess._SessionLocal()
    u = s.get(Usuario, s.get(Paciente, pid).usuario_id)
    u.plan = "cancelado"
    s.commit()
    s.close()

    r2 = client.post("/acompanante/chat", headers=h, json={"mensaje": "hola", "historial": []})
    assert r2.status_code == 200
    assert r2.json()["configurado"] is False
    assert "avisale a tu familia" in r2.json()["respuesta"]


def test_login_paciente_rate_limited():
    from health_monitor.ratelimit import reset
    reset()
    _, _, codigo = _crear_paciente_y_codigo()
    # 5 intentos con clave mala permitidos; el 6º debe ser 429 (no 401).
    codes = [client.post("/acompanante/login",
                         json={"codigo_acceso": codigo, "clave": "99"}).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
    reset()
