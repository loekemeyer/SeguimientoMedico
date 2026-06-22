"""Dependencias compartidas de la API (autenticación del request)."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from health_monitor.db.models import Usuario
from health_monitor.db.session import get_session
from shared.auth import decode_token


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_session),
) -> Usuario:
    """Valida el token Bearer y devuelve el usuario autenticado."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el token de sesión")
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o vencido")
    user = db.get(Usuario, payload.get("sub"))
    if user is None or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user
