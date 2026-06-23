"""Plantillas de límites clínicos por patología (triaje contextual).

Ajustan los umbrales de `ClinicalLimits` según las patologías del paciente: un
diabético tipo 1 (riesgo de hipoglucemia) no se tría igual que un prediabético, ni
un EPOC (que tolera saturaciones más bajas) como alguien sano.

Son conservadoras y SIEMPRE las puede sobrescribir el admin con límites manuales
en la ficha (los manuales ganan). Acepta texto ("Hipertensión") o códigos CIE-10.
"""
from __future__ import annotations

import unicodedata


def _norm(s: str) -> str:
    """Minúsculas y sin acentos, para que 'Hipertensión' matchee 'hipertension'."""
    s = (s or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# alias (substring en minúscula) -> overrides de límites. Orden: más específico primero.
PLANTILLAS: dict[str, dict] = {
    "diabetes tipo 1": {"glucemia_min": 80, "glucemia_critica_min": 60, "glucemia_critica_max": 250},
    "e10": {"glucemia_min": 80, "glucemia_critica_min": 60, "glucemia_critica_max": 250},
    "diabetes": {"glucemia_min": 80, "glucemia_critica_min": 60},
    "e11": {"glucemia_min": 80, "glucemia_critica_min": 60},
    "hipertension": {"sistolica_max": 135, "diastolica_max": 85},
    "i10": {"sistolica_max": 135, "diastolica_max": 85},
    "epoc": {"spo2_min": 92, "spo2_critica_min": 88},
    "j44": {"spo2_min": 92, "spo2_critica_min": 88},
    "insuficiencia cardiaca": {"peso_delta_amarillo": 1.5, "spo2_min": 93},
    "i50": {"peso_delta_amarillo": 1.5, "spo2_min": 93},
}


def aplicar_plantillas(base: dict, patologias: list[str]) -> dict:
    """Devuelve `base` con los overrides de las plantillas que apliquen.

    Lo más específico gana: para "Diabetes tipo 1" se aplica esa plantilla y no la
    genérica de "diabetes" (se usa setdefault sobre lo ya puesto).
    """
    out = dict(base)
    textos = [_norm(p) for p in (patologias or [])]
    for clave, overrides in PLANTILLAS.items():
        if any(clave in t for t in textos):
            for k, v in overrides.items():
                out.setdefault(k, v)
    return out
