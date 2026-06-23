"""Dependencias compartidas de la API (autenticación y suscripción del request)."""
from __future__ import annotations

from datetime import datetime, timezone

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


def subscription_active(user: Usuario, now: datetime | None = None) -> bool:
    """¿El usuario tiene una suscripción vigente para operar (escribir/llamar)?

    Reglas: cuenta activa, plan distinto de 'cancelado' y fecha de vencimiento en
    el futuro. Un plan 'activo' sin fecha se considera vigente (cuenta de
    cortesía/interna). Tolera fechas naive (SQLite no preserva la zona horaria).
    """
    now = now or datetime.now(timezone.utc)
    if not user.activo or user.plan == "cancelado":
        return False
    vence = user.suscripcion_vence
    if vence is not None:
        if vence.tzinfo is None:  # SQLite devuelve datetimes sin zona
            vence = vence.replace(tzinfo=timezone.utc)
        return vence >= now
    return user.plan == "activo"


def require_active_subscription(
    user: Usuario = Depends(get_current_user),
) -> Usuario:
    """Como `get_current_user` pero además exige suscripción vigente (402 si no).

    Se usa en las acciones que consumen el servicio (alta/edición de pacientes,
    rutina, contactos, iniciar llamadas). Las lecturas siguen permitidas para que
    un usuario vencido pueda ver sus datos y renovar.
    """
    if not subscription_active(user):
        raise HTTPException(
            status_code=402,
            detail=(
                "Tu suscripción no está vigente. Renovala para seguir gestionando "
                "pacientes y llamadas."
            ),
        )
    return user
