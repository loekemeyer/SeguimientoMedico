"""Agente 2: Clínico — extrae métricas estructuradas de la transcripción.

Corre en segundo plano sobre la transcripción acumulada de la llamada y produce
un `ClinicalReadout`. Usa el LLM con salida estructurada cuando hay API key;
si no, cae a un extractor heurístico por regex (útil para tests y degradación).
"""
from __future__ import annotations

import json
import logging
import re

from health_monitor.agents.prompts import CLINICAL_EXTRACTION_PROMPT, RELATO_PROMPT
from health_monitor.schemas.clinical import (
    AdherenceState,
    ClinicalReadout,
    EmotionalRisk,
    MoodState,
)
from shared.config import get_settings

logger = logging.getLogger(__name__)

_SINTOMAS_ALARMA = {
    "dolor de pecho": "dolor de pecho",
    "opresión en el pecho": "dolor de pecho",
    "falta de aire": "disnea",
    "no puedo respirar": "disnea",
    "me ahogo": "disnea",
    "me desmayé": "síncope",
    "desmayo": "síncope",
    "no me sale hablar": "posible ACV",
    "se me dobló la cara": "posible ACV",
}

# Frases que sugieren ideación/intención suicida o autolesión. Se eligen
# deliberadamente ESPECÍFICAS para no confundir modismos ("me muero de hambre",
# "me mata la espalda"). La detección fina la hace el LLM; esto es el respaldo.
_FRASES_RIESGO_SUICIDA = (
    "no quiero vivir", "no quiero seguir viviendo", "ya no quiero vivir",
    "quiero morir", "quiero morirme", "me quiero morir", "ojalá me muera",
    "quiero matarme", "me quiero matar", "voy a matarme", "pensé en matarme",
    "quitarme la vida", "sacarme la vida", "terminar con mi vida", "acabar con mi vida",
    "hacerme daño", "lastimarme", "no vale la pena vivir", "estaría mejor muerto",
    "estaría mejor muerta", "para qué seguir viviendo", "mejor desaparecer",
)
# Frases de crisis/angustia aguda o desesperanza, SIN contenido suicida explícito.
_FRASES_ANGUSTIA_AGUDA = (
    "no aguanto más", "no doy más", "no puedo más", "no puedo seguir así",
    "estoy desesperad", "no le encuentro sentido", "no tiene sentido nada",
    "estoy muy solo", "estoy muy sola", "me siento muy solo", "me siento muy sola",
    "nadie me quiere", "soy una carga", "no le importo a nadie",
    "no paro de llorar", "ataque de pánico", "una crisis",
)


def _detectar_riesgo_emocional(text: str) -> EmotionalRisk:
    """Clasifica la señal de seguridad emocional (conservador: ante la duda, NINGUNO)."""
    if any(frase in text for frase in _FRASES_RIESGO_SUICIDA):
        return EmotionalRisk.RIESGO_SUICIDA
    if any(frase in text for frase in _FRASES_ANGUSTIA_AGUDA):
        return EmotionalRisk.ANGUSTIA_AGUDA
    return EmotionalRisk.NINGUNO


# Frases de que la PERSONA se cayó. Se evita "se me cayó (algo)" = se le cayó un objeto.
_FRASES_CAIDA = (
    "me caí", "me caigo", "me he caído", "me caído", "tuve una caída",
    "sufrí una caída", "una caída", "me fui al piso", "me fui al suelo",
    "terminé en el piso", "terminé en el suelo", "me resbalé y caí", "caí al piso",
    "caí al suelo", "me desplomé",
)


def _detectar_caida(text: str) -> bool:
    """¿La persona reportó una caída propia? Excluye 'se me cayó (un objeto)'."""
    # "se me cayó / se le cayó (algo)" no es una caída de la persona.
    limpio = re.sub(r"se (me|le|nos|te) cay[oó]\w*", " ", text)
    return any(frase in limpio for frase in _FRASES_CAIDA)


def _parse_temperatura(text: str) -> float | None:
    """Extrae temperatura corporal en °C de frases comunes. Conservador.

    Acepta "fiebre de 38", "tengo 38 y medio", "37,5 grados", "38.5°". Descarta
    valores fuera del rango plausible de temperatura corporal (34–44 °C), así no
    confunde "hace 10 días" o "38 cuadras" con una temperatura.
    """
    # "38 y medio" => 38.5 (con contexto de fiebre/temperatura, antes o después).
    m = re.search(r"(?:fiebre|temperatura|febril|grados?)\D{0,15}(\d{2})\s+y\s+medio", text)
    if not m:
        m = re.search(r"(\d{2})\s+y\s+medio\s+(?:de\s+)?(?:fiebre|grados|temperatura)", text)
    if m:
        val = float(m.group(1)) + 0.5
        return val if 34.0 <= val <= 44.0 else None

    # Número (con decimal opcional) junto a fiebre/temperatura, o seguido de "grados/°".
    m = re.search(r"(?:fiebre|temperatura|febril)\D{0,15}(\d{2})(?:[.,](\d))?", text)
    if not m:
        m = re.search(r"(\d{2})(?:[.,](\d))?\s*(?:grados|°)", text)
    if m:
        val = float(f"{m.group(1)}.{m.group(2)}") if m.group(2) else float(m.group(1))
        return val if 34.0 <= val <= 44.0 else None
    return None


