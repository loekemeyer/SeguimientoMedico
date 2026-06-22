"""Agente 2: Clínico — extrae métricas estructuradas de la transcripción.

Corre en segundo plano sobre la transcripción acumulada de la llamada y produce
un `ClinicalReadout`. Usa el LLM con salida estructurada cuando hay API key;
si no, cae a un extractor heurístico por regex (útil para tests y degradación).
"""
from __future__ import annotations

import json
import logging
import re

from health_monitor.agents.prompts import CLINICAL_EXTRACTION_PROMPT
from health_monitor.schemas.clinical import (
    AdherenceState,
    ClinicalReadout,
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

    return readout
