"""Tests de validación de entrada en los schemas (audit #25)."""
import pytest
from pydantic import ValidationError

from health_monitor.schemas.api import ContactoIn, PacienteIn, RutinaItemIn


def test_paciente_nombre_obligatorio():
    with pytest.raises(ValidationError):
        PacienteIn(nombre="   ", telefono_whatsapp="+5491112345678")


def test_paciente_telefono_invalido():
    with pytest.raises(ValidationError):
        PacienteIn(nombre="Rosa", telefono_whatsapp="123")  # pocos dígitos


def test_paciente_valido_ok():
    p = PacienteIn(nombre="  Rosa  ", telefono_whatsapp="+54 9 11 1234-5678",
                   patologias=["Hipertensión", "  ", "Diabetes"])
    assert p.nombre == "Rosa"  # trim
    assert p.patologias == ["Hipertensión", "Diabetes"]  # saca vacíos


def test_contacto_prioridad_se_clampa():
    c = ContactoIn(nombre="Hija", telefono="+5491112345678", prioridad=9)
    assert c.prioridad == 3
    c2 = ContactoIn(nombre="Hija", telefono="+5491112345678", prioridad=0)
    assert c2.prioridad == 1


def test_rutina_horario_invalido():
    with pytest.raises(ValidationError):
        RutinaItemIn(nombre="Losartán", horario="25:99")


def test_rutina_horario_vacio_ok():
    r = RutinaItemIn(nombre="Losartán", horario="")
    assert r.horario == ""


def test_rutina_nombre_obligatorio():
    with pytest.raises(ValidationError):
        RutinaItemIn(nombre="  ")
