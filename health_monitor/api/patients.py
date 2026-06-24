"""CRUD multi-usuario de pacientes y sus datos (ficha, medicación, contactos,
historial de llamadas y notificaciones registradas)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.api.deps import get_current_user, require_active_subscription
from health_monitor.db.models import (
    AuditLog,
    ContactoEmergencia,
    EvolucionDiaria,
    FichaClinica,
    Notificacion,
    Paciente,
    RutinaItem,
    Usuario,
)
from health_monitor.db.session import get_session
from health_monitor.schemas.api import (
    ContactoIn,
    ContactoOut,
    EvolucionOut,
    PacienteIn,
    PacienteOut,
    PersonalidadAcompanante,
    ProgramacionLlamada,
    RutinaItemIn,
    RutinaItemOut,
)
from health_monitor.schemas.clinical import ClinicalReadout
from health_monitor.schemas.fhir import readout_to_fhir_bundle
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


def _auditar(db: Session, usuario_id: int, accion: str, recurso: str,
             recurso_id: int | None = None, detalle: str = "") -> None:
    """Asienta una acción en el registro de auditoría (sin commitear: lo hace el caller).

    `detalle` no debe contener PII en claro (solo una descripción)."""
    db.add(AuditLog(usuario_id=usuario_id, accion=accion, recurso=recurso,
                    recurso_id=recurso_id, detalle=detalle))


def _ultimo_nivel(db: Session, paciente_id: int) -> str | None:
    """Nivel de alerta del último seguimiento (para el semáforo de la tarjeta)."""
    return db.scalar(
        select(EvolucionDiaria.nivel_alerta)
        .where(EvolucionDiaria.paciente_id == paciente_id)
        .order_by(EvolucionDiaria.fecha.desc())
        .limit(1)
    )


def _generar_codigo_acceso(db: Session) -> str:
    """Genera un código de 6 dígitos único entre todos los pacientes."""
    for _ in range(25):
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        if not db.scalar(select(Paciente.id).where(Paciente.codigo_acceso == codigo)):
            return codigo
    return f"{secrets.randbelow(1_000_000):06d}"  # colisión extremadamente improbable


def _to_out(p: Paciente, cipher: FieldCipher, ultimo_nivel: str | None = None) -> PacienteOut:
    return PacienteOut(
        id=p.id,
        ultimo_nivel=ultimo_nivel,
        codigo_acceso=p.codigo_acceso,
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
            nivel_insistencia=p.nivel_insistencia,
        ),
        personalidad=PersonalidadAcompanante(
            voz=p.voz,
            velocidad=p.voz_velocidad,
            trato=p.trato,
            acompanante_nombre=p.acompanante_nombre,
            temas_preferidos=p.temas_preferidos,
            temas_evitar=p.temas_evitar,
        ),
        activo=p.activo,
    )


def _apply_programacion(p: Paciente, prog: ProgramacionLlamada) -> None:
    p.llamada_activa = prog.llamada_activa
    p.llamada_hora = prog.llamada_hora
    p.llamada_zona = prog.llamada_zona
    p.llamada_dias = prog.llamada_dias
    p.nivel_insistencia = prog.nivel_insistencia


def _apply_personalidad(p: Paciente, pers: PersonalidadAcompanante) -> None:
    p.voz = pers.voz
    p.voz_velocidad = pers.velocidad
    p.trato = pers.trato
    p.acompanante_nombre = pers.acompanante_nombre.strip()
    p.temas_preferidos = pers.temas_preferidos.strip()
    p.temas_evitar = pers.temas_evitar.strip()


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
        codigo_acceso=_generar_codigo_acceso(db),
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
    _apply_personalidad(p, data.personalidad)
    db.add(p)
    db.flush()  # asigna p.id para la auditoría
    _auditar(db, user.id, "crear", "paciente", p.id, "alta de paciente")
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
    return [_to_out(p, cipher, _ultimo_nivel(db, p.id)) for p in rows]


@router.get("/{paciente_id}", response_model=PacienteOut)
def ver_paciente(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> PacienteOut:
    p = _owned_paciente(db, user, paciente_id)
    return _to_out(p, _cipher(), _ultimo_nivel(db, p.id))


@router.get("/{paciente_id}/codigo-rotativo")
def codigo_rotativo_paciente(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Clave rotativa de 2 dígitos (cambia cada 30s) para dictarle al paciente al entrar."""
    from health_monitor.acompanante import clave_rotativa, segundos_restantes

    p = _owned_paciente(db, user, paciente_id)
    if not p.codigo_acceso:
        return {"clave": None, "segundos": 0}
    return {"clave": clave_rotativa(p.codigo_acceso), "segundos": segundos_restantes()}


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
    _apply_personalidad(p, data.personalidad)
    _auditar(db, user.id, "actualizar", "paciente", p.id, "edición de paciente")
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
    _auditar(db, user.id, "baja", "paciente", p.id, "baja de paciente")
    db.commit()


# --- Medicación ---

def _rutina_out(r: RutinaItem, cipher: FieldCipher) -> RutinaItemOut:
    return RutinaItemOut(
        id=r.id, tipo=r.tipo, nombre=cipher.decrypt(r.nombre_enc),
        frecuencia=r.frecuencia, horario=r.horario, dias=r.dias or [], activa=r.activa,
        aviso=r.aviso,
    )


