"""Memoria de continuidad por paciente.

Acumula, en lenguaje natural, lo que la persona fue contando a lo largo de las
charlas (familia, gustos, cómo viene de ánimo/sueño, temas abiertos para
repreguntar). El acompañante la **repasa al empezar** cada llamada/charla para
retomar la conversación ("la última vez me contaste de tu nieto, ¿cómo sigue?").

- Es PII: se guarda cifrada en ``Paciente.memoria_enc`` (la capa de servicio
  cifra/descifra).
- Se actualiza al terminar cada llamada, destilando memoria previa + lo nuevo
  con un LLM. Sin ``OPENAI_API_KEY`` cae a un append acotado (igual sirve).
- Acotada en tamaño para no inflar el prompt ni el costo.
"""
from __future__ import annotations

import logging

import httpx

from health_monitor.chat import OPENAI_CHAT_URL
from shared.config import get_settings

logger = logging.getLogger(__name__)

MAX_MEMORIA_CHARS = 1800  # tope del resumen acumulativo


def _fallback(memoria_previa: str, relato: str) -> str:
    """Sin LLM: agrega el relato nuevo y recorta al tope (lo más reciente manda)."""
    nuevo = (memoria_previa or "").strip()
    add = (relato or "").strip()
    if add:
        nuevo = (nuevo + "\n- " + add).strip() if nuevo else "- " + add
    if len(nuevo) > MAX_MEMORIA_CHARS:
        nuevo = nuevo[-MAX_MEMORIA_CHARS:]
    return nuevo


def actualizar_memoria(
    memoria_previa: str,
    relato: str,
    transcript: str = "",
    *,
    nombre: str = "",
    trato: str = "vos",
) -> str:
    """Devuelve la memoria acumulada actualizada con lo de la última charla.

    Best-effort: ante cualquier error o sin API key, usa el fallback (nunca
    rompe el flujo post-llamada).
    """
    relato = (relato or "").strip()
    transcript = (transcript or "").strip()
    if not relato and not transcript:
        return (memoria_previa or "").strip()

    settings = get_settings()
    if not settings.openai_api_key:
        return _fallback(memoria_previa, relato)

    quien = (nombre or "la persona").strip()
    prompt = (
        "Sos el asistente que mantiene una MEMORIA de continuidad sobre una persona "
        f"mayor ({quien}) a la que acompañamos con llamadas. Te paso la memoria "
        "acumulada hasta ahora y lo que surgió en la última charla. Devolvé una "
        "memoria ACTUALIZADA, breve y en viñetas, que sirva para retomar la próxima "
        "vez. Incluí: datos personales que mencione (familia, nombres, gustos, "
        "rutinas), estado de ánimo/salud reciente, y TEMAS ABIERTOS para "
        "repreguntar con tacto. Fusioná y sacá lo repetido o ya resuelto. No "
        "inventes. Máximo ~1500 caracteres. Español rioplatense, neutral.\n\n"
        f"MEMORIA ACTUAL:\n{(memoria_previa or '(vacía)').strip()}\n\n"
        f"ÚLTIMA CHARLA (relato):\n{relato}\n\n"
        f"TRANSCRIPCIÓN (si ayuda):\n{transcript[:3000]}"
    )
    try:
        resp = httpx.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_chat_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 600,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        texto = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if not texto:
            return _fallback(memoria_previa, relato)
        return texto[:MAX_MEMORIA_CHARS]
    except Exception as exc:
        logger.warning("No se pudo actualizar la memoria con IA (%s); uso fallback.", exc)
        return _fallback(memoria_previa, relato)


def bloque_para_prompt(memoria: str) -> str:
    """Formatea la memoria como bloque para inyectar en el prompt del acompañante."""
    memoria = (memoria or "").strip()
    if not memoria:
        return ""
    return (
        "LO QUE YA SABÉS DE LA PERSONA (memoria de charlas anteriores; repasala "
        "para retomar con naturalidad y repreguntar lo que quedó abierto):\n"
        f"{memoria}"
    )
