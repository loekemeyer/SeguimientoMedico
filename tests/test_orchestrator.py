"""Tests de la orquestación post-llamada (runner secuencial / LangGraph)."""
from health_monitor.agents.orchestrator import CallState, run_post_call
from health_monitor.triage import AlertLevel, ClinicalLimits


def _state(transcript: str) -> CallState:
    return CallState(
        paciente_id=1,
        limits=ClinicalLimits(paciente_id=1),
        paciente_nombre="Alejandro Loekemeyer",
        contactos=[{"telefono": "+5491155550000", "label": "Thomas (hijo)",
                    "recibe_alertas": True}],
        ficha_resumen="Paciente 1. Patologías: hipertensión.",
        transcript=transcript,
    )


def test_post_call_estable_es_verde():
    state = _state("Hola, todo bien, tranquilo, ya tomé la pastilla.")
    out = run_post_call(state)
    assert out.finished is True
    assert out.triage is not None
    assert out.triage.level == AlertLevel.VERDE
    assert out.interrupted is False


def test_post_call_sintoma_alarma_es_roja_e_interrumpe():
    state = _state("Tengo un dolor de pecho muy fuerte y me falta el aire.")
    out = run_post_call(state)
    assert out.triage.level == AlertLevel.ROJA
    assert out.interrupted is True
    # Se intentó disparar alertas (en modo dev quedan registradas, no enviadas).
    assert out.alerts_dispatched is not None


def test_post_call_no_adherencia_es_amarilla():
    state = _state("Me olvidé de tomar la pastilla hoy, perdón.")
    out = run_post_call(state)
    assert out.triage.level == AlertLevel.AMARILLA
