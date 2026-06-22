"""Demo local del flujo completo — SIN servicios pagos (Twilio/OpenAI) ni red.

Ejecuta de punta a punta lo que pasa al cerrar una llamada de seguimiento:

    paciente + consentimiento  ->  ficha clínica (límites)  ->  transcripción
        ->  Agente Clínico (extrae métricas)  ->  Supervisor (triaje)
        ->  alertas (modo degradado: se loguean)  ->  guardado en la HCE

Usa SQLite local (archivo demo.db) y una clave de cifrado generada al vuelo, así
no necesitás configurar nada. Corré desde la raíz del repo:

    python scripts/demo_local.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite correr el script directamente (python scripts/demo_local.py) agregando
# la raíz del repo al path de imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Configuración de la demo: se setea ANTES de importar los módulos ---
# (get_settings cachea, así que el entorno tiene que estar listo primero).
os.environ.setdefault("DATABASE_URL", "sqlite:///./demo.db")
if not os.environ.get("ENCRYPTION_KEY"):
    from shared.security import generate_key

    os.environ["ENCRYPTION_KEY"] = generate_key()

from health_monitor.agents.orchestrator import CallState, run_post_call  # noqa: E402
from health_monitor.db.models import FichaClinica, Paciente  # noqa: E402
from health_monitor.db.session import create_all, get_session  # noqa: E402
from health_monitor.schemas.fhir import readout_to_fhir_bundle  # noqa: E402
from health_monitor.services import build_call_state, persist_evolucion  # noqa: E402
from shared.config import get_settings  # noqa: E402
from shared.security import FieldCipher  # noqa: E402

# Tres llamadas simuladas que disparan cada nivel de triaje.
TRANSCRIPCIONES = {
    "VERDE": "Hola, ¿cómo está? — Bien, tranquilo. Ya tomé la pastilla. "
             "Me medí la presión y me dio 120 sobre 80. Todo bien.",
    "AMARILLA": "Hola. — La verdad medio decaído, sin ganas. "
                "Uy, me olvidé de tomar la pastilla hoy.",
    "ROJA": "Hola... — Me agarró un dolor de pecho fuerte y me falta el aire "
            "desde hace un rato.",
}


def seed_paciente(db) -> int:
    """Crea un paciente de prueba con consentimiento firmado y ficha clínica."""
    cipher = FieldCipher(get_settings().encryption_key)

    # Limpieza idempotente: borra el paciente demo si ya existe.
    existente = db.query(Paciente).filter_by(hce_id="DEMO-001").one_or_none()
    if existente:
        db.delete(existente)
        db.commit()

    paciente = Paciente(
        hce_id="DEMO-001",
        nombre_enc=cipher.encrypt("Alejandro Damián Loekemeyer"),
        telefono_whatsapp_enc=cipher.encrypt("+5491131181594"),
        familiares_enc=[cipher.encrypt("+5491162521635")],  # Thomas (hijo) a cargo
        consentimiento_firmado=True,
        consentimiento_fecha=datetime.now(timezone.utc),
        consentimiento_apoderado_enc=cipher.encrypt("Thomas Loekemeyer (hijo)"),
    )
    paciente.ficha = FichaClinica(
        limites={"sistolica_max": 140, "sistolica_min": 100, "glucemia_max": 180},
        medicacion_enc=[cipher.encrypt("Losartán 50mg - 1 por día")],
        patologias=["I10"],  # hipertensión esencial (CIE-10)
    )
    db.add(paciente)
    db.commit()
    db.refresh(paciente)
    return paciente.id


def correr_llamada(db, paciente_id: int, nivel: str, transcript: str) -> None:
    state, nombre = build_call_state(db, paciente_id)
    state.transcript = transcript
    state = run_post_call(state)
    persist_evolucion(db, state)

    print(f"\n{'='*64}\n  LLAMADA SIMULADA — esperado: {nivel}  (paciente: {nombre})")
    print(f"{'='*64}")
    print(f"  Transcripción : {transcript[:70]}...")
    print(f"  Triaje        : {state.triage.level_name}")
    for motivo in state.triage.reasons:
        print(f"      - {motivo}")
    print(f"  Alertas       : {state.alerts_dispatched}")
    if state.readout:
        bundle = readout_to_fhir_bundle(state.readout)
        print(f"  FHIR Bundle   : {len(bundle['entry'])} Observation(s) listas para la HCE")


def main() -> None:
    print("Inicializando base de datos local (SQLite: demo.db)...")
    create_all()
    db = next(get_session())
    try:
        paciente_id = seed_paciente(db)
        print(f"Paciente demo creado (id={paciente_id}, consentimiento OK).")
        for nivel, transcript in TRANSCRIPCIONES.items():
            correr_llamada(db, paciente_id, nivel, transcript)

        total = len(db.get(Paciente, paciente_id).evoluciones)
        print(f"\n{'='*64}")
        print(f"  Listo. Se guardaron {total} registros en la HCE (evolucion_diaria).")
        print("  (Las transcripciones quedaron CIFRADAS con AES-256 en la DB.)")
        print(f"{'='*64}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
