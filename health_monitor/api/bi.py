"""Panel de inteligencia de negocio (BI) del dueño.

Costo por cliente (desde EventoUso) vs ingreso (desde el plan suscripto) →
rentabilidad, mix de módulos y un asesor agéntico de mejoras. Acceso reservado
al dueño (require_owner). Ver docs/ARQUITECTURA_ESCALA.md §6.

Los costos de EventoUso se estiman en USD; el ingreso de los planes está en ARS.
Para el margen se convierte con `usd_ars` (configurable). Es una estimación de
gestión, no contabilidad.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from health_monitor.api.deps import require_owner
from health_monitor.db.models import AuditLog, EventoUso, Paciente, Usuario
from health_monitor.db.session import get_session
from health_monitor.payments import PLANES
from shared.config import get_settings

router = APIRouter(prefix="/bi", tags=["bi"])


def _ingreso_mensual(user: Usuario) -> int:
    """Ingreso mensual reconocido del cliente (ARS): sólo si el plan está activo."""
    if user.plan != "activo":
        return 0
    plan = PLANES.get(user.plan_tipo)
    return plan.precio if plan else 0


def _desde(dias: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max(1, dias))


@router.get("/resumen")
def resumen(
    dias: int = 30,
    _: Usuario = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    """Totales del negocio en el período: ingreso, costo, margen y actividad."""
    desde = _desde(dias)
    usd_ars = get_settings().usd_ars

    usuarios = db.scalars(select(Usuario).where(Usuario.activo.is_(True))).all()
    clientes_total = len(usuarios)
    clientes_activos = sum(1 for u in usuarios if u.plan == "activo")
    ingreso_ars = sum(_ingreso_mensual(u) for u in usuarios)

    costo_usd = db.scalar(
        select(func.coalesce(func.sum(EventoUso.costo_estimado), 0.0)).where(EventoUso.ts >= desde)
    ) or 0.0
    costo_ars = costo_usd * usd_ars

    por_tipo = db.execute(
        select(EventoUso.tipo, func.count(), func.coalesce(func.sum(EventoUso.costo_estimado), 0.0))
        .where(EventoUso.ts >= desde)
        .group_by(EventoUso.tipo)
    ).all()
    por_modulo = db.execute(
        select(EventoUso.modulo, func.count(), func.coalesce(func.sum(EventoUso.costo_estimado), 0.0))
        .where(EventoUso.ts >= desde)
        .group_by(EventoUso.modulo)
    ).all()

    return {
        "dias": dias,
        "moneda_ingreso": "ARS",
        "usd_ars": usd_ars,
        "clientes_total": clientes_total,
        "clientes_activos": clientes_activos,
        "clientes_trial": sum(1 for u in usuarios if u.plan == "trial"),
        "ingreso_mensual_ars": ingreso_ars,
        "costo_periodo_usd": round(costo_usd, 4),
        "costo_periodo_ars": round(costo_ars, 2),
        "margen_ars": round(ingreso_ars - costo_ars, 2),
        "eventos_por_tipo": [
            {"tipo": t, "cantidad": c, "costo_usd": round(s, 4)} for (t, c, s) in por_tipo
        ],
        "costo_por_modulo": [
            {"modulo": m or "—", "cantidad": c, "costo_usd": round(s, 4)} for (m, c, s) in por_modulo
        ],
    }


@router.get("/clientes")
def clientes(
    dias: int = 30,
    _: Usuario = Depends(require_owner),
    db: Session = Depends(get_session),
) -> list[dict]:
    """Rentabilidad por cliente: ingreso vs costo, mix de módulos y actividad."""
    desde = _desde(dias)
    usd_ars = get_settings().usd_ars

    # Costo y actividad por cliente (una query agregada, sin N+1).
    agg = db.execute(
        select(
            EventoUso.usuario_id,
            func.coalesce(func.sum(EventoUso.costo_estimado), 0.0),
            func.count(),
            func.max(EventoUso.ts),
        )
        .where(EventoUso.ts >= desde)
        .group_by(EventoUso.usuario_id)
    ).all()
    costo_por_user = {uid: (c, n, ult) for (uid, c, n, ult) in agg}

    # Mix de módulos por cliente.
    mix_rows = db.execute(
        select(EventoUso.usuario_id, EventoUso.modulo, func.count())
        .where(EventoUso.ts >= desde)
        .group_by(EventoUso.usuario_id, EventoUso.modulo)
    ).all()
    mix_por_user: dict[int, dict[str, int]] = {}
    for uid, modulo, n in mix_rows:
        mix_por_user.setdefault(uid, {})[modulo or "—"] = n

    # Cantidad de pacientes por cliente.
    pac_rows = db.execute(
        select(Paciente.usuario_id, func.count()).group_by(Paciente.usuario_id)
    ).all()
    pac_por_user = {uid: n for (uid, n) in pac_rows}

    usuarios = db.scalars(select(Usuario).where(Usuario.activo.is_(True))).all()
    out = []
    for u in usuarios:
        costo_usd, eventos, ult = costo_por_user.get(u.id, (0.0, 0, None))
        costo_ars = (costo_usd or 0.0) * usd_ars
        ingreso = _ingreso_mensual(u)
        margen = ingreso - costo_ars
        out.append({
            "usuario_id": u.id,
            "email": u.email,
            "nombre": u.nombre or "",
            "plan": u.plan,
            "plan_tipo": u.plan_tipo or "",
            "pacientes": pac_por_user.get(u.id, 0),
            "ingreso_mensual_ars": ingreso,
            "costo_periodo_usd": round(costo_usd or 0.0, 4),
            "costo_periodo_ars": round(costo_ars, 2),
            "margen_ars": round(margen, 2),
            "en_perdida": ingreso > 0 and margen < 0,
            "eventos": eventos,
            "mix_modulos": mix_por_user.get(u.id, {}),
            "ultima_actividad": ult.isoformat() if ult else None,
        })
    # Ordenado por margen ascendente: lo que da pérdida primero.
    out.sort(key=lambda r: r["margen_ars"])
    return out


@router.get("/asesor")
def asesor(
    dias: int = 30,
    owner: Usuario = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    """Asesor de rentabilidad: recomendaciones accionables sobre los agregados.

    Siempre devuelve recomendaciones heurísticas (sin depender de la IA) y, si
    hay OPENAI_API_KEY, agrega un análisis en prosa.
    """
    from health_monitor.bi_advisor import narrativa_llm, recomendaciones_heuristicas

    res = resumen(dias=dias, _=owner, db=db)
    cli = clientes(dias=dias, _=owner, db=db)
    recs = recomendaciones_heuristicas(res, cli)
    narrativa = narrativa_llm(res, cli)
    return {
        "dias": dias,
        "recomendaciones": recs,
        "narrativa": narrativa,
        "configurado": narrativa is not None,
    }


class ActivarIn(BaseModel):
    usuario_id: int
    plan_tipo: str = "app"  # app | telefono
    meses: int = 1


@router.post("/activar")
def activar(
    data: ActivarIn,
    owner: Usuario = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    """Activa manualmente la suscripción de un cliente (tras confirmar el pago).

    Cierra el lazo de cobro mientras no esté el webhook de MercadoPago: el dueño
    confirma el pago en MP y acá deja al cliente como pago. Idempotente por diseño
    (vuelve a setear el estado). Queda asentado en AuditLog.
    """
    if data.plan_tipo not in PLANES:
        raise HTTPException(status_code=400, detail="plan_tipo inválido (app|telefono)")
    u = db.get(Usuario, data.usuario_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    meses = max(1, min(36, data.meses))
    u.plan = "activo"
    u.plan_tipo = data.plan_tipo
    u.suscripcion_vence = datetime.now(timezone.utc) + timedelta(days=30 * meses)
    db.add(AuditLog(
        usuario_id=owner.id, accion="activar_suscripcion", recurso="usuario",
        recurso_id=u.id, detalle=f"plan {data.plan_tipo} x{meses}m (manual)",
    ))
    db.commit()
    return {
        "usuario_id": u.id,
        "plan": u.plan,
        "plan_tipo": u.plan_tipo,
        "suscripcion_vence": u.suscripcion_vence.isoformat(),
    }
