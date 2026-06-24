"""Endpoints del módulo Acompañante (la app del paciente).

El paciente entra con su código de acceso (6 dígitos) + la clave rotativa (2
dígitos del panel del familiar) y recibe un token de larga duración. La charla
con IA (texto/voz) se enchufa cuando se configura OPENAI_API_KEY.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.acompanante import clave_valida
from health_monitor.api.deps import subscription_active
from health_monitor.chat import ContextoPaciente, responder
from health_monitor.db.models import Paciente
from health_monitor.ratelimit import enforce
from health_monitor.usage import (
    CHAT_MSG,
    LOGIN_PACIENTE,
    estimar_costo_chat,
    estimar_tokens,
    registrar_evento,
)
from health_monitor.db.session import get_session
from shared.auth import create_patient_token, paciente_id_from_token
from shared.config import get_settings
from shared.security import FieldCipher

router = APIRouter(prefix="/acompanante", tags=["acompanante"])


def _nombre(p: Paciente) -> str:
    if not p.nombre_enc:
        return ""
    try:
        return FieldCipher(get_settings().encryption_key).decrypt(p.nombre_enc)
    except Exception:
        # Dato corrupto / clave rotada: que el login no se caiga por el nombre.
        return ""


def _memoria(p: Paciente) -> str:
    """Memoria de continuidad descifrada (vacía si no hay)."""
    if not p.memoria_enc:
        return ""
    try:
        return FieldCipher(get_settings().encryption_key).decrypt(p.memoria_enc)
    except Exception:
        return ""


def paciente_actual(
    authorization: str = Header(default=""),
    db: Session = Depends(get_session),
) -> Paciente:
    """Valida el token del paciente y devuelve su registro."""
    token = authorization.removeprefix("Bearer ").strip()
    pid = paciente_id_from_token(token)
    if pid is None:
        raise HTTPException(status_code=401, detail="Sesión inválida")
    p = db.get(Paciente, pid)
    if p is None or not p.activo:
        raise HTTPException(status_code=401, detail="Sesión inválida")
    return p


class AccesoIn(BaseModel):
    codigo_acceso: str
    clave: str


@router.post("/login")
def login(data: AccesoIn, request: Request, db: Session = Depends(get_session)) -> dict:
    """Login del paciente: código de acceso + clave rotativa. Token sin vencimiento útil."""
    codigo = (data.codigo_acceso or "").strip()
    # Anti-fuerza-bruta de la clave de 2 dígitos. Los límites POR CÓDIGO van sin IP
    # (include_ip=False): si dependieran de la IP, un atacante que rota
    # X-Forwarded-For tendría presupuesto nuevo por cada IP y podría adivinar la
    # clave en segundos. Capamos por código (rápido y lento) y además por IP.
    enforce(request, bucket="paclogin", identity=codigo, limit=5, window=60,
            include_ip=False,
            detail="Demasiados intentos. Esperá un momento y pedí la clave de nuevo.")
    enforce(request, bucket="paclogin-lento", identity=codigo, limit=20, window=600,
            include_ip=False,
            detail="Demasiados intentos con este código. Esperá unos minutos.")
    enforce(request, bucket="paclogin-ip", limit=20, window=60,
            detail="Demasiados intentos. Esperá un momento y probá de nuevo.")
    p = db.scalar(select(Paciente).where(Paciente.codigo_acceso == codigo)) if codigo else None
    if p is None or not p.activo or not clave_valida(codigo, data.clave):
        raise HTTPException(status_code=401, detail="Código o clave incorrectos")
    registrar_evento(
        db, tipo=LOGIN_PACIENTE, modulo="acompanado",
        usuario_id=p.usuario_id, paciente_id=p.id,
    )
    return {"token": create_patient_token(p.id), "nombre": _nombre(p)}


@router.get("/me")
def me(p: Paciente = Depends(paciente_actual)) -> dict:
    """Datos mínimos del paciente para saludarlo en su pantalla."""
    return {
        "nombre": _nombre(p),
        "trato": p.trato,
        "acompanante_nombre": p.acompanante_nombre,
    }


class MensajeIn(BaseModel):
    mensaje: str = ""
    historial: list = []


@router.post("/chat")
def chat(
    data: MensajeIn,
    p: Paciente = Depends(paciente_actual),
    db: Session = Depends(get_session),
) -> dict:
    """Charla del paciente con el acompañante.

    La IA (texto) se activa cuando se configura OPENAI_API_KEY en el entorno.
    Hasta entonces responde con un mensaje cálido (el módulo ya queda andando).
    La apertura de la charla siempre es un saludo cordial (sin gastar API).
    """
    # Gating de pago: la charla con IA es la feature paga. El saludo de apertura
    # (mensaje vacío) es siempre gratis; un turno real exige suscripción vigente
    # de la familia. Si no hay, respondemos con cariño y sin gastar API.
    if (data.mensaje or "").strip() and not (p.usuario and subscription_active(p.usuario)):
        return {
            "configurado": False,
            "respuesta": (
                "¡Hola! Te quiero un montón 💛. En un ratito seguimos charlando; "
                "avisale a tu familia que ya volvemos."
            ),
        }

    ctx = ContextoPaciente(
        nombre=_nombre(p),
        trato=p.trato or "vos",
        acompanante_nombre=p.acompanante_nombre or "",
        como_llamarlo=p.como_llamarlo or "",
        temas_preferidos=p.temas_preferidos or "",
        temas_evitar=p.temas_evitar or "",
        memoria=_memoria(p),
    )
    configurado, respuesta = responder(data.mensaje, data.historial, ctx)
    # Registrar el turno solo cuando hubo una llamada real a la IA (no el saludo).
    if configurado and (data.mensaje or "").strip():
        tokens = estimar_tokens(data.mensaje, respuesta, *(
            (h.get("content") or "") for h in (data.historial or []) if isinstance(h, dict)
        ))
        registrar_evento(
            db, tipo=CHAT_MSG, modulo="acompanado",
            usuario_id=p.usuario_id, paciente_id=p.id,
            unidades=tokens, costo_estimado=estimar_costo_chat(tokens),
            meta={"modelo": get_settings().openai_chat_model},
        )
    return {"configurado": configurado, "respuesta": respuesta}
