"""Tests del cifrado AES-256-GCM (Ley 25.326)."""
import base64

import pytest

from shared.security import FieldCipher, generate_key


def test_roundtrip_encrypt_decrypt():
    cipher = FieldCipher(generate_key())
    plaintext = "Juan Pérez — 11-5555-4444"
    token = cipher.encrypt(plaintext)
    assert token != plaintext
    assert cipher.decrypt(token) == plaintext


def test_distintos_nonces_distinto_ciphertext():
    cipher = FieldCipher(generate_key())
    a = cipher.encrypt("120/80")
    b = cipher.encrypt("120/80")
    assert a != b  # nonce aleatorio => ciphertext distinto
    assert cipher.decrypt(a) == cipher.decrypt(b) == "120/80"


def test_tamper_detectado():
    cipher = FieldCipher(generate_key())
    token = cipher.encrypt("dato sensible")
    raw = bytearray(base64.urlsafe_b64decode(token))
    raw[-1] ^= 0x01  # altera un byte del tag/ciphertext
    tampered = base64.urlsafe_b64encode(bytes(raw)).decode()
    with pytest.raises(Exception):
        cipher.decrypt(tampered)


def test_aad_debe_coincidir():
    cipher = FieldCipher(generate_key())
    token = cipher.encrypt("expediente", aad=b"paciente-1")
    assert cipher.decrypt(token, aad=b"paciente-1") == "expediente"
    with pytest.raises(Exception):
        cipher.decrypt(token, aad=b"paciente-2")


def test_clave_de_tamano_invalido_rechazada():
    short_key = base64.b64encode(b"too-short").decode()
    with pytest.raises(ValueError):
        FieldCipher(short_key)


def test_clave_vacia_rechazada():
    with pytest.raises(ValueError):
        FieldCipher("")


def test_generate_key_es_256_bits():
    key = base64.b64decode(generate_key())
    assert len(key) == 32


# --- Tokens de sesión: fail-closed y formato robusto (audit #2) ---

def test_secret_falla_cerrado_fuera_de_dev(monkeypatch):
    import shared.auth as auth
    import shared.config as cfg

    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("ENVIRONMENT", "production")
    cfg.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        auth._secret()
    # entorno desconocido también es fail-closed
    monkeypatch.setenv("ENVIRONMENT", "staging")
    cfg.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        auth._secret()
    cfg.get_settings.cache_clear()


def test_secret_usa_dev_en_desarrollo(monkeypatch):
    import shared.auth as auth
    import shared.config as cfg

    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    cfg.get_settings.cache_clear()
    assert auth._secret() == auth._DEV_SECRET
    cfg.get_settings.cache_clear()


def test_decode_token_rechaza_formato_invalido(monkeypatch):
    import shared.auth as auth
    import shared.config as cfg

    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    cfg.get_settings.cache_clear()
    for malo in ["", "sinpunto", "a.b.c", ".", "a.", ".b"]:
        with pytest.raises(ValueError):
            auth.decode_token(malo)
    # un token válido se decodifica
    tok = auth.create_access_token(7)
    assert auth.decode_token(tok)["sub"] == 7
    cfg.get_settings.cache_clear()
