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
from health_monitor.payments import PLAN_DEFAULT, PLANES, get_provider

router = APIRouter(prefix="/billing", tags=["billing"])


def _plan_dict(p) -> dict:
    return {"id": p.id, "nombre": p.nombre, "precio": p.precio, "moneda": p.moneda}


@router.get("/estado")
def estado(user: Usuario = Depends(get_current_user)) -> dict:
    """Estado de la suscripción + los planes disponibles para 'Mi suscripción'."""
    return {
        "tipo_cuenta": user.tipo_cuenta,
        "obra_social": user.obra_social,
        "plan": user.plan,
        "suscripcion_vence": user.suscripcion_vence.isoformat() if user.suscripcion_vence else None,
        "proveedor_configurado": get_provider().configurado(),
        "planes": [_plan_dict(p) for p in PLANES.values()],
        # compat: el primer plan como "disponible" por defecto.
        "plan_disponible": _plan_dict(PLAN_DEFAULT),
    }


@router.post("/suscribir")
def suscribir(
    plan: str = "app",
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict:
    """Inicia el checkout del plan elegido (o informa que la obra social ya cubre)."""
    if user.tipo_cuenta == "obra_social":
        return {
            "status": "cubierto",
            "detail": "Tu cobertura corre por cuenta de tu obra social; no necesitás pagar.",
        }
    elegido = PLANES.get(plan, PLAN_DEFAULT)
    # Registramos el plan elegido (para BI/ingreso). El cobro real lo confirma
    # la pasarela; el ingreso se reconoce cuando plan == "activo".
    if user.plan_tipo != elegido.id:
        user.plan_tipo = elegido.id
        db.commit()
    return get_provider().crear_checkout(user, elegido)
