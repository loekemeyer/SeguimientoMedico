"""Tests del modo WhatsApp por voz (núcleo, con degradación: sin red ni API key)."""
from health_monitor.whatsapp import voice_chat
from shared.security import phone_index


def test_apertura_sin_historial_da_mensaje():
    msg, fin = voice_chat.next_assistant_message([], "")
    assert msg and not fin


def test_continuacion_da_mensaje():
    msg, fin = voice_chat.next_assistant_message(
        [{"role": "assistant", "content": "Hola"}], "Bien, gracias"
    )
    assert msg and not fin


def test_transcribe_sin_apikey_es_vacio():
    assert voice_chat.transcribe(b"datos-de-audio") == ""


def test_synthesize_sin_apikey_es_vacio():
    assert voice_chat.synthesize("hola") == b""


def test_phone_index_determinista_y_normaliza_whatsapp():
    a = phone_index("whatsapp:+5491112345678", "")
    b = phone_index("+5491112345678", "")
    assert a == b  # mismo número, con o sin prefijo whatsapp:
    assert a != phone_index("+5491100000000", "")  # números distintos, índices distintos
