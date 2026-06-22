"""Capa de servicio: une persistencia (HCE), cifrado y orquestación de agentes.

Aquí se descifran los datos sensibles para uso en memoria y se vuelven a cifrar
antes de persistir. Mantener esta lógica fuera de los modelos ORM hace explícito
dónde existen datos en claro (y por cuánto tiempo).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from health_monitor.agents.orchestrator import CallState
from health_monitor.db.models import EvolucionDiaria, FichaClinica, Paciente
from health_monitor.triage import ClinicalLimits
from shared.config import get_settings
from shared.security import FieldCipher


def _cipher() -> FieldCipher:
    return FieldCipher(get_settings().encryption_key)


def require_consent(paciente: Paciente) -> None:
    """Exige consentimiento informado firmado (Ley 25.326) antes de operar."""
    if not (paciente.consentimiento_firmado and paciente.consentimiento_fecha):
        raise HTTPException(
            status_code=403,
            detail=(
                "Falta el consentimiento informado del apoderado legal. "
                "No se puede iniciar el seguimiento (Ley 25.326)."
            ),
        )


def _limits_from_ficha(paciente_id: int, ficha: FichaClinica | None) -> ClinicalLimits:
    """Construye los límites de triaje desde la ficha clínica (o defaults)."""
    data = dict(ficha.limites) if ficha and ficha.limites else {}
    data["paciente_id"] = paciente_id
    return ClinicalLimits.model_validate(data)


def build_call_state(db: Session, paciente_id: int) -> tuple[CallState, str | None]:
    """Prepara el CallState de una llamada: límites, familiares y resumen de ficha.

    Devuelve (state, nombre_descifrado_para_saludo).
    """
    paciente = db.get(Paciente, paciente_id)
    if paciente is None:
        raise ValueError(f"Paciente {paciente_id} inexistente")
    require_consent(paciente)

    cipher = _cipher()
    nombre = cipher.decrypt(paciente.nombre_enc) if paciente.nombre_enc else None
    familiares = [cipher.decrypt(f) for f in (paciente.familiares_enc or [])]

    ficha = paciente.ficha
    limits = _limits_from_ficha(paciente_id, ficha)
    patologias = ", ".join(ficha.patologias) if ficha and ficha.patologias else "s/d"
    ficha_resumen = f"Paciente {paciente_id}. Patologías: {patologias}."

    state = CallState(
        paciente_id=paciente_id,
        limits=limits,
        paciente_nombre=nombre or "",
        familiares=familiares,
        ficha_resumen=ficha_resumen,
    )
    return state, nombre


def persist_evolucion(db: Session, state: CallState) -> EvolucionDiaria:
    """Guarda el registro diario en la HCE, con la transcripción cifrada."""
    cipher = _cipher()
    transcripcion_enc = (
        cipher.encrypt(state.transcript) if state.transcript else None
    )
    evo = EvolucionDiaria(
        paciente_id=state.paciente_id,
        fecha=datetime.now(timezone.utc),
        readout=state.readout.model_dump(mode="json") if state.readout else {},
        nivel_alerta=state.triage.level_name if state.triage else "VERDE",
        motivos=state.triage.reasons if state.triage else [],
        transcripcion_enc=transcripcion_enc,
    )
    db.add(evo)
    db.commit()
    db.refresh(evo)
    return evo
