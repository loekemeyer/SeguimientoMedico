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


_SCREENING_ANIMO = (
    "\n- ATENCIÓN: el ánimo de la persona viene bajo en las últimas llamadas. Con MUCHO "
    "tacto y SIN que parezca un cuestionario, explorá cómo está anímicamente: cómo viene "
    "durmiendo, si tiene ganas de hacer las cosas que le gustan, si se siente acompañada "
    "o sola, si la nota más desganada o sin esperanza. Escuchá más de lo que preguntás, "
    "una sola pregunta por vez, sin interrogar ni presionar."
)


def _build_instructions(nombre: str = "", rutina: str = "", nivel_insistencia: int = 2,
                        historial: str = "", *, trato: str = "vos",
                        acompanante_nombre: str = "", temas_preferidos: str = "",
                        temas_evitar: str = "", explorar_animo: bool = False,
                        memoria: str = "") -> str:
    """Suma a la persona base el contexto y la personalización del paciente."""
    datos = ["\n\nDATOS DE ESTA LLAMADA:", f"- Persona: {nombre or 'la persona'}."]
    if memoria and memoria.strip():
        from health_monitor.memoria import bloque_para_prompt
        datos.append("\n" + bloque_para_prompt(memoria))
    if explorar_animo:
        datos.append(_SCREENING_ANIMO)
    if acompanante_nombre:
        datos.append(f"- Te presentás como {acompanante_nombre}, del equipo que lo acompaña.")
    if trato == "usted":
        datos.append("- Tratá a la persona de USTED (con respeto y calidez).")
    else:
        datos.append("- Tratá a la persona de VOS (cercano y cálido).")
    if temas_preferidos:
        datos.append(
            f"- Temas que le gustan (usalos para charlar con naturalidad): {temas_preferidos}."
        )
    if temas_evitar:
        datos.append(f"- Temas a EVITAR (no los saques): {temas_evitar}.")
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
    speed: float = 0.9, trato: str = "vos", acompanante_nombre: str = "",
    temas_preferidos: str = "", temas_evitar: str = "", explorar_animo: bool = False,
    memoria: str = "",
) -> dict[str, Any]:
    """Config de sesión para la Realtime API (OpenAI) con la persona del contenedor.

    El formato de audio mulaw/8000 coincide con el de Twilio Media Streams, así
    se evita el resampleo y se minimiza la latencia. `voice`, `speed`, `trato`,
    `acompanante_nombre` y los `temas_*` personalizan la voz y el estilo por paciente.
    """
    # Formato GA de la Realtime API: el audio va anidado en session.audio.{input,output}
    # con audio/pcmu (= g711 u-law, el formato de Twilio). El modelo va en la URL del WS.
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": _build_instructions(
                nombre, rutina, nivel_insistencia, historial,
                trato=trato, acompanante_nombre=acompanante_nombre,
                temas_preferidos=temas_preferidos, temas_evitar=temas_evitar,
                explorar_animo=explorar_animo, memoria=memoria,
            ),
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
                    "speed": speed,  # configurable por paciente (0.25–1.5)
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


def opening_line(nombre: str | None = None, acompanante_nombre: str = "") -> str:
    """Saludo inicial que abre la llamada con calidez (humano, nunca como un bot)."""
    saludo = f"Hola, {nombre}" if nombre else "Hola"
    quien = f"soy {acompanante_nombre}" if acompanante_nombre else "soy tu acompañante de siempre"
    return (
        f"{saludo}, {quien}. Te llamo para ver cómo venís hoy. "
        "Contame, ¿cómo andás?"
    )
