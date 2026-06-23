"""Tests de las plantillas de límites por patología (triaje contextual)."""
from health_monitor.schemas.clinical import ClinicalReadout
from health_monitor.services import _limits_from_ficha
from health_monitor.triage import AlertLevel, ClinicalLimits, evaluate
from health_monitor.triage.plantillas import aplicar_plantillas


def test_hta_ajusta_presion():
    out = aplicar_plantillas({}, ["Hipertensión"])
    assert out["sistolica_max"] == 135


def test_codigo_cie10_tambien_aplica():
    assert aplicar_plantillas({}, ["I10"])["sistolica_max"] == 135


def test_diabetes_tipo1_baja_umbral_de_hipoglucemia():
    out = aplicar_plantillas({}, ["Diabetes tipo 1"])
    assert out["glucemia_critica_min"] == 60
    assert out["glucemia_critica_max"] == 250  # específico, no el genérico


def test_sin_patologia_no_cambia_nada():
    assert aplicar_plantillas({}, []) == {}


def test_diabetico_tipo1_glucemia_60_es_roja_vs_amarilla_en_sano():
    merged = aplicar_plantillas({}, ["Diabetes tipo 1"])
    merged["paciente_id"] = 1
    limits_diab = ClinicalLimits.model_validate(merged)
    roja = evaluate(ClinicalReadout(paciente_id=1, glucemia=60), limits_diab)
    assert roja.level == AlertLevel.ROJA
    # En un paciente sin la patología, 60 mg/dL es solo AMARILLA.
    amarilla = evaluate(ClinicalReadout(paciente_id=1, glucemia=60), ClinicalLimits(paciente_id=1))
    assert amarilla.level == AlertLevel.AMARILLA


class _Ficha:
    def __init__(self, patologias, limites):
        self.patologias = patologias
        self.limites = limites


def test_limite_manual_gana_sobre_la_plantilla():
    # HTA aplicaría sistolica_max=135, pero el admin cargó 150 a mano: gana 150.
    limits = _limits_from_ficha(1, _Ficha(["Hipertensión"], {"sistolica_max": 150}))
    assert limits.sistolica_max == 150


def test_plantilla_se_aplica_si_no_hay_manual():
    limits = _limits_from_ficha(1, _Ficha(["Hipertensión"], {}))
    assert limits.sistolica_max == 135
