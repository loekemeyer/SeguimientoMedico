"""Dependencias compartidas de la API (autenticación y suscripción del request)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from health_monitor.db.models import Usuario
from health_monitor.db.session import get_session
from shared.auth import decode_token
from shared.config import get_settings


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
    if payload.get("typ") == "paciente":  # token del Acompañante, no del familiar
        raise HTTPException(status_code=401, detail="Token inválido para esta sección")
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
    if not user.activo:
        return False
    # Obra social: la cobertura corre por cuenta del prestador, no por una
    # suscripción paga. La cuenta opera siempre (no se la bloquea con 402).
    if user.tipo_cuenta == "obra_social":
        return True
    if user.plan == "cancelado":
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


def require_plan_telefono(user: Usuario = Depends(require_active_subscription)) -> Usuario:
    """Como `require_active_subscription` pero además exige el plan Teléfono.

    Las llamadas de voz salientes (Twilio) tienen el costo del plan Teléfono
    ($20.000). Un cliente que pagó el plan App ($10.000) no las incluye. La obra
    social y el período de prueba (trial) sí pueden usarlas (cobertura / evaluación).
    """
    if user.tipo_cuenta == "obra_social":
        return user
    if user.plan == "activo" and user.plan_tipo == "app":
        raise HTTPException(
            status_code=402,
            detail=(
                "Las llamadas telefónicas son parte del plan Teléfono. Tu plan "
                "actual es App (charla desde la app). Cambiá al plan Teléfono para "
                "que la llamemos por teléfono."
            ),
        )
    return user


def require_owner(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Exige que el usuario sea el DUEÑO del negocio (panel BI privado).

    Se valida contra `OWNER_EMAIL` del entorno. Si no está configurado, se niega
    el acceso (seguro por defecto): el dueño setea OWNER_EMAIL con su email.
    """
    owner = (get_settings().owner_email or "").strip().lower()
    if not owner or (user.email or "").strip().lower() != owner:
        raise HTTPException(status_code=403, detail="Acceso reservado al dueño")
    return user
