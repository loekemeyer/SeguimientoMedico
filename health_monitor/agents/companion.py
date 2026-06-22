"""Agente 1: Contenedor — la voz empática del sistema.

En el pipeline de latencia cero, la "personalidad" de este agente se inyecta
como `instructions` de la sesión Realtime (audio-to-audio): el modelo de voz
*es* el contenedor. Este módulo construye esa configuración de sesión y expone
el system prompt para reuso/tests.
"""
from __future__ import annotations

from typing import Any

from health_monitor.agents.prompts import COMPANION_SYSTEM_PROMPT


def build_realtime_session_config(
    voice: str = "alloy", language: str = "es",
) -> dict[str, Any]:
    """Config de sesión para la Realtime API (OpenAI) con la persona del contenedor.

    El formato de audio mulaw/8000 coincide con el de Twilio Media Streams, así
    se evita el resampleo y se minimiza la latencia.
    """
    return {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"],
            "instructions": COMPANION_SYSTEM_PROMPT,
            "voice": voice,
            "input_audio_format": "g711_ulaw",   # mulaw/8000 de Twilio
            "output_audio_format": "g711_ulaw",
            "input_audio_transcription": {"model": "whisper-1", "language": language},
            "turn_detection": {"type": "server_vad", "silence_duration_ms": 600},
            "temperature": 0.7,
        },
    }


def opening_line(nombre: str | None = None) -> str:
    """Saludo inicial que abre la llamada con calidez."""
    saludo = f"Hola {nombre}" if nombre else "Hola, ¿cómo está?"
    return (
        f"{saludo}, le hablo de su servicio de acompañamiento. "
        "Lo/la llamo para ver cómo viene su día. ¿Cómo se está sintiendo hoy?"
    )
