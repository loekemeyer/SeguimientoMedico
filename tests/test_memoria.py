"""Tests de la memoria de continuidad (funciones puras + fallback sin API)."""
import shared.config as cfg
from health_monitor.memoria import (
    MAX_MEMORIA_CHARS,
    actualizar_memoria,
    bloque_para_prompt,
)


def test_bloque_vacio_si_no_hay_memoria():
    assert bloque_para_prompt("") == ""
    assert bloque_para_prompt("   ") == ""


def test_bloque_incluye_memoria():
    b = bloque_para_prompt("- Tiene un nieto, Tomás.")
    assert "Tomás" in b
    assert "memoria" in b.lower()


def test_fallback_sin_api_acumula(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    cfg.get_settings.cache_clear()
    m = actualizar_memoria("", "Hoy contó que durmió mal.", nombre="Rosa")
    assert "durmió mal" in m
    m2 = actualizar_memoria(m, "Le duele la rodilla.", nombre="Rosa")
    assert "rodilla" in m2
    assert "durmió mal" in m2  # conserva lo anterior
    cfg.get_settings.cache_clear()


def test_fallback_respeta_tope(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    cfg.get_settings.cache_clear()
    largo = "x" * 5000
    m = actualizar_memoria(largo, "algo nuevo", nombre="Rosa")
    assert len(m) <= MAX_MEMORIA_CHARS
    cfg.get_settings.cache_clear()


def test_sin_nada_devuelve_memoria_previa(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    cfg.get_settings.cache_clear()
    assert actualizar_memoria("memoria vieja", "", "") == "memoria vieja"
    cfg.get_settings.cache_clear()
