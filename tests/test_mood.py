"""Tests del análisis longitudinal del ánimo (continuidad emocional entre llamadas)."""
from datetime import datetime, timezone

from health_monitor.agents.mood import tendencia_animo


def _evo(dia: int, animo: str | None) -> dict:
    readout = {"estado_animo": animo} if animo is not None else {}
    return {"fecha": datetime(2026, 6, dia, tzinfo=timezone.utc), "readout": readout}


def test_sin_datos_suficientes_no_hay_tendencia():
    assert tendencia_animo([]) == ""
    assert tendencia_animo([_evo(10, "bien")]) == ""  # un solo punto


def test_detecta_mejora():
    # Lista MÁS RECIENTE PRIMERO: 18 bien (nuevo) ... 12 angustiado (viejo).
    evos = [_evo(18, "bien"), _evo(15, "decaido"), _evo(12, "angustiado")]
    out = tendencia_animo(evos)
    assert "viene mejorando" in out
    # Se muestra de la más vieja a la más nueva.
    assert out.index("12/06") < out.index("18/06")


def test_detecta_baja():
    evos = [_evo(18, "angustiado"), _evo(12, "bien")]
    out = tendencia_animo(evos)
    assert "viene en baja" in out


def test_se_mantiene():
    evos = [_evo(18, "estable"), _evo(12, "estable")]
    assert "se mantiene" in tendencia_animo(evos)


def test_ignora_animo_desconocido():
    # 'desconocido' (o ausente) no cuenta como punto: solo queda uno válido -> "".
    evos = [_evo(18, "bien"), _evo(15, None), _evo(12, "desconocido")]
    assert tendencia_animo(evos) == ""


def test_screening_se_gatilla_con_animo_bajo_repetido():
    from health_monitor.agents.mood import necesita_screening
    evos = [_evo(18, "decaido"), _evo(15, "angustiado"), _evo(12, "bien")]
    assert necesita_screening(evos) is True


def test_screening_no_se_gatilla_con_buen_animo():
    from health_monitor.agents.mood import necesita_screening
    evos = [_evo(18, "bien"), _evo(15, "bien"), _evo(12, "estable")]
    assert necesita_screening(evos) is False


def test_screening_se_gatilla_con_riesgo_emocional():
    from health_monitor.agents.mood import necesita_screening
    evos = [{"readout": {"estado_animo": "bien", "riesgo_emocional": "angustia_aguda"}}]
    assert necesita_screening(evos) is True
