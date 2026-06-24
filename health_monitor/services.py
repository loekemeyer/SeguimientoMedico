"""Capa de servicio: une persistencia (HCE), cifrado y orquestación de agentes.

Aquí se descifran los datos sensibles para uso en memoria y se vuelven a cifrar
antes de persistir. Mantener esto fuera de los modelos ORM hace explícito dónde
existen datos en claro.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.agents import mood
from health_monitor.agents.orchestrator import CallState
from health_monitor.db.models import (
    ContactoEmergencia,
    EvolucionDiaria,
    FichaClinica,
    Notificacion,
    Paciente,
    RutinaItem,
)
from health_monitor.triage import ClinicalLimits
from health_monitor.triage.plantillas import aplicar_plantillas
from shared.config import get_settings
from shared.security import FieldCipher

logger = logging.getLogger(__name__)


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
    # Orden de precedencia: defaults del modelo < plantillas por patología < manual.
    manual = dict(ficha.limites) if ficha and ficha.limites else {}
    manual["paciente_id"] = paciente_id
    patologias = ficha.patologias if ficha and ficha.patologias else []
    merged = aplicar_plantillas({}, patologias)
    merged.update(manual)  # los límites manuales del admin ganan sobre la plantilla
    return ClinicalLimits.model_validate(merged)


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


def _load_rutina_resumen(db: Session, paciente_id: int, cipher: FieldCipher) -> str:
    """Texto con la rutina activa del paciente, ordenada por horario, para el guion."""
    rows = db.scalars(
        select(RutinaItem)
        .where(RutinaItem.paciente_id == paciente_id, RutinaItem.activa.is_(True))
        .order_by(RutinaItem.horario)
    ).all()
    partes: list[str] = []
    for r in rows:
        nombre = cipher.decrypt(r.nombre_enc) if r.nombre_enc else ""
        if not nombre:
            continue
        hora = f" ({r.horario})" if r.horario else ""
        partes.append(f"{nombre}{hora}")
    return "; ".join(partes)


def _load_historial_resumen(db: Session, paciente_id: int) -> str:
    """Resumen de la última llamada + tendencia del ánimo, para abrir con contexto.

    Le da al acompañante continuidad emocional: no solo qué pasó la última vez,
    sino cómo viene el ánimo en las últimas llamadas (mejora / baja / se mantiene).
    """
    evos = db.scalars(
        select(EvolucionDiaria)
        .where(EvolucionDiaria.paciente_id == paciente_id)
        .order_by(EvolucionDiaria.fecha.desc())
        .limit(5)
    ).all()
    if not evos:
        return ""
    ult = evos[0]
    fecha = ult.fecha.strftime("%d/%m")
    detalle = ult.resumen or "; ".join(ult.motivos or []) or "sin novedades"
    linea = f"Última llamada ({fecha}, nivel {ult.nivel_alerta}): {detalle}"
    tendencia = mood.tendencia_animo(
        [{"fecha": e.fecha, "readout": e.readout} for e in evos]
    )
    return f"{linea}. {tendencia}" if tendencia else linea


def _necesita_screening_animo(db: Session, paciente_id: int) -> bool:
    """¿Conviene explorar el ánimo (GDS-15) hoy? Gatillado por señales del historial."""
    evos = db.scalars(
        select(EvolucionDiaria)
        .where(EvolucionDiaria.paciente_id == paciente_id)
        .order_by(EvolucionDiaria.fecha.desc())
        .limit(3)
    ).all()
    return mood.necesita_screening([{"readout": e.readout} for e in evos])


def _load_peso_anterior(db: Session, paciente_id: int) -> tuple[float | None, int | None]:
    """Última medición de peso conocida y su antigüedad en días (para detectar saltos)."""
    rows = db.scalars(
        select(EvolucionDiaria)
        .where(EvolucionDiaria.paciente_id == paciente_id)
        .order_by(EvolucionDiaria.fecha.desc())
        .limit(10)
    ).all()
    for e in rows:
        peso = (e.readout or {}).get("peso")
        if isinstance(peso, (int, float)):
            fecha = e.fecha if e.fecha.tzinfo else e.fecha.replace(tzinfo=timezone.utc)
            return float(peso), (datetime.now(timezone.utc) - fecha).days
    return None, None


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
    rutina_resumen = _load_rutina_resumen(db, paciente_id, cipher)
    historial_resumen = _load_historial_resumen(db, paciente_id)
    memoria = cipher.decrypt(paciente.memoria_enc) if paciente.memoria_enc else ""
    peso_anterior, peso_dias = _load_peso_anterior(db, paciente_id)
    explorar_animo = _necesita_screening_animo(db, paciente_id)

    state = CallState(
        paciente_id=paciente_id,
        limits=limits,
        paciente_nombre=nombre or "",
        contactos=contactos,
        ficha_resumen=ficha_resumen,
        rutina_resumen=rutina_resumen,
        historial_resumen=historial_resumen,
        memoria=memoria,
        resumen_diario=paciente.resumen_diario_familia,
        nivel_insistencia=paciente.nivel_insistencia,
        voz=paciente.voz,
        voz_velocidad=paciente.voz_velocidad,
        trato=paciente.trato,
        acompanante_nombre=paciente.acompanante_nombre,
        como_llamarlo=paciente.como_llamarlo,
        temas_preferidos=paciente.temas_preferidos,
        temas_evitar=paciente.temas_evitar,
        peso_anterior=peso_anterior,
        peso_dias=peso_dias,
        explorar_animo=explorar_animo,
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
        relato=state.relato,
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

    # Actualizar la memoria de continuidad del paciente (best-effort: nunca rompe).
    _actualizar_memoria_paciente(db, state, cipher)

    db.commit()
    db.refresh(evo)
    return evo


def _actualizar_memoria_paciente(db: Session, state: CallState, cipher: FieldCipher) -> None:
    """Destila la memoria acumulada con lo de esta llamada y la guarda cifrada."""
    try:
        from health_monitor.memoria import actualizar_memoria

        paciente = db.get(Paciente, state.paciente_id)
        if paciente is None:
            return
        previa = cipher.decrypt(paciente.memoria_enc) if paciente.memoria_enc else ""
        nueva = actualizar_memoria(
            previa, state.relato, state.transcript,
            nombre=state.paciente_nombre, trato=state.trato,
        )
        if nueva and nueva.strip():
            paciente.memoria_enc = cipher.encrypt(nueva.strip())
    except Exception:  # la memoria es un extra: si falla, no frena la persistencia
        logger.warning("No se pudo actualizar la memoria del paciente %s", state.paciente_id)
