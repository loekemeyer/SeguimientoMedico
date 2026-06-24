"""Suscripción y pagos: estado del plan e inicio del checkout.

Los usuarios de obra social no pagan (lo cubre el prestador). Los privados ven su
plan y pueden iniciar el pago; la pasarela real se enchufa en `payments.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from health_monitor.api.deps import get_current_user
from health_monitor.db.models import Usuario
from health_monitor.db.session import get_session
from health_monitor.payments import PLAN_DEFAULT, get_provider

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/estado")
def estado(user: Usuario = Depends(get_current_user)) -> dict:
    """Estado de la suscripción + plan disponible para mostrarlo en 'Mi suscripción'."""
    plan = PLAN_DEFAULT
    return {
        "tipo_cuenta": user.tipo_cuenta,
        "obra_social": user.obra_social,
        "plan": user.plan,
        "suscripcion_vence": user.suscripcion_vence.isoformat() if user.suscripcion_vence else None,
        "proveedor_configurado": get_provider().configurado(),
        "plan_disponible": {
            "id": plan.id, "nombre": plan.nombre, "precio": plan.precio, "moneda": plan.moneda,
        },
    }


@router.post("/suscribir")
def suscribir(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Inicia el checkout de la suscripción privada (o informa que ya está cubierta)."""
    if user.tipo_cuenta == "obra_social":
        return {
            "status": "cubierto",
            "detail": "Tu cobertura corre por cuenta de tu obra social; no necesitás pagar.",
        }
    return get_provider().crear_checkout(user, PLAN_DEFAULT)
