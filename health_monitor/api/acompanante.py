"""Endpoints del módulo Acompañante (la app del paciente).

El paciente entra con su código de acceso (6 dígitos) + la clave rotativa (2
dígitos del panel del familiar) y recibe un token de larga duración. La charla
con IA (texto/voz) se enchufa cuando se configura OPENAI_API_KEY.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.acompanante import clave_valida
from health_monitor.db.models import Paciente
from health_monitor.db.session import get_session
from shared.auth import create_patient_token, paciente_id_from_token
from shared.config import get_settings
from shared.security import FieldCipher

router = APIRouter(prefix="/acompanante", tags=["acompanante"])


def _nombre(p: Paciente) -> str:
    if not p.nombre_enc:
        return ""
    return FieldCipher(get_settings().encryption_key).decrypt(p.nombre_enc)


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
def login(data: AccesoIn, db: Session = Depends(get_session)) -> dict:
    """Login del paciente: código de acceso + clave rotativa. Token sin vencimiento útil."""
    codigo = (data.codigo_acceso or "").strip()
    p = db.scalar(select(Paciente).where(Paciente.codigo_acceso == codigo)) if codigo else None
    if p is None or not p.activo or not clave_valida(codigo, data.clave):
        raise HTTPException(status_code=401, detail="Código o clave incorrectos")
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
def chat(data: MensajeIn, p: Paciente = Depends(paciente_actual)) -> dict:
    """Charla del paciente con el acompañante.

    La IA (texto/voz) se activa cuando se configura OPENAI_API_KEY en el entorno.
    Hasta entonces responde con un mensaje cálido (el módulo ya queda andando).
    """
    if not get_settings().openai_api_key:
        return {
            "configurado": False,
            "respuesta": (
                "¡Hola! Soy tu acompañante 💛. En un ratito ya vamos a poder charlar "
                "tranquilos. Falta un pasito para activar mi voz."
            ),
        }
    return {"configurado": True, "respuesta": "Te escucho. Contame, ¿cómo venís hoy?"}
