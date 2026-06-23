"""Tests del extractor heurístico del Agente Clínico (sin LLM)."""
from health_monitor.agents.clinical import _extract_heuristic
from health_monitor.schemas.clinical import AdherenceState, MoodState


def test_extrae_presion():
    r = _extract_heuristic(1, "Hoy me tomé la presión y me dio 140 sobre 90.")
    assert r.presion_sistolica == 140
    assert r.presion_diastolica == 90


def test_extrae_glucemia():
    r = _extract_heuristic(1, "La glucemia me dio 250 esta mañana.")
    assert r.glucemia == 250


def test_extrae_saturacion():
    r = _extract_heuristic(1, "El oxímetro marcó saturación 92.")
    assert r.saturacion_oxigeno == 92


def test_detecta_no_adherencia():
    r = _extract_heuristic(1, "Uy, me olvidé de tomar la pastilla hoy.")
    assert r.adherencia_medicacion == AdherenceState.NO_TOMO


def test_detecta_animo_angustiado():
    r = _extract_heuristic(1, "Estoy muy angustiado, me la paso llorando.")
    assert r.estado_animo == MoodState.ANGUSTIADO


def test_detecta_sintoma_de_alarma():
    r = _extract_heuristic(1, "Tengo un dolor de pecho fuerte desde hace un rato.")
    assert "dolor de pecho" in r.sintomas_alarma


def test_conservador_sin_datos():
    r = _extract_heuristic(1, "Hola, todo tranquilo por acá, charlando nomás.")
    assert r.presion_sistolica is None
    assert r.glucemia is None
    assert r.sintomas_alarma == []


def test_relato_empatico_sin_apikey_es_vacio():
    # Sin OPENAI_API_KEY degrada a "" (el sistema sigue con el resumen métrico).
    from health_monitor.agents.clinical import relato_empatico

    assert relato_empatico("Dormí mal y estoy un poco triste.") == ""
