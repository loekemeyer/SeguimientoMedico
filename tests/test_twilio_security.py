"""Tests de la seguridad de webhooks de Twilio: firma + token del WebSocket."""
import time

from shared.twilio_security import (
    compute_twilio_signature,
    is_valid_twilio_signature,
    make_stream_token,
    verify_stream_token,
)

# Vector oficial de la documentación de Twilio ("Validating Signatures").
_AUTH_TOKEN = "12345"
_URL = "https://mycompany.com/myapp.php?foo=1&bar=2"
_PARAMS = {
    "CallSid": "CA1234567890ABCDE",
    "Caller": "+14158675309",
    "Digits": "1234",
    "From": "+14158675309",
    "To": "+18005551212",
}
# Verificado contra twilio.request_validator.RequestValidator('12345').
_EXPECTED = "RSOYDt4T1cUTdK1PDd93/VVr8B8="


def test_firma_coincide_con_el_vector_oficial_de_twilio():
    assert compute_twilio_signature(_AUTH_TOKEN, _URL, _PARAMS) == _EXPECTED


def test_firma_valida_es_aceptada():
    assert is_valid_twilio_signature(_AUTH_TOKEN, _EXPECTED, _URL, _PARAMS) is True


def test_firma_alterada_es_rechazada():
    assert is_valid_twilio_signature(_AUTH_TOKEN, "firma-falsa", _URL, _PARAMS) is False


def test_parametro_modificado_invalida_la_firma():
    adulterado = {**_PARAMS, "Digits": "9999"}
    assert is_valid_twilio_signature(_AUTH_TOKEN, _EXPECTED, _URL, adulterado) is False


def test_sin_token_o_sin_firma_se_rechaza():
    assert is_valid_twilio_signature("", _EXPECTED, _URL, _PARAMS) is False
    assert is_valid_twilio_signature(_AUTH_TOKEN, "", _URL, _PARAMS) is False


# --- Token del WebSocket de Media Streams ---

def test_stream_token_roundtrip():
    token = make_stream_token("secreto", 42)
    assert verify_stream_token("secreto", token, 42) is True


def test_stream_token_otro_paciente_es_rechazado():
    token = make_stream_token("secreto", 42)
    assert verify_stream_token("secreto", token, 43) is False


def test_stream_token_otro_secreto_es_rechazado():
    token = make_stream_token("secreto", 42)
    assert verify_stream_token("otro-secreto", token, 42) is False


def test_stream_token_vencido_es_rechazado():
    token = make_stream_token("secreto", 42, ttl=-1)
    assert verify_stream_token("secreto", token, 42) is False


def test_stream_token_malformado_es_rechazado():
    assert verify_stream_token("secreto", "", 42) is False
    assert verify_stream_token("secreto", "basura", 42) is False
    assert verify_stream_token("secreto", "1.2", 42) is False


def test_stream_token_adulterado_es_rechazado():
    token = make_stream_token("secreto", 42)
    pid, exp, _sig = token.split(".")
    # Reescribir el cuerpo dejando otra firma no debe validar.
    assert verify_stream_token("secreto", f"{pid}.{exp}.firmafalsa", 42) is False


def test_stream_token_respeta_ttl_futuro():
    token = make_stream_token("secreto", 7, ttl=600)
    assert int(token.split(".")[1]) > time.time()
