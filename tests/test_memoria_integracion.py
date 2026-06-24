"""Integración: al cerrar una llamada, persist_evolucion actualiza la memoria."""
import base64
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_memoria_int.db"
os.environ["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()
os.environ["JWT_SECRET"] = "test-secret"
os.environ["OPENAI_API_KEY"] = ""  # fuerza el fallback determinístico

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
    os.environ["DATABASE_URL"] = "sqlite:///./test_memoria_int.db"
    get_settings.cache_clear()
    sess._engine = None
    sess._SessionLocal = None
    if os.path.exists("test_memoria_int.db"):
        os.remove("test_memoria_int.db")
    create_all()
    yield
    if os.path.exists("test_memoria_int.db"):
        os.remove("test_memoria_int.db")
    sess._engine = None
    sess._SessionLocal = None
    get_settings.cache_clear()


def test_persist_evolucion_actualiza_memoria():
    # crear familia + paciente con consentimiento
    r = client.post("/auth/register", json={"email": "fam@mem.com", "password": "secret123", "nombre": "F"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    p = client.post("/pacientes", headers=h, json={
        "nombre": "Rosa", "telefono_whatsapp": "+5491100000000", "consentimiento_firmado": True})
    pid = p.json()["id"]

    import health_monitor.db.session as sess
    from health_monitor.db.models import Paciente
    from health_monitor.services import build_call_state, persist_evolucion
    from shared.security import FieldCipher

    s = sess._SessionLocal()
    state, _ = build_call_state(s, pid)  # arma un CallState válido (limits, etc.)
    state.relato = "Contó que su nieto Tomás empezó la facultad y está contenta."
    state.transcript = "Rosa: mi nieto Tomás empezó la facultad."
    persist_evolucion(s, state)
    p_row = s.get(Paciente, pid)
    assert p_row.memoria_enc is not None  # se pobló la memoria
    memoria = FieldCipher(get_settings().encryption_key).decrypt(p_row.memoria_enc)
    assert "Tomás" in memoria  # contiene lo que contó
    s.close()
