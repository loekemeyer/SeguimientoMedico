"""Capa de servicio: une persistencia (HCE), cifrado y orquestación de agentes.

Aquí se descifran los datos sensibles para uso en memoria y se vuelven a cifrar
antes de persistir. Mantener esto fuera de los modelos ORM hace explícito dónde
existen datos en claro.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.agents.orchestrator import CallState
from health_monitor.db.models import (
    ContactoEmergencia,
    EvolucionDiaria,
    FichaClinica,
    Notificacion,
    Paciente,
)
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
    data = dict(ficha.limites) if ficha and ficha.limites else {}
    data["paciente_id"] = paciente_id
    return ClinicalLimits.model_validate(data)


def _load_contactos(db: Session, paciente_id: int) -> list[dict]:
    """Devuelve los contactos descifrados, ordenados por escalamiento."""
    cipher = _cipher()
    rows = db.scalars(
        select(ContactoEmergencia)
        .where(ContactoEmergencia.paciente_id == paciente_id)
        .order_by(ContactoEmergencia.prioridad)
    ).all()
    contactos = []
    for c in rows:
        nombre = cipher.decrypt(c.nombre_enc) if c.nombre_enc else ""
        label = f"{nombre} ({c.relacion})" if c.relacion else nombre
        contactos.append({
            "telefono": cipher.decrypt(c.telefono_enc),
            "label": label,
            "recibe_alertas": c.recibe_alertas,
        })
    return contactos


def build_call_state(db: Session, paciente_id: int) -> tuple[CallState, str | None]:
    """Prepara el CallState de una llamada: límites, contactos y resumen de ficha."""
    paciente = db.get(Paciente, paciente_id)
    if paciente is None:
        raise ValueError(f"Paciente {paciente_id} inexistente")
    require_consent(paciente)

    cipher = _cipher()
    nombre = cipher.decrypt(paciente.nombre_enc) if paciente.nombre_enc else None
    contactos = _load_contactos(db, paciente_id)

    ficha = paciente.ficha
    limits = _limits_from_ficha(paciente_id, ficha)
    patologias = ", ".join(ficha.patologias) if ficha and ficha.patologias else "s/d"
    ficha_resumen = f"Paciente {paciente_id}. Patologías: {patologias}."

    state = CallState(
        paciente_id=paciente_id,
        limits=limits,
        paciente_nombre=nombre or "",
        contactos=contactos,
        ficha_resumen=ficha_resumen,
    )
    return state, nombre


def persist_evolucion(db: Session, state: CallState) -> EvolucionDiaria:
    """Guarda el registro de la llamada (resumen, triaje, transcripción cifrada)
    y asienta cada notificación enviada para el seguimiento del familiar."""
    cipher = _cipher()
    evo = EvolucionDiaria(
        paciente_id=state.paciente_id,
        fecha=datetime.now(timezone.utc),
        readout=state.readout.model_dump(mode="json") if state.readout else {},
        nivel_alerta=state.triage.level_name if state.triage else "VERDE",
        motivos=state.triage.reasons if state.triage else [],
        resumen=state.resumen,
        transcripcion_enc=cipher.encrypt(state.transcript) if state.transcript else None,
    )
    db.add(evo)
    db.flush()  # asigna evo.id sin cerrar la transacción

    for reg in state.alerts_dispatched or []:
        db.add(Notificacion(
            paciente_id=state.paciente_id,
            evolucion_id=evo.id,
            canal=reg["canal"],
            nivel_alerta=reg["nivel"],
            destino_enc=cipher.encrypt(str(reg["destino"])),
            destino_label=reg.get("destino_label", ""),
            contenido=reg["contenido"],
            enviado=reg["enviado"],
        ))

    db.commit()
    db.refresh(evo)
    return evo
