"""Agente 1: Contenedor — la voz empática del sistema.

En el pipeline de latencia cero, la "personalidad" de este agente se inyecta
como `instructions` de la sesión Realtime (audio-to-audio): el modelo de voz
*es* el contenedor. Este módulo construye esa configuración de sesión y expone
el system prompt para reuso/tests.
"""
from __future__ import annotations

from typing import Any

from health_monitor.agents.prompts import COMPANION_SYSTEM_PROMPT

_LANG_RULE = (
    "\n\nIMPORTANTE: hablá SIEMPRE en español rioplatense (de Argentina), con voz "
    "cálida y cercana. Nunca cambies a inglés ni a otro idioma."
)


# Cómo reacciona el asistente ante algo que la persona NO hizo de su rutina.
# Lo elige el admin por paciente (1=pasivo, 2=recordar, 3=insistir amablemente).
_INSISTENCIA = {
    1: "- Insistencia 1 (pasivo): solo escuchá y registrá. Si no hizo algo, "
       "anotalo sin recordarle ni presionar.",
    2: "- Insistencia 2 (recordar): si no hizo algo, recordáselo UNA vez con "
       "calidez y seguí, sin presionar.",
    3: "- Insistencia 3 (insistir amablemente): si no hizo algo, recordáselo y "
       "animala con mucha amabilidad a hacerlo (por ej. proponé que lo haga ahora), "
       "sin retar ni presionar de más.",
}


def _build_instructions(nombre: str = "", rutina: str = "", nivel_insistencia: int = 2,
                        historial: str = "") -> str:
    """Suma a la persona base el contexto del paciente (nombre, rutina, insistencia, historial)."""
    datos = ["\n\nDATOS DE ESTA LLAMADA:", f"- Persona: {nombre or 'la persona'}."]
    if historial:
        datos.append(
            f"- {historial}. Tenelo en cuenta para abrir la charla y para "
            "repreguntar con tacto lo que haya quedado pendiente la vez pasada."
        )
    if rutina:
        datos.append(f"- Rutina de hoy para repasar, en orden: {rutina}.")
    else:
        datos.append(
            "- No hay rutina cargada: hacé un seguimiento general "
            "(medicación, presión/glucemia, molestias)."
        )
    datos.append(_INSISTENCIA.get(nivel_insistencia, _INSISTENCIA[2]))
    return COMPANION_SYSTEM_PROMPT + _LANG_RULE + "\n".join(datos)


def build_realtime_session_config(
    voice: str = "coral", language: str = "es",
    *, nombre: str = "", rutina: str = "", nivel_insistencia: int = 2, historial: str = "",
) -> dict[str, Any]:
    """Config de sesión para la Realtime API (OpenAI) con la persona del contenedor.

    El formato de audio mulaw/8000 coincide con el de Twilio Media Streams, así
    se evita el resampleo y se minimiza la latencia. `nombre` y `rutina` permiten
    personalizar la llamada con los datos puntuales del paciente.
    """
    # Formato GA de la Realtime API: el audio va anidado en session.audio.{input,output}
    # con audio/pcmu (= g711 u-law, el formato de Twilio). El modelo va en la URL del WS.
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": _build_instructions(nombre, rutina, nivel_insistencia, historial),
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    # silence_duration_ms alto: deja que la persona haga pausas largas
                    # (hasta ~3,5 s) sin que el asistente la interrumpa. Clave para
                    # adultos mayores que hablan pausado.
                    "turn_detection": {"type": "server_vad", "silence_duration_ms": 3500},
                    "transcription": {"model": "whisper-1"},
                },
                "output": {
                    "format": {"type": "audio/pcmu"},
                    "voice": voice,
                    "speed": 0.9,  # levemente pausado pero natural, no robótico (0.25–1.5)
                },
            },
            # Herramienta para que el asistente corte la llamada solo al despedirse.
            "tools": [
                {
                    "type": "function",
                    "name": "end_call",
                    "description": (
                        "Terminá la llamada cuando la conversación ya concluyó. "
                        "Usala SOLO después de haberte despedido en voz."
                    ),
                    "parameters": {"type": "object", "properties": {}},
                },
                {
                    "type": "function",
                    "name": "escalar_a_familia",
                    "description": (
                        "Avisá YA a la familia si detectás algo preocupante que no "
                        "puede esperar (un síntoma de alarma, mucha angustia, una "
                        "caída). Seguí la charla con calma y contención después de usarla."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "motivo": {
                                "type": "string",
                                "description": "Qué detectaste, en una frase corta.",
                            }
                        },
                        "required": ["motivo"],
                    },
                },
            ],
            "tool_choice": "auto",
        },
    }


def opening_line(nombre: str | None = None) -> str:
    """Saludo inicial que abre la llamada con calidez."""
    saludo = f"Hola, {nombre}" if nombre else "Hola"
    return (
        f"{saludo}, soy tu acompañante de siempre. Te llamo para ver cómo venís hoy. "
        "Contame, ¿cómo andás?"
    )
