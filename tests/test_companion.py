"""Tests de la configuración de la sesión Realtime (voz, rutina, insistencia)."""
from health_monitor.agents.companion import build_realtime_session_config


def _session(**kw):
    return build_realtime_session_config(**kw)["session"]


def test_audio_pcmu_y_voz_pausada():
    out = _session()["audio"]["output"]
    assert out["format"]["type"] == "audio/pcmu"
    assert out["speed"] < 1.0  # algo más lento/pausado que lo normal
    assert _session()["audio"]["input"]["format"]["type"] == "audio/pcmu"


def test_tool_end_call_presente():
    assert any(t["name"] == "end_call" for t in _session()["tools"])


def test_instrucciones_incluyen_nombre_rutina_y_nivel():
    ins = _session(
        nombre="Alejandro",
        rutina="Losartán 50mg (08:00); Caminar (17:00)",
        nivel_insistencia=3,
    )["instructions"]
    assert "Alejandro" in ins
    assert "Losartán" in ins
    assert "Insistencia 3" in ins


def test_sin_rutina_hace_seguimiento_general():
    ins = _session(nombre="Rosa", rutina="")["instructions"]
    assert "seguimiento general" in ins


def test_nivel_invalido_cae_a_recordar():
    assert "Insistencia 2" in _session(nivel_insistencia=99)["instructions"]


def test_tool_escalar_a_familia_presente():
    assert any(t["name"] == "escalar_a_familia" for t in _session()["tools"])


def test_historial_se_inyecta_en_las_instrucciones():
    ins = _session(
        historial="Última llamada (12/06, nivel AMARILLA): no tomó la medicación"
    )["instructions"]
    assert "Última llamada" in ins
    assert "AMARILLA" in ins
