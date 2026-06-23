"""Análisis longitudinal del ánimo: da continuidad emocional entre llamadas.

A partir del historial (EvolucionDiaria.readout), arma un resumen de la TENDENCIA
del estado de ánimo para que el acompañante pueda retomar con sensibilidad ("la
última vez te noté más bajón…") en lugar de empezar de cero cada llamada.

Es lógica pura y testeable: no toca la base ni el LLM.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Escala ordinal del ánimo, para inferir si la persona mejora o empeora.
_VALOR_ANIMO = {"bien": 2, "estable": 1, "decaido": -1, "angustiado": -2}
_ETIQUETA = {
    "bien": "bien",
    "estable": "estable",
    "decaido": "decaído",
    "angustiado": "angustiado",
}


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


def tendencia_animo(evoluciones: list[dict], *, max_puntos: int = 5) -> str:
    """Resumen de la trayectoria del ánimo (de la más vieja a la más nueva).

    `evoluciones`: lista MÁS RECIENTE PRIMERO, cada una con 'fecha' y 'readout'
    (un dict con 'estado_animo'). Devuelve "" si no hay al menos dos puntos con
    ánimo conocido (no hay tendencia que mostrar).
    """
    puntos: list[tuple[datetime | None, str]] = []
    for e in evoluciones[:max_puntos]:
        animo = (e.get("readout") or {}).get("estado_animo")
        if animo in _VALOR_ANIMO:
            puntos.append((_fecha(e.get("fecha")), animo))
    if len(puntos) < 2:
        return ""

    puntos.reverse()  # de la más vieja a la más nueva
    tramo = " → ".join(
        f"{f.strftime('%d/%m') if f else 's/f'} {_ETIQUETA[a]}" for f, a in puntos
    )
    delta = _VALOR_ANIMO[puntos[-1][1]] - _VALOR_ANIMO[puntos[0][1]]
    rumbo = "viene mejorando" if delta > 0 else "viene en baja" if delta < 0 else "se mantiene"
    return f"Ánimo en las últimas llamadas: {tramo} ({rumbo})"
