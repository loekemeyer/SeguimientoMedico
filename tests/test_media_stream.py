"""Tests del puente de audio (Twilio <-> Realtime).

Lo crítico: cuando el paciente cuelga (Twilio cierra el WS y la corrutina de
entrada termina), `run()` debe TERMINAR —no quedar colgado esperando a OpenAI—
para que el bloque que persiste el reporte llegue a ejecutarse.
"""
from __future__ import annotations

import asyncio

from health_monitor.agents.orchestrator import CallState
from health_monitor.realtime.media_stream import MediaStreamBridge
from health_monitor.triage import ClinicalLimits


class _FakeTwilioWS:
    """Simula el WS de Twilio: manda 'start', un 'media', y se desconecta."""

    def __init__(self):
        self.sent: list[str] = []

    async def iter_text(self):
        # Starlette se TRAGA el WebSocketDisconnect: el generador simplemente
        # termina (no levanta excepción) cuando el cliente cuelga.
        yield '{"event": "start", "start": {"streamSid": "SS1"}}'
        yield '{"event": "media", "media": {"payload": "AAAA"}}'
        return

    async def send_text(self, _data):
        self.sent.append(_data)


class _FakeOpenAIWS:
    """Simula el WS de OpenAI: NUNCA emite nada (se quedaría esperando)."""

    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Nunca llega audio del modelo: bloquea hasta que lo cancelen.
        await asyncio.Event().wait()
        raise StopAsyncIteration  # nunca se alcanza

    async def close(self):
        self.closed = True


def _state() -> CallState:
    return CallState(paciente_id=1, limits=ClinicalLimits(paciente_id=1))


def test_run_no_se_cuelga_cuando_el_paciente_corta(monkeypatch):
    import health_monitor.realtime.media_stream as ms

    # OPENAI_API_KEY presente (si no, run() sale temprano) y un modelo cualquiera.
    fake_settings = type("S", (), {"openai_api_key": "sk-test", "openai_realtime_model": "m"})()
    monkeypatch.setattr(ms, "get_settings", lambda: fake_settings)

    fake_openai = _FakeOpenAIWS()
    bridge = MediaStreamBridge(_FakeTwilioWS(), _state(), nombre="Test")

    async def _fake_connect(self, *_a, **_k):
        return fake_openai

    monkeypatch.setattr(MediaStreamBridge, "_connect_openai", _fake_connect)

    async def _run_con_timeout():
        # Si el fix no estuviera, esto colgaría para siempre: el timeout lo delataría.
        await asyncio.wait_for(bridge.run(), timeout=3)

    asyncio.run(_run_con_timeout())

    assert fake_openai.closed  # se cerró la sesión de OpenAI al terminar
