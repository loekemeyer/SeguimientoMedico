"""Charla del paciente con su acompañante de IA (texto).

El paciente toca **Hablar** y conversa en lenguaje natural con un acompañante
cálido, paciente y respetuoso. Se apoya en OpenAI Chat Completions vía ``httpx``
(sin el SDK) para mantenerlo liviano y testeable. La voz (Realtime API) se
enchufa aparte; esto cubre el chat de texto, que ya hace usable la app.

Diseño:
- ``construir_system_prompt`` y ``saludo_inicial`` son **puras** (testeables sin red).
- ``responder`` hace la llamada HTTP; ante cualquier falla devuelve un mensaje
  cálido para que la pantalla nunca se "rompa" delante de una persona mayor.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from shared.config import get_settings

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

# Tope de turnos del historial que mandamos (cuida tokens y costo por cliente).
MAX_TURNOS = 24

_FALLBACK_SIN_KEY = (
    "¡Hola! Soy tu acompañante 💛. En un ratito ya vamos a poder charlar "
    "tranquilos. Falta un pasito para activar mi voz."
)
_FALLBACK_ERROR = (
    "Uy, se me cortó un segundo. Estoy acá igual 💛. ¿Me lo contás de nuevo?"
)


@dataclass(frozen=True)
class ContextoPaciente:
    """Lo mínimo para personalizar la charla (todo opcional, con defaults sanos)."""

    nombre: str = ""
    trato: str = "vos"  # "vos" | "usted"
    acompanante_nombre: str = ""
    temas_preferidos: str = ""
    temas_evitar: str = ""


def _conjuga(trato: str) -> dict[str, str]:
    """Devuelve formas verbales según el trato, para no mezclar vos/usted."""
    if trato == "usted":
        return {"vos": "usted", "contame": "cuénteme", "vení": "venga", "estas": "está"}
    return {"vos": "vos", "contame": "contame", "vení": "vení", "estas": "estás"}


def construir_system_prompt(ctx: ContextoPaciente) -> str:
    """Arma el prompt de sistema, en español rioplatense y según el trato."""
    c = _conjuga(ctx.trato)
    persona = (ctx.acompanante_nombre or "").strip() or "un acompañante"
    quien = (ctx.nombre or "").strip()
    saludo_a = f" de {quien}" if quien else ""

    lineas = [
        f"Sos {persona}, un acompañante cálido y paciente{saludo_a}, una persona mayor.",
        f"Hablás en español rioplatense y la tratás de '{c['vos']}'. Nunca cambies el trato.",
        "Tu rol es hacerle compañía: escuchar, charlar de lo que le gusta y, con cariño, "
        f"preguntarle cómo está (ánimo, sueño, si comió, si tomó la medicación, cómo se siente).",
        "Hablás CORTO y SIMPLE: frases breves, una sola pregunta por vez, cero tecnicismos.",
        "Sos cálido, tranquilo y respetuoso. Nunca apurás ni retás.",
        "NO sos médico: no das diagnósticos ni indicás ni cambiás medicación.",
        "Si menciona algo preocupante (dolor en el pecho, falta de aire, una caída, "
        "confusión repentina, sangrado), mantené la calma, no la asustes, y sugerile "
        "avisar a su familia o llamar a su médico o a emergencias.",
    ]
    pref = (ctx.temas_preferidos or "").strip()
    if pref:
        lineas.append(f"Le gusta hablar de: {pref}. Sacá esos temas cuando venga bien.")
    evitar = (ctx.temas_evitar or "").strip()
    if evitar:
        lineas.append(f"Evitá estos temas: {evitar}.")
    return " ".join(lineas)


def saludo_inicial(ctx: ContextoPaciente) -> str:
    """Saludo de apertura (determinístico: rápido, gratis y siempre cordial)."""
    nombre = (ctx.nombre or "").strip()
    coma = f" {nombre}" if nombre else ""
    if ctx.trato == "usted":
        return f"¡Hola{coma}! Qué bueno escucharlo. ¿Cómo viene hoy?"
    return f"¡Hola{coma}! Qué bueno escucharte. ¿Cómo venís hoy?"


def _normalizar_historial(historial: list) -> list[dict]:
    """Filtra el historial a turnos válidos {role, content} para la API."""
    msgs: list[dict] = []
    for h in (historial or [])[-MAX_TURNOS:]:
        if not isinstance(h, dict):
            continue
        rol = h.get("role") or h.get("rol")
        texto = (h.get("content") or h.get("texto") or "").strip()
        if rol in ("user", "usuario") and texto:
            msgs.append({"role": "user", "content": texto})
        elif rol in ("assistant", "acompanante") and texto:
            msgs.append({"role": "assistant", "content": texto})
    return msgs


def responder(mensaje: str, historial: list, ctx: ContextoPaciente) -> tuple[bool, str]:
    """Genera la respuesta del acompañante.

    Devuelve ``(configurado, texto)``. ``configurado`` es ``False`` sólo cuando
    no hay ``OPENAI_API_KEY``: ahí la app muestra el aviso de "falta un pasito".
    """
    settings = get_settings()
    mensaje = (mensaje or "").strip()

    # Apertura de la charla: saludo determinístico (no gasta API).
    if not mensaje and not _normalizar_historial(historial):
        return bool(settings.openai_api_key), saludo_inicial(ctx)

    if not settings.openai_api_key:
        return False, _FALLBACK_SIN_KEY

    messages = [{"role": "system", "content": construir_system_prompt(ctx)}]
    messages.extend(_normalizar_historial(historial))
    if mensaje:
        messages.append({"role": "user", "content": mensaje})

    try:
        resp = httpx.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_chat_model,
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 220,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        texto = (data["choices"][0]["message"]["content"] or "").strip()
        return True, texto or _FALLBACK_ERROR
    except Exception:
        # Nunca rompemos la pantalla del paciente: respondemos con calidez.
        return True, _FALLBACK_ERROR
