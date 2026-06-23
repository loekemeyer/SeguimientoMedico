"""Agente de Mejora Continua: analiza la evolución del paciente y propone acciones.

A diferencia de los otros agentes (que actúan DURANTE la llamada), este corre
"de fondo" sobre el historial (EvolucionDiaria) y le sugiere al admin/familiar
mejoras de cuidado de forma proactiva: subir la insistencia, avisar al médico,
ajustar la rutina, retomar el seguimiento, etc.

Las reglas son determinísticas y testeables (no dependen del LLM). Encima, una
capa LLM opcional agrega una lectura más rica; degrada con elegancia si no hay
API key (devuelve solo las reglas).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from health_monitor.agents.prompts import IMPROVER_PROMPT
from shared.config import get_settings

logger = logging.getLogger(__name__)

_PRIORIDAD_ORDEN = {"alta": 0, "media": 1, "baja": 2}


def analizar(
    evoluciones: list[dict],
    *,
    nombre: str = "",
    ahora: datetime | None = None,
    usar_llm: bool = True,
) -> list[dict]:
    """Devuelve sugerencias [{'tipo','prioridad','texto'}] a partir del historial.

    `evoluciones`: lista (más reciente primero) de dicts con, al menos:
        {'fecha': datetime|str, 'nivel_alerta': str, 'readout': dict, 'motivos': list}
    """
    ahora = ahora or datetime.now(timezone.utc)
    quien = nombre.strip() or "el paciente"
    out = _reglas(evoluciones, quien, ahora)

    if usar_llm and evoluciones:
        try:
            out += _enriquecer_con_llm(evoluciones, quien)
        except Exception as exc:  # degradación elegante
            logger.warning("Sugerencias LLM fallaron (%s); uso solo reglas.", exc)

    out.sort(key=lambda s: _PRIORIDAD_ORDEN.get(s.get("prioridad"), 1))
    return out


def _reglas(evoluciones: list[dict], quien: str, ahora: datetime) -> list[dict]:
    sugerencias: list[dict] = []
    recientes = evoluciones[:5]

    if not evoluciones:
        return [{
            "tipo": "seguimiento", "prioridad": "baja",
            "texto": f"Todavía no hay seguimientos de {quien}. Hacé la primera "
                     "llamada para empezar a acompañarlo.",
        }]

    # No-adherencia repetida.
    no_tomo = sum(1 for e in recientes
                  if (e.get("readout") or {}).get("adherencia_medicacion") == "no_tomo")
    if no_tomo >= 2:
        sugerencias.append({
            "tipo": "adherencia", "prioridad": "alta",
            "texto": f"{quien} no tomó la medicación en {no_tomo} de las últimas "
                     f"{len(recientes)} llamadas. Subí el nivel de insistencia o "
                     "avisá al médico sobre la adherencia.",
        })

    # Alerta roja reciente.
    if any(e.get("nivel_alerta") == "ROJA" for e in recientes):
        sugerencias.append({
            "tipo": "alerta", "prioridad": "alta",
            "texto": f"Hubo una alerta ROJA reciente con {quien}. Verificá que el "
                     "seguimiento con el médico o la familia haya quedado cerrado.",
        })

    # Presión sistólica en aumento (lista viene más reciente primero).
    sis = [(e.get("readout") or {}).get("presion_sistolica") for e in recientes]
    sis = [s for s in sis if isinstance(s, (int, float))]
    if len(sis) >= 3 and sis[0] > sis[-1] and sis[0] >= 140:
        sugerencias.append({
            "tipo": "presion", "prioridad": "media",
            "texto": f"La presión de {quien} viene en aumento (última {sis[0]} mmHg). "
                     "Conviene consultarlo con su médico.",
        })

    # Ánimo decaído/angustiado repetido.
    animo_bajo = sum(1 for e in recientes
                     if (e.get("readout") or {}).get("estado_animo") in ("decaido", "angustiado"))
    if animo_bajo >= 2:
        sugerencias.append({
            "tipo": "animo", "prioridad": "media",
            "texto": f"El ánimo de {quien} viene decaído en varias llamadas. "
                     "Considerá un acompañamiento o consultarlo con un profesional.",
        })

    # Riesgo emocional grave (señal de seguridad).
    if any((e.get("readout") or {}).get("riesgo_emocional") == "riesgo_suicida"
           for e in recientes):
        sugerencias.append({
            "tipo": "emocional", "prioridad": "alta",
            "texto": f"Se detectó una señal de riesgo emocional grave en {quien}. "
                     "Asegurá compañía y una consulta con salud mental cuanto antes.",
        })
    elif sum(1 for e in recientes
             if (e.get("readout") or {}).get("riesgo_emocional") == "angustia_aguda") >= 2:
        sugerencias.append({
            "tipo": "emocional", "prioridad": "media",
            "texto": f"{quien} mostró angustia marcada en varias llamadas. "
                     "Considerá acompañamiento más frecuente o una consulta profesional.",
        })

    # Caídas (riesgo de lesión y de recurrencia).
    caidas = sum(1 for e in recientes if (e.get("readout") or {}).get("caida_reportada"))
    if caidas >= 2:
        sugerencias.append({
            "tipo": "caidas", "prioridad": "alta",
            "texto": f"{quien} reportó caídas en {caidas} de las últimas llamadas. "
                     "Revisá el entorno (alfombras, iluminación, el baño) y consultá al "
                     "médico por una evaluación de riesgo de caídas.",
        })
    elif caidas == 1:
        sugerencias.append({
            "tipo": "caidas", "prioridad": "media",
            "texto": f"{quien} reportó una caída hace poco. Conviene chequear que no haya "
                     "quedado una molestia y prevenir nuevas caídas en casa.",
        })

    # Sin seguimiento hace varios días.
    ult = _fecha(evoluciones[0].get("fecha"))
    if ult and (ahora - ult).days >= 3:
        sugerencias.append({
            "tipo": "seguimiento", "prioridad": "media",
            "texto": f"Hace {(ahora - ult).days} días que no hay un seguimiento de "
                     f"{quien}. Conviene retomar las llamadas.",
        })

    return sugerencias


def _enriquecer_con_llm(evoluciones: list[dict], quien: str) -> list[dict]:
    """Sugerencia(s) adicional(es) del LLM a partir de un resumen del historial."""
    settings = get_settings()
    if not settings.openai_api_key:
        return []
    from openai import OpenAI  # import perezoso

    resumen = "\n".join(
        f"- {_fecha_txt(e.get('fecha'))}: nivel {e.get('nivel_alerta', '?')}; "
        f"{'; '.join(e.get('motivos') or []) or 'sin novedades'}"
        for e in evoluciones[:8]
    )
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": IMPROVER_PROMPT},
            {"role": "user", "content": f"Paciente: {quien}\nHistorial:\n{resumen}"},
        ],
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    items = data.get("sugerencias", []) if isinstance(data, dict) else []
    out = []
    for it in items[:3]:
        texto = (it or {}).get("texto", "").strip()
        if texto:
            out.append({
                "tipo": (it.get("tipo") or "general"),
                "prioridad": it.get("prioridad") if it.get("prioridad") in _PRIORIDAD_ORDEN else "media",
                "texto": texto,
            })
    return out


def _fecha(v) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _fecha_txt(v) -> str:
    d = _fecha(v)
    return d.strftime("%d/%m") if d else "s/f"
