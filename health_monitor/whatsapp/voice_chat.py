"""Modo WhatsApp por voz: seguimiento ASÍNCRONO por mensajes de audio.

A diferencia de la llamada en vivo (Twilio Media Streams + Realtime API, que se
cobra por minuto de telefonía), acá el seguimiento es por turnos de mensajes de
voz de WhatsApp. Es mucho más económico —no hay minutos de telefonía; solo STT +
LLM + TTS, que cuestan centavos— y el paciente responde cuando quiere.

Flujo de un turno:
    audio del paciente --STT(Whisper)--> texto
        --> next_assistant_message (LLM con el guion del contenedor) --> texto
        --TTS--> audio de respuesta --> WhatsApp

Las integraciones con OpenAI usan import perezoso y degradan con elegancia: el
núcleo (la lógica de turnos) se testea sin red ni API keys.
"""
from __future__ import annotations

import io
import logging

from health_monitor.agents.companion import _build_instructions
from shared.config import get_settings

logger = logging.getLogger(__name__)

# Marca con la que el modelo indica que el seguimiento terminó (la quitamos del texto).
_FIN = "[FIN]"

_CHAT_RULE = (
    "\n\nFORMATO: es una conversación por mensajes de voz de WhatsApp, por turnos "
    "(no en vivo). Mandá UN mensaje corto por turno (1 o 2 frases), con una sola "
    "pregunta. Hablás en español rioplatense, cálido y claro. Cuando el seguimiento "
    f"haya terminado, despedite y poné {_FIN} al final de tu último mensaje."
)


def _system_prompt(nombre: str, rutina: str, nivel_insistencia: int, historial_clinico: str,
                   *, trato: str = "vos", acompanante_nombre: str = "",
                   temas_preferidos: str = "", temas_evitar: str = "") -> str:
    """Reusa el guion del contenedor (rutina, insistencia, historial, personalidad)."""
    return _build_instructions(
        nombre, rutina, nivel_insistencia, historial_clinico,
        trato=trato, acompanante_nombre=acompanante_nombre,
        temas_preferidos=temas_preferidos, temas_evitar=temas_evitar,
    ) + _CHAT_RULE


def next_assistant_message(
    historial: list[dict],
    user_text: str,
    *,
    nombre: str = "",
    rutina: str = "",
    nivel_insistencia: int = 2,
    historial_clinico: str = "",
    trato: str = "vos",
    acompanante_nombre: str = "",
    temas_preferidos: str = "",
    temas_evitar: str = "",
) -> tuple[str, bool]:
    """Genera el próximo mensaje del asistente y si la conversación terminó.

    `historial`: turnos previos como [{"role": "assistant"|"user", "content": str}].
    Devuelve (texto_respuesta, terminado).
    """
    settings = get_settings()
    if not settings.openai_api_key:
        return _fallback_message(historial, trato, acompanante_nombre), False
    try:
        from openai import OpenAI  # import perezoso

        client = OpenAI(api_key=settings.openai_api_key)
        messages = [{"role": "system", "content": _system_prompt(
            nombre, rutina, nivel_insistencia, historial_clinico,
            trato=trato, acompanante_nombre=acompanante_nombre,
            temas_preferidos=temas_preferidos, temas_evitar=temas_evitar)}]
        messages.extend(historial)
        if user_text:
            messages.append({"role": "user", "content": user_text})
        resp = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.6, messages=messages,
        )
        text = (resp.choices[0].message.content or "").strip()
        finished = _FIN in text
        return text.replace(_FIN, "").strip(), finished
    except Exception as exc:  # degradación elegante
        logger.warning("LLM del chat por voz falló (%s); uso fallback.", exc)
        return _fallback_message(historial, trato, acompanante_nombre), False


def _fallback_message(historial: list[dict], trato: str = "vos",
                      acompanante_nombre: str = "") -> str:
    """Respuesta de respaldo cuando no hay LLM (apertura o continuación neutra)."""
    quien = f"soy {acompanante_nombre}" if acompanante_nombre else "le hablo de su acompañamiento"
    if not historial:
        if trato == "usted":
            return f"Hola, {quien}. Cuénteme, ¿cómo viene con su rutina de hoy?"
        return f"Hola, {quien}. Contame, ¿cómo venís con tu rutina de hoy?"
    return ("Gracias por contarme. ¿Hay algo más que quieras comentarme hoy?"
            if trato != "usted"
            else "Gracias por contarme. ¿Hay algo más que quiera comentarme hoy?")


def transcribe(audio_bytes: bytes, *, filename: str = "audio.ogg") -> str:
    """Transcribe audio a texto con Whisper. Devuelve '' si no hay API key o falla."""
    settings = get_settings()
    if not (settings.openai_api_key and audio_bytes):
        return ""
    try:
        from openai import OpenAI  # import perezoso

        client = OpenAI(api_key=settings.openai_api_key)
        buf = io.BytesIO(audio_bytes)
        buf.name = filename
        r = client.audio.transcriptions.create(model="whisper-1", file=buf, language="es")
        return (r.text or "").strip()
    except Exception as exc:
        logger.error("Transcripción (STT) falló: %s", exc)
        return ""


def synthesize(text: str, *, voice: str = "alloy") -> bytes:
    """Genera audio (mp3) del texto con TTS. Devuelve b'' si no hay API key o falla."""
    settings = get_settings()
    if not (settings.openai_api_key and text):
        return b""
    try:
        from openai import OpenAI  # import perezoso

        client = OpenAI(api_key=settings.openai_api_key)
        r = client.audio.speech.create(model="tts-1", voice=voice, input=text)
        return r.content
    except Exception as exc:
        logger.error("Síntesis de voz (TTS) falló: %s", exc)
        return b""
