"""CRUD multi-usuario de pacientes y sus datos (ficha, medicación, contactos,
historial de llamadas y notificaciones registradas)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.api.deps import get_current_user
from health_monitor.db.models import (
    ContactoEmergencia,
    EvolucionDiaria,
    FichaClinica,
    Medicacion,
    Notificacion,
    Paciente,
    Usuario,
)
from health_monitor.db.session import get_session
from health_monitor.schemas.api import (
    ContactoIn,
    ContactoOut,
    EvolucionOut,
    MedicacionIn,
    MedicacionOut,
    PacienteIn,
    PacienteOut,
    ProgramacionLlamada,
)
from shared.config import get_settings
from shared.security import FieldCipher

router = APIRouter(prefix="/pacientes", tags=["pacientes"])


def _cipher() -> FieldCipher:
    return FieldCipher(get_settings().encryption_key)


def _owned_paciente(db: Session, user: Usuario, paciente_id: int) -> Paciente:
    """Devuelve el paciente solo si pertenece al usuario; si no, 404."""
    p = db.get(Paciente, paciente_id)
    if p is None or p.usuario_id != user.id:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return p


def _to_out(p: Paciente, cipher: FieldCipher) -> PacienteOut:
    return PacienteOut(
        id=p.id,
        nombre=cipher.decrypt(p.nombre_enc) if p.nombre_enc else "",
        telefono_whatsapp=cipher.decrypt(p.telefono_whatsapp_enc) if p.telefono_whatsapp_enc else "",
        consentimiento_firmado=p.consentimiento_firmado,
        consentimiento_fecha=p.consentimiento_fecha,
        patologias=p.ficha.patologias if p.ficha else [],
        limites=p.ficha.limites if p.ficha else {},
        programacion=ProgramacionLlamada(
            llamada_activa=p.llamada_activa,
            llamada_hora=p.llamada_hora,
            llamada_zona=p.llamada_zona,
            llamada_dias=p.llamada_dias or [],
        ),
        activo=p.activo,
    )


def _apply_programacion(p: Paciente, prog: ProgramacionLlamada) -> None:
    p.llamada_activa = prog.llamada_activa
    p.llamada_hora = prog.llamada_hora
    p.llamada_zona = prog.llamada_zona
    p.llamada_dias = prog.llamada_dias


# --- Pacientes ---

@router.post("", response_model=PacienteOut, status_code=201)
def crear_paciente(
    data: PacienteIn,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> PacienteOut:
    cipher = _cipher()
    p = Paciente(
        usuario_id=user.id,
        hce_id=uuid.uuid4().hex,
        nombre_enc=cipher.encrypt(data.nombre),
        telefono_whatsapp_enc=cipher.encrypt(data.telefono_whatsapp),
        consentimiento_firmado=data.consentimiento_firmado,
        consentimiento_fecha=datetime.now(timezone.utc) if data.consentimiento_firmado else None,
        consentimiento_apoderado_enc=(
            cipher.encrypt(data.consentimiento_apoderado)
            if data.consentimiento_apoderado else None
        ),
    )
    p.ficha = FichaClinica(limites=data.limites, patologias=data.patologias)
    _apply_programacion(p, data.programacion)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_out(p, cipher)


@router.get("", response_model=list[PacienteOut])
def listar_pacientes(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[PacienteOut]:
    cipher = _cipher()
    rows = db.scalars(select(Paciente).where(Paciente.usuario_id == user.id)).all()
    return [_to_out(p, cipher) for p in rows]


@router.get("/{paciente_id}", response_model=PacienteOut)
def ver_paciente(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> PacienteOut:
    return _to_out(_owned_paciente(db, user, paciente_id), _cipher())


@router.put("/{paciente_id}", response_model=PacienteOut)
def actualizar_paciente(
    paciente_id: int,
    data: PacienteIn,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> PacienteOut:
    cipher = _cipher()
    p = _owned_paciente(db, user, paciente_id)
    p.nombre_enc = cipher.encrypt(data.nombre)
    p.telefono_whatsapp_enc = cipher.encrypt(data.telefono_whatsapp)
    if data.consentimiento_firmado and not p.consentimiento_firmado:
        p.consentimiento_fecha = datetime.now(timezone.utc)
    p.consentimiento_firmado = data.consentimiento_firmado
    if p.ficha is None:
        p.ficha = FichaClinica()
    p.ficha.limites = data.limites
    p.ficha.patologias = data.patologias
    _apply_programacion(p, data.programacion)
    db.commit()
    db.refresh(p)
    return _to_out(p, cipher)


@router.delete("/{paciente_id}", status_code=204)
def baja_paciente(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    p = _owned_paciente(db, user, paciente_id)
    p.activo = False
    db.commit()


# --- Medicación ---

@router.post("/{paciente_id}/medicacion", response_model=MedicacionOut, status_code=201)
def agregar_medicacion(
    paciente_id: int,
    data: MedicacionIn,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> MedicacionOut:
    _owned_paciente(db, user, paciente_id)
    m = Medicacion(
        paciente_id=paciente_id,
        nombre_enc=_cipher().encrypt(data.nombre),
        frecuencia=data.frecuencia,
        activa=data.activa,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return MedicacionOut(id=m.id, nombre=data.nombre, frecuencia=m.frecuencia, activa=m.activa)


@router.get("/{paciente_id}/medicacion", response_model=list[MedicacionOut])
def listar_medicacion(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[MedicacionOut]:
    _owned_paciente(db, user, paciente_id)
    cipher = _cipher()
    rows = db.scalars(select(Medicacion).where(Medicacion.paciente_id == paciente_id)).all()
    return [
        MedicacionOut(id=m.id, nombre=cipher.decrypt(m.nombre_enc),
                      frecuencia=m.frecuencia, activa=m.activa)
        for m in rows
    ]


# --- Contactos de emergencia ---

@router.post("/{paciente_id}/contactos", response_model=ContactoOut, status_code=201)
def agregar_contacto(
    paciente_id: int,
    data: ContactoIn,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> ContactoOut:
    _owned_paciente(db, user, paciente_id)
    cipher = _cipher()
    c = ContactoEmergencia(
        paciente_id=paciente_id,
        nombre_enc=cipher.encrypt(data.nombre),
        telefono_enc=cipher.encrypt(data.telefono),
        relacion=data.relacion,
        prioridad=data.prioridad,
        recibe_alertas=data.recibe_alertas,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return ContactoOut(id=c.id, **data.model_dump())


@router.get("/{paciente_id}/contactos", response_model=list[ContactoOut])
def listar_contactos(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[ContactoOut]:
    _owned_paciente(db, user, paciente_id)
    cipher = _cipher()
    rows = db.scalars(
        select(ContactoEmergencia)
        .where(ContactoEmergencia.paciente_id == paciente_id)
        .order_by(ContactoEmergencia.prioridad)
    ).all()
    return [
        ContactoOut(
            id=c.id, nombre=cipher.decrypt(c.nombre_enc),
            telefono=cipher.decrypt(c.telefono_enc), relacion=c.relacion,
            prioridad=c.prioridad, recibe_alertas=c.recibe_alertas,
        )
        for c in rows
    ]


# --- Historial de llamadas y notificaciones (seguimiento del familiar) ---

@router.get("/{paciente_id}/evoluciones", response_model=list[EvolucionOut])
def historial_llamadas(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[EvolucionOut]:
    _owned_paciente(db, user, paciente_id)
    rows = db.scalars(
        select(EvolucionDiaria)
        .where(EvolucionDiaria.paciente_id == paciente_id)
        .order_by(EvolucionDiaria.fecha.desc())
    ).all()
    return [
        EvolucionOut(id=e.id, fecha=e.fecha, nivel_alerta=e.nivel_alerta,
                     motivos=e.motivos, readout=e.readout)
        for e in rows
    ]


@router.get("/{paciente_id}/notificaciones")
def historial_notificaciones(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict]:
    """Registro de todos los mensajes/alertas enviados sobre este paciente."""
    _owned_paciente(db, user, paciente_id)
    rows = db.scalars(
        select(Notificacion)
        .where(Notificacion.paciente_id == paciente_id)
        .order_by(Notificacion.fecha.desc())
    ).all()
    return [
        {
            "id": n.id, "fecha": n.fecha.isoformat(), "canal": n.canal,
            "nivel_alerta": n.nivel_alerta, "destino": n.destino_label,
            "contenido": n.contenido, "enviado": n.enviado,
        }
        for n in rows
    ]
