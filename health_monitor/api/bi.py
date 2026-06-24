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


@router.get("/diagnostico")
def diagnostico(owner: Usuario = Depends(require_owner)) -> dict:
    """Qué integraciones están configuradas (sin exponer secretos): para saber por
    qué 'no anda' la llamada o el WhatsApp. Sólo el dueño."""
    s = get_settings()
    return {
        "twilio_account_sid": bool(s.twilio_account_sid),
        "twilio_auth_token": bool(s.twilio_auth_token),
        "twilio_voice_from": s.twilio_voice_from or "(vacío)",   # número de voz, no es secreto
        "twilio_whatsapp_from": s.twilio_whatsapp_from or "(vacío)",
        "public_base_url": s.public_base_url or "(vacío)",
        "openai_api_key": bool(s.openai_api_key),
        "llamada_de_voz_lista": bool(
            s.twilio_account_sid and s.twilio_auth_token and s.twilio_voice_from and s.public_base_url
        ),
        "whatsapp_listo": bool(s.twilio_account_sid and s.twilio_auth_token),
        "chat_ia_listo": bool(s.openai_api_key),
    }


@router.get("/probar-openai")
def probar_openai(owner: Usuario = Depends(require_owner)) -> dict:
    """Diagnóstico de OpenAI: ¿la key es válida? ¿la cuenta tiene el modelo de voz?

    Es lo que destraba la llamada con IA: si el modelo Realtime no está disponible
    para esta key, la llamada conecta pero dice 'application error'.
    """
    import httpx

    s = get_settings()
    if not s.openai_api_key:
        return {"ok": False, "detalle": "OPENAI_API_KEY no está configurada."}
    try:
        r = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {s.openai_api_key}"}, timeout=15.0,
        )
    except Exception as exc:
        return {"ok": False, "detalle": f"No se pudo contactar a OpenAI: {exc}"}
    if r.status_code == 401:
        return {"ok": False, "detalle": "La OPENAI_API_KEY es inválida o está vencida (401)."}
    if r.status_code != 200:
        return {"ok": False, "detalle": f"OpenAI respondió {r.status_code}: {r.text[:200]}"}

    ids = {m.get("id") for m in r.json().get("data", [])}
    rt = s.openai_realtime_model
    realtime_disponibles = sorted(i for i in ids if i and "realtime" in i)
    rt_ok = rt in ids
    return {
        "ok": True,
        "key_valida": True,
        "modelo_realtime_configurado": rt,
        "modelo_realtime_disponible": rt_ok,
        "realtime_disponibles_en_tu_cuenta": realtime_disponibles,
        "modelo_chat_configurado": s.openai_chat_model,
        "modelo_chat_disponible": s.openai_chat_model in ids,
        "detalle": (
            "Key OK y el modelo de voz está disponible." if rt_ok else
            (f"Key OK, pero tu cuenta NO tiene '{rt}'. Por eso la llamada dice "
             f"'application error'. Cambiá OPENAI_REALTIME_MODEL a uno de: "
             f"{realtime_disponibles or 'ninguno (tu cuenta no tiene acceso a Realtime)'}.")
        ),
    }


class ProbarContactoIn(BaseModel):
    telefono: str


@router.post("/probar-whatsapp")
def probar_whatsapp(
    data: ProbarContactoIn,
    owner: Usuario = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    """Manda un WhatsApp de prueba y devuelve el resultado EXACTO de Twilio.

    Sirve para diagnosticar por qué 'no llega' (sandbox sin join, número no
    verificado, credenciales). Sólo el dueño.
    """
    from shared.notifications import enviar_whatsapp_detallado

    tel = (data.telefono or "").strip()
    if not tel:
        raise HTTPException(status_code=400, detail="Pasá un teléfono (ej. +5491112345678)")
    return enviar_whatsapp_detallado(tel, "Mensaje de prueba de SeguimientoMedico ✅. Si lo recibís, ¡WhatsApp está andando!")


@router.post("/probar-llamada")
def probar_llamada(
    data: ProbarContactoIn,
    owner: Usuario = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict:
    """Intenta una llamada de prueba y devuelve el resultado EXACTO de Twilio."""
    s = get_settings()
    faltan = [n for n, ok in (
        ("TWILIO_ACCOUNT_SID", s.twilio_account_sid),
        ("TWILIO_AUTH_TOKEN", s.twilio_auth_token),
        ("TWILIO_VOICE_FROM", s.twilio_voice_from),
        ("PUBLIC_BASE_URL", s.public_base_url),
    ) if not ok]
    if faltan:
        return {"ok": False, "detalle": f"Falta configurar en el servidor: {', '.join(faltan)}."}
    tel = (data.telefono or "").strip()
    if not tel:
        raise HTTPException(status_code=400, detail="Pasá un teléfono (ej. +5491112345678)")
    try:
        from twilio.rest import Client
        client = Client(s.twilio_account_sid, s.twilio_auth_token)
        call = client.calls.create(
            to=tel, from_=s.twilio_voice_from,
            url=f"{s.public_base_url.rstrip('/')}/twilio/voice?paciente_id=0",
        )
        return {"ok": True, "call_sid": call.sid, "estado": getattr(call, "status", ""),
                "detalle": "Llamada creada. Si no suena, verificá que el número esté verificado en Twilio (cuenta de prueba)."}
    except Exception as exc:
        code = getattr(exc, "code", None)
        ayuda = " En cuenta de prueba sólo se puede llamar a números verificados." if code == 21219 else ""
        return {"ok": False, "error_code": code, "detalle": f"{exc}{ayuda}"}


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
