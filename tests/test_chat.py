"""Tests del módulo de charla del paciente (funciones puras + fallbacks)."""
from health_monitor.chat import (
    ContextoPaciente,
    construir_system_prompt,
    responder,
    saludo_inicial,
)


def test_system_prompt_usa_trato_vos():
    p = construir_system_prompt(ContextoPaciente(nombre="Rosa", trato="vos"))
    assert "Rosa" in p
    assert "'vos'" in p
    assert "no das diagnósticos" in p


def test_system_prompt_usa_trato_usted():
    p = construir_system_prompt(ContextoPaciente(nombre="Don José", trato="usted"))
    assert "'usted'" in p
    assert "'vos'" not in p


def test_system_prompt_incluye_temas():
    p = construir_system_prompt(
        ContextoPaciente(temas_preferidos="fútbol, sus nietos", temas_evitar="política")
    )
    assert "fútbol, sus nietos" in p
    assert "política" in p


def test_saludo_inicial_personalizado():
    assert "Rosa" in saludo_inicial(ContextoPaciente(nombre="Rosa", trato="vos"))
    assert "venís" in saludo_inicial(ContextoPaciente(nombre="Rosa", trato="vos"))
    assert "viene" in saludo_inicial(ContextoPaciente(nombre="Rosa", trato="usted"))


def test_apertura_no_requiere_api(monkeypatch):
    # Sin key y sin mensaje: devuelve el saludo inicial igual (no rompe).
    monkeypatch.setenv("OPENAI_API_KEY", "")
    configurado, texto = responder("", [], ContextoPaciente(nombre="Ana", trato="vos"))
    assert "Ana" in texto


def test_sin_key_y_con_mensaje_devuelve_fallback(monkeypatch):
    import shared.config as cfg

    monkeypatch.setenv("OPENAI_API_KEY", "")
    cfg.get_settings.cache_clear()
    configurado, texto = responder("Hola", [], ContextoPaciente())
    assert configurado is False
    assert "💛" in texto
    cfg.get_settings.cache_clear()
