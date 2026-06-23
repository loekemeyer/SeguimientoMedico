"""Tests del Agente de Mejora Continua (reglas, sin LLM)."""
from datetime import datetime, timedelta, timezone

from health_monitor.agents.improver import analizar

_NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _evo(dias_atras: int = 0, nivel: str = "VERDE", **readout) -> dict:
    return {
        "fecha": _NOW - timedelta(days=dias_atras),
        "nivel_alerta": nivel,
        "motivos": [],
        "readout": readout,
    }


def test_sin_evoluciones_sugiere_primera_llamada():
    s = analizar([], nombre="Alejandro", ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "seguimiento" for x in s)


def test_no_adherencia_repetida_es_alta():
    evos = [_evo(0, adherencia_medicacion="no_tomo"),
            _evo(1, adherencia_medicacion="no_tomo")]
    s = analizar(evos, ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "adherencia" and x["prioridad"] == "alta" for x in s)


def test_alerta_roja_reciente():
    s = analizar([_evo(0, nivel="ROJA")], ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "alerta" for x in s)


def test_presion_en_aumento():
    evos = [_evo(0, presion_sistolica=160),
            _evo(1, presion_sistolica=150),
            _evo(2, presion_sistolica=140)]
    s = analizar(evos, ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "presion" for x in s)


def test_sin_seguimiento_hace_dias():
    s = analizar([_evo(5)], ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "seguimiento" for x in s)


def test_riesgo_suicida_sugerencia_alta():
    s = analizar([_evo(0, riesgo_emocional="riesgo_suicida")], ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "emocional" and x["prioridad"] == "alta" for x in s)
    assert any("135" in x["texto"] for x in s)  # incluye la línea de crisis


def test_animo_bajo_sostenido_sugiere_derivacion():
    evos = [_evo(0, estado_animo="decaido"), _evo(1, estado_animo="angustiado"),
            _evo(2, estado_animo="decaido")]
    s = analizar(evos, ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "derivacion" and x["prioridad"] == "alta" for x in s)


def test_caidas_recurrentes_es_alta():
    evos = [_evo(0, caida_reportada=True), _evo(2, caida_reportada=True)]
    s = analizar(evos, ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "caidas" and x["prioridad"] == "alta" for x in s)


def test_una_caida_es_media():
    s = analizar([_evo(0, caida_reportada=True)], ahora=_NOW, usar_llm=False)
    assert any(x["tipo"] == "caidas" and x["prioridad"] == "media" for x in s)


def test_ordena_por_prioridad():
    evos = [_evo(5, adherencia_medicacion="no_tomo"),
            _evo(6, adherencia_medicacion="no_tomo")]
    s = analizar(evos, ahora=_NOW, usar_llm=False)
    orden = {"alta": 0, "media": 1, "baja": 2}
    prioridades = [orden[x["prioridad"]] for x in s]
    assert prioridades == sorted(prioridades)
    # adherencia (alta) debe venir antes que el aviso de seguimiento (media)
    assert s[0]["tipo"] == "adherencia"
