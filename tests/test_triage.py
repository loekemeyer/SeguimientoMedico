"""Tests del triaje (Agente Supervisor) — el corazón de la lógica de negocio."""
from health_monitor.schemas.clinical import (
    AdherenceState,
    ClinicalReadout,
    EmotionalRisk,
    MoodState,
)
from health_monitor.triage import AlertLevel, ClinicalLimits, evaluate


def _limits() -> ClinicalLimits:
    return ClinicalLimits(paciente_id=1)


def test_paciente_estable_es_verde():
    readout = ClinicalReadout(
        paciente_id=1,
        presion_sistolica=120,
        presion_diastolica=80,
        frecuencia_cardiaca=72,
        glucemia=100,
        saturacion_oxigeno=98,
        adherencia_medicacion=AdherenceState.TOMO_TODO,
        estado_animo=MoodState.BIEN,
    )
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.VERDE


def test_sintoma_de_alarma_dispara_roja():
    readout = ClinicalReadout(paciente_id=1, sintomas_alarma=["dolor de pecho"])
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA
    assert any("dolor de pecho" in r for r in result.reasons)


def test_presion_critica_es_roja():
    readout = ClinicalReadout(paciente_id=1, presion_sistolica=190, presion_diastolica=125)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA


def test_presion_levemente_alta_es_amarilla():
    readout = ClinicalReadout(paciente_id=1, presion_sistolica=150, presion_diastolica=95)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.AMARILLA


def test_no_adherencia_es_amarilla():
    readout = ClinicalReadout(
        paciente_id=1, adherencia_medicacion=AdherenceState.NO_TOMO
    )
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.AMARILLA


def test_animo_angustiado_es_amarilla():
    readout = ClinicalReadout(paciente_id=1, estado_animo=MoodState.ANGUSTIADO)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.AMARILLA


def test_riesgo_suicida_es_roja():
    readout = ClinicalReadout(paciente_id=1, riesgo_emocional=EmotionalRisk.RIESGO_SUICIDA)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA
    assert any("suicida" in r.lower() for r in result.reasons)


def test_angustia_aguda_es_amarilla():
    readout = ClinicalReadout(paciente_id=1, riesgo_emocional=EmotionalRisk.ANGUSTIA_AGUDA)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.AMARILLA


def test_riesgo_suicida_gana_sobre_un_buen_animo():
    # Aunque el ánimo diga "bien", una señal de riesgo manda y es ROJA.
    readout = ClinicalReadout(
        paciente_id=1,
        estado_animo=MoodState.BIEN,
        riesgo_emocional=EmotionalRisk.RIESGO_SUICIDA,
    )
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA


def test_jerarquia_gana_el_nivel_mas_grave():
    # Mezcla de amarilla (no adherencia) + roja (glucemia crítica) => ROJA.
    readout = ClinicalReadout(
        paciente_id=1,
        glucemia=320,
        adherencia_medicacion=AdherenceState.NO_TOMO,
    )
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA
    # Las razones acumulan ambos hallazgos.
    assert len(result.reasons) >= 2


def test_limites_personalizados_se_respetan():
    # Un paciente con sistólica_max=130 marca amarilla en 135.
    limits = ClinicalLimits(paciente_id=2, sistolica_max=130)
    readout = ClinicalReadout(paciente_id=2, presion_sistolica=135)
    result = evaluate(readout, limits)
    assert result.level == AlertLevel.AMARILLA


def test_glucemia_baja_critica_es_roja():
    readout = ClinicalReadout(paciente_id=1, glucemia=45)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA


def test_saturacion_baja_critica_es_roja():
    readout = ClinicalReadout(paciente_id=1, saturacion_oxigeno=88)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA


def test_fiebre_alta_critica_es_roja():
    readout = ClinicalReadout(paciente_id=1, temperatura=39.5)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA


def test_febricula_es_amarilla():
    readout = ClinicalReadout(paciente_id=1, temperatura=38.0)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.AMARILLA


def test_temperatura_normal_es_verde():
    readout = ClinicalReadout(paciente_id=1, temperatura=36.7)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.VERDE


def test_hipotermia_es_roja():
    readout = ClinicalReadout(paciente_id=1, temperatura=34.8)
    result = evaluate(readout, _limits())
    assert result.level == AlertLevel.ROJA
