"""Tests de la programación de llamadas (horario, zona y días)."""
from datetime import datetime, timezone

from health_monitor.db.models import Paciente
from health_monitor.scheduler import debe_llamar


def _paciente(**kw) -> Paciente:
    base = dict(
        activo=True, llamada_activa=True, consentimiento_firmado=True,
        llamada_hora="10:00", llamada_zona="America/Argentina/Buenos_Aires",
        llamada_dias=[],
    )
    base.update(kw)
    p = Paciente()
    for k, v in base.items():
        setattr(p, k, v)
    return p


# 13:00 UTC == 10:00 en Buenos Aires (UTC-3)
_UTC_10_BA = datetime(2026, 6, 22, 13, 0, tzinfo=timezone.utc)  # lunes


def test_llama_en_la_hora_programada():
    assert debe_llamar(_paciente(), _UTC_10_BA) is True


def test_no_llama_fuera_de_hora():
    fuera = datetime(2026, 6, 22, 18, 0, tzinfo=timezone.utc)  # 15:00 BA
    assert debe_llamar(_paciente(), fuera) is False


def test_respeta_ventana_de_tolerancia():
    casi = datetime(2026, 6, 22, 13, 4, tzinfo=timezone.utc)  # 10:04 BA
    assert debe_llamar(_paciente(), casi) is True
    tarde = datetime(2026, 6, 22, 13, 10, tzinfo=timezone.utc)  # 10:10 BA
    assert debe_llamar(_paciente(), tarde) is False


def test_no_llama_si_desactivada():
    assert debe_llamar(_paciente(llamada_activa=False), _UTC_10_BA) is False


def test_no_llama_sin_consentimiento():
    assert debe_llamar(_paciente(consentimiento_firmado=False), _UTC_10_BA) is False


def test_respeta_dias_de_la_semana():
    # _UTC_10_BA es lunes (weekday 0). Si solo se llaman martes/jueves (1,3), no llama.
    assert debe_llamar(_paciente(llamada_dias=[1, 3]), _UTC_10_BA) is False
    assert debe_llamar(_paciente(llamada_dias=[0, 2, 4]), _UTC_10_BA) is True


def test_respeta_zona_horaria():
    # Mismo instante, pero configurado en zona de México (UTC-6): 07:00 allá, no 10:00.
    p = _paciente(llamada_zona="America/Mexico_City")
    assert debe_llamar(p, _UTC_10_BA) is False
