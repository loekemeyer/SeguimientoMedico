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
