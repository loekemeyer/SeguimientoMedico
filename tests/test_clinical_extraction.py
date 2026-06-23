"""Tests del extractor heurístico del Agente Clínico (sin LLM)."""
from health_monitor.agents.clinical import _extract_heuristic
from health_monitor.schemas.clinical import AdherenceState, EmotionalRisk, MoodState


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


def test_extrae_temperatura_con_decimal():
    r = _extract_heuristic(1, "Me tomé la fiebre y tengo 38,5.")
    assert r.temperatura == 38.5


def test_extrae_temperatura_y_medio():
    r = _extract_heuristic(1, "Tengo algo de fiebre, 38 y medio.")
    assert r.temperatura == 38.5


def test_extrae_temperatura_grados():
    r = _extract_heuristic(1, "El termómetro marcó 37 grados, todo normal.")
    assert r.temperatura == 37.0


def test_no_confunde_dias_con_temperatura():
    # "hace 10 días" no es una temperatura plausible (fuera de 34–44 °C).
    r = _extract_heuristic(1, "Tengo fiebre hace 10 días, no se me va.")
    assert r.temperatura is None


def test_extrae_dolor_escala():
    r = _extract_heuristic(1, "Me duele la rodilla, como un 8 sobre 10.")
    assert r.dolor == 8


def test_extrae_dolor_de_x():
    r = _extract_heuristic(1, "Tengo un dolor de 7 en la espalda.")
    assert r.dolor == 7


def test_no_confunde_dias_con_dolor():
    # "hace 8 días" es duración, no intensidad.
    r = _extract_heuristic(1, "Me duele la cabeza hace 8 días.")
    assert r.dolor is None


def test_dolor_sin_intensidad_queda_en_none():
    r = _extract_heuristic(1, "Me duele un poco la cabeza, nada grave.")
    assert r.dolor is None


def test_detecta_caida():
    r = _extract_heuristic(1, "Ayer me caí en el baño, pero no me pasó nada grave.")
    assert r.caida_reportada is True


def test_no_confunde_objeto_caido_con_caida():
    # "se me cayó el vaso" no es una caída de la persona.
    r = _extract_heuristic(1, "Se me cayó el vaso al piso y se rompió.")
    assert r.caida_reportada is False


def test_sin_caida_es_false():
    r = _extract_heuristic(1, "Todo bien, salí a caminar un rato.")
    assert r.caida_reportada is False


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
    assert r.riesgo_emocional == EmotionalRisk.NINGUNO


def test_detecta_riesgo_suicida():
    r = _extract_heuristic(1, "Para qué seguir, ya no quiero vivir más.")
    assert r.riesgo_emocional == EmotionalRisk.RIESGO_SUICIDA


def test_detecta_angustia_aguda():
    r = _extract_heuristic(1, "No doy más, me siento muy solo y no paro de llorar.")
    assert r.riesgo_emocional == EmotionalRisk.ANGUSTIA_AGUDA


def test_no_confunde_modismo_con_riesgo_suicida():
    # "me muero de hambre/risa" NO debe disparar riesgo: detección conservadora.
    r = _extract_heuristic(1, "Me muero de hambre, ¿comemos algo? Ja, me mata la espalda.")
    assert r.riesgo_emocional == EmotionalRisk.NINGUNO


def test_relato_empatico_sin_apikey_es_vacio():
    # Sin OPENAI_API_KEY degrada a "" (el sistema sigue con el resumen métrico).
    from health_monitor.agents.clinical import relato_empatico

    assert relato_empatico("Dormí mal y estoy un poco triste.") == ""
