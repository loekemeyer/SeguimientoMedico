"""Asesor de rentabilidad del dueño.

Toma los agregados del panel BI (resumen + por-cliente) y produce
recomendaciones CONCRETAS para mejorar la rentabilidad. Dos capas:

1. ``recomendaciones_heuristicas``: reglas determinísticas (puras, testeables)
   que funcionan SIN OpenAI — el panel siempre da valor.
2. ``narrativa_llm``: opcional, enriquece con un análisis en prosa si hay
   OPENAI_API_KEY.

Trabaja sólo con números agregados: nunca con PII ni con el contenido de las
charlas. Ver docs/ARQUITECTURA_ESCALA.md §6.4.
"""
from __future__ import annotations

import json

import httpx

from health_monitor.chat import OPENAI_CHAT_URL
from shared.config import get_settings

# Umbrales (ajustables) de las heurísticas.
DIAS_INACTIVO = 14
COSTO_CHAT_ALTO_USD = 3.0  # costo de chat por cliente/mes que enciende alerta


def recomendaciones_heuristicas(resumen: dict, clientes: list[dict]) -> list[dict]:
    """Reglas de negocio que no dependen de la IA. Devuelve [{prioridad, titulo, detalle}]."""
    recs: list[dict] = []

    en_perdida = [c for c in clientes if c.get("en_perdida")]
    if en_perdida:
        nombres = ", ".join(c.get("email", "?") for c in en_perdida[:5])
        recs.append({
            "prioridad": "alta",
            "titulo": f"{len(en_perdida)} cliente(s) dan pérdida",
            "detalle": (
                f"Estos clientes cuestan más de lo que pagan: {nombres}. "
                "Revisá si conviene subirlos de plan, acotar el uso o renegociar."
            ),
        })

    # Plan App que consume como Teléfono (mucho costo de chat).
    app_caros = [
        c for c in clientes
        if c.get("plan_tipo") == "app" and c.get("costo_periodo_usd", 0) >= COSTO_CHAT_ALTO_USD
    ]
    if app_caros:
        recs.append({
            "prioridad": "media",
            "titulo": f"{len(app_caros)} cliente(s) App con uso intensivo",
            "detalle": (
                "Usan el chat mucho más que el promedio. Son candidatos a "
                "ofrecerles el plan Teléfono (más ingreso) o a revisar el "
                "max_tokens del chat para acotar el costo."
            ),
        })

    inactivos = [c for c in clientes if c.get("ultima_actividad") is None]
    if inactivos:
        recs.append({
            "prioridad": "media",
            "titulo": f"{len(inactivos)} cliente(s) sin actividad reciente",
            "detalle": (
                "No registran uso en el período. Riesgo de baja: contactalos para "
                "reactivarlos antes de que cancelen."
            ),
        })

    trials = resumen.get("clientes_trial", 0)
    if trials:
        recs.append({
            "prioridad": "media",
            "titulo": f"{trials} cuenta(s) en prueba",
            "detalle": (
                "Oportunidad de conversión: acompañalas en estos días con un "
                "mensaje cálido y mostrales el valor antes de que venza el trial."
            ),
        })

    margen = resumen.get("margen_ars", 0)
    if margen < 0:
        recs.append({
            "prioridad": "alta",
            "titulo": "El negocio está en pérdida en el período",
            "detalle": (
                "El costo total supera al ingreso. Priorizá convertir trials a "
                "pago y revisar los clientes en pérdida de arriba."
            ),
        })
    elif resumen.get("clientes_activos", 0) == 0 and resumen.get("clientes_total", 0) > 0:
        recs.append({
            "prioridad": "alta",
            "titulo": "Todavía no hay clientes pagos",
            "detalle": "Enfocate en convertir las cuentas de prueba a un plan pago.",
        })

    if not recs:
        recs.append({
            "prioridad": "baja",
            "titulo": "Todo sano por ahora",
            "detalle": "No hay focos de pérdida ni inactividad. Seguí sumando clientes.",
        })
    return recs


def narrativa_llm(resumen: dict, clientes: list[dict]) -> str | None:
    """Análisis en prosa con OpenAI (opcional). None si no hay key o falla."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    # Mandamos sólo agregados (sin PII más allá del email, que es del dueño).
    datos = {
        "resumen": resumen,
        "clientes": [
            {k: c.get(k) for k in (
                "email", "plan", "plan_tipo", "ingreso_mensual_ars",
                "costo_periodo_ars", "margen_ars", "en_perdida", "mix_modulos")}
            for c in clientes[:40]
        ],
    }
    prompt = (
        "Sos un asesor de negocio de un SaaS de monitoreo de salud para adultos "
        "mayores. Te paso los números de rentabilidad (ingreso en ARS, costo "
        "estimado, margen, mix de uso por cliente). Dame un análisis BREVE y "
        "accionable (máximo 6 puntos) para mejorar la rentabilidad: qué clientes "
        "atender, qué planes mover, dónde bajar costos, qué oportunidades hay. "
        "Sé concreto y directo, en español rioplatense.\n\n"
        f"DATOS:\n{json.dumps(datos, ensure_ascii=False)}"
    )
    try:
        resp = httpx.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_chat_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 500,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None