@router.post("/{paciente_id}/rutina", response_model=RutinaItemOut, status_code=201)
def agregar_rutina(
    paciente_id: int,
    data: RutinaItemIn,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> RutinaItemOut:
    _owned_paciente(db, user, paciente_id)
    r = RutinaItem(
        paciente_id=paciente_id,
        tipo=data.tipo,
        nombre_enc=_cipher().encrypt(data.nombre),
        frecuencia=data.frecuencia,
        horario=data.horario,
        dias=data.dias,
        activa=data.activa,
        aviso=data.aviso,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _rutina_out(r, _cipher())


@router.get("/{paciente_id}/rutina", response_model=list[RutinaItemOut])
def listar_rutina(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[RutinaItemOut]:
    _owned_paciente(db, user, paciente_id)
    cipher = _cipher()
    rows = db.scalars(select(RutinaItem).where(RutinaItem.paciente_id == paciente_id)).all()
    return [_rutina_out(r, cipher) for r in rows]


@router.delete("/{paciente_id}/rutina/{rutina_id}", status_code=204)
def borrar_rutina(
    paciente_id: int,
    rutina_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    """Quita un ítem de la rutina del paciente (solo el dueño)."""
    _owned_paciente(db, user, paciente_id)
    r = db.get(RutinaItem, rutina_id)
    if r is None or r.paciente_id != paciente_id:
        raise HTTPException(status_code=404, detail="Ítem de rutina no encontrado")
    db.delete(r)
    _auditar(db, user.id, "baja", "rutina", paciente_id, "baja de ítem de rutina")
    db.commit()


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


@router.delete("/{paciente_id}/contactos/{contacto_id}", status_code=204)
def borrar_contacto(
    paciente_id: int,
    contacto_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    """Quita un contacto de emergencia del paciente (solo el dueño)."""
    _owned_paciente(db, user, paciente_id)
    c = db.get(ContactoEmergencia, contacto_id)
    if c is None or c.paciente_id != paciente_id:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    db.delete(c)
    _auditar(db, user.id, "baja", "contacto", paciente_id, "baja de contacto de emergencia")
    db.commit()


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
                     motivos=e.motivos, readout=e.readout, relato=e.relato)
        for e in rows
    ]


@router.get("/{paciente_id}/auditoria")
def auditoria_paciente(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict]:
    """Registro de auditoría (quién hizo qué y cuándo) sobre este paciente."""
    _owned_paciente(db, user, paciente_id)
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.recurso == "paciente", AuditLog.recurso_id == paciente_id)
        .order_by(AuditLog.fecha.desc())
    ).all()
    return [
        {"fecha": r.fecha.isoformat(), "accion": r.accion,
         "recurso": r.recurso, "detalle": r.detalle}
        for r in rows
    ]


@router.get("/{paciente_id}/fhir")
def exportar_fhir(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Exporta la última evolución como Bundle FHIR R4 (interoperable con prepagas/HCE)."""
    _owned_paciente(db, user, paciente_id)
    evo = db.scalars(
        select(EvolucionDiaria)
        .where(EvolucionDiaria.paciente_id == paciente_id)
        .order_by(EvolucionDiaria.fecha.desc())
    ).first()
    if evo is None or not evo.readout:
        raise HTTPException(status_code=404, detail="No hay registros clínicos para exportar")
    readout = ClinicalReadout.model_validate(evo.readout)
    return readout_to_fhir_bundle(readout)


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


@router.post("/{paciente_id}/llamar")
def llamar_ahora(
    paciente_id: int,
    user: Usuario = Depends(require_active_subscription),
    db: Session = Depends(get_session),
) -> dict:
    """Dispara una llamada de seguimiento inmediata (sin esperar el horario)."""
    from health_monitor.services import require_consent

    p = _owned_paciente(db, user, paciente_id)
    require_consent(p)

    s = get_settings()
    # Sin teléfono saliente / URL pública no se puede hacer la llamada de voz real.
    if not (s.twilio_account_sid and s.twilio_auth_token and s.public_base_url):
        return {
            "status": "no_disponible",
            "detail": (
                "La llamada de voz todavía no está configurada (falta el teléfono "
                "saliente y la URL pública). Cuando se configure, este botón llama "
                "al instante."
            ),
        }
    try:
        from twilio.rest import Client  # import perezoso

        to = _cipher().decrypt(p.telefono_whatsapp_enc)
        client = Client(s.twilio_account_sid, s.twilio_auth_token)
        call = client.calls.create(
            to=f"whatsapp:{to}",
            from_=s.twilio_whatsapp_from,
            url=f"{s.public_base_url}/twilio/voice?paciente_id={p.id}",
        )
        return {"status": "llamando", "detail": "Llamada iniciada.", "call_sid": call.sid}
    except Exception as exc:
        return {"status": "error", "detail": f"No se pudo iniciar la llamada: {exc}"}


# --- Agente de Mejora Continua (sugerencias proactivas) ---

@router.get("/{paciente_id}/sugerencias")
def sugerencias_paciente(
    paciente_id: int,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict]:
    """Sugerencias proactivas de mejora del cuidado, a partir del historial."""
    from health_monitor.agents.improver import analizar

    p = _owned_paciente(db, user, paciente_id)
    rows = db.scalars(
        select(EvolucionDiaria)
        .where(EvolucionDiaria.paciente_id == paciente_id)
        .order_by(EvolucionDiaria.fecha.desc())
    ).all()
    evoluciones = [
        {"fecha": e.fecha, "nivel_alerta": e.nivel_alerta,
         "motivos": e.motivos, "readout": e.readout}
        for e in rows
    ]
    nombre = _cipher().decrypt(p.nombre_enc) if p.nombre_enc else ""
    return analizar(evoluciones, nombre=nombre)