def _parse_dolor(text: str) -> int | None:
    """Extrae la intensidad del dolor (0-10) cuando hay una escala explícita.

    Prioriza precisión: solo captura con señal clara de escala ("8 sobre 10",
    "del 1 al 10 un 8", "dolor de 8"), y excluye duraciones ("dolor de 8 días").
    """
    m = re.search(r"\b(\d{1,2})\s*(?:/\s*10|sobre\s*(?:10|diez)|de\s*10)\b", text)
    if not m:
        m = re.search(r"(?:1\s*al\s*10|uno\s*al\s*diez)\D{0,20}(\d{1,2})\b", text)
    if not m:
        m = re.search(
            r"(?:dolor|duele|molestia)\D{0,12}?(?:un|de|en)\s+(\d{1,2})\b"
            r"(?!\s*(?:d[ií]a|semana|hora|año|mes))",
            text,
        )
    if m:
        val = int(m.group(1))
        return val if 0 <= val <= 10 else None
    return None


def extract_readout(paciente_id: int, transcript: str) -> ClinicalReadout:
    """Extrae un ClinicalReadout de la transcripción.

    Intenta el LLM estructurado; ante cualquier falla usa el extractor heurístico.
    """
    settings = get_settings()
    if settings.openai_api_key:
        try:
            return _extract_with_llm(paciente_id, transcript, settings)
        except Exception as exc:  # degradación elegante
            logger.warning("Extracción LLM falló (%s); uso heurística.", exc)
    return _extract_heuristic(paciente_id, transcript)


def _extract_with_llm(paciente_id: int, transcript: str, settings) -> ClinicalReadout:
    from openai import OpenAI  # import perezoso

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": CLINICAL_EXTRACTION_PROMPT},
            {"role": "user", "content": f"paciente_id={paciente_id}\n\n{transcript}"},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    data["paciente_id"] = paciente_id
    return ClinicalReadout.model_validate(data)


def _extract_heuristic(paciente_id: int, transcript: str) -> ClinicalReadout:
    """Extractor de respaldo basado en regex/keywords. Conservador: ante la duda, null."""
    text = transcript.lower()
    readout = ClinicalReadout(paciente_id=paciente_id)

    # Presión "120/80", "120-80", "140 sobre 90", "120 por 80" (formas comunes).
    m = re.search(r"\b(\d{2,3})\s*(?:/|-|sobre|por|con)\s*(\d{2,3})\b", text)
    if m:
        sis, dia = int(m.group(1)), int(m.group(2))
        if 40 <= sis <= 300 and 20 <= dia <= 200:
            readout.presion_sistolica, readout.presion_diastolica = sis, dia

    # Glucemia "glucemia 250", "azúcar en 110".
    mg = re.search(r"(?:glucemia|az[uú]car|glucosa)\D{0,12}(\d{2,3})", text)
    if mg:
        readout.glucemia = int(mg.group(1))

    # Saturación "saturación 92".
    ms = re.search(r"(?:saturaci[oó]n|satura|spo2)\D{0,8}(\d{2,3})", text)
    if ms:
        readout.saturacion_oxigeno = int(ms.group(1))

    # Temperatura "fiebre de 38", "tengo 38 y medio", "37,5 grados".
    temp = _parse_temperatura(text)
    if temp is not None:
        readout.temperatura = temp

    # Dolor "8 sobre 10", "dolor de 8".
    dolor = _parse_dolor(text)
    if dolor is not None:
        readout.dolor = dolor

    # Adherencia.
    if re.search(r"no\s+(la|las|lo|los)?\s*tom", text) or "me olvidé" in text:
        readout.adherencia_medicacion = AdherenceState.NO_TOMO
    elif "tomé todo" in text or "sí, la tomé" in text or "ya tomé" in text:
        readout.adherencia_medicacion = AdherenceState.TOMO_TODO

    # Estado de ánimo.
    if any(w in text for w in ("angustia", "llor", "no doy más", "desesper")):
        readout.estado_animo = MoodState.ANGUSTIADO
    elif any(w in text for w in ("triste", "bajón", "decaíd", "sin ganas")):
        readout.estado_animo = MoodState.DECAIDO
    elif any(w in text for w in ("bien", "tranquil", "contento")):
        readout.estado_animo = MoodState.BIEN

    # Síntomas de alarma.
    for frase, etiqueta in _SINTOMAS_ALARMA.items():
        if frase in text and etiqueta not in readout.sintomas_alarma:
            readout.sintomas_alarma.append(etiqueta)

    # Seguridad emocional (crisis / riesgo suicida).
    readout.riesgo_emocional = _detectar_riesgo_emocional(text)

    # Caída reportada.
    readout.caida_reportada = _detectar_caida(text)

    return readout


def relato_empatico(transcript: str) -> str:
    """Resumen NARRATIVO de lo que contó el paciente (lo emocional/cualitativo).

    Sirve para que el familiar entienda cómo se siente la persona y pueda darle
    contención. Usa el LLM; sin API key o ante una falla devuelve "" (el sistema
    sigue funcionando con el resumen métrico del supervisor).
    """
    settings = get_settings()
    if not (settings.openai_api_key and transcript.strip()):
        return ""
    try:
        from openai import OpenAI  # import perezoso

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[
                {"role": "system", "content": RELATO_PROMPT},
                {"role": "user", "content": transcript},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # degradación elegante
        logger.warning("Relato empático falló (%s).", exc)
        return ""
