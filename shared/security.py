"""Cifrado de datos sensibles en reposo — Ley 25.326 (Datos Sensibles, Argentina).

Implementa AES-256-GCM (cifrado autenticado) sobre la librería `cryptography`.
GCM provee confidencialidad + integridad: si el ciphertext es alterado, el
descifrado falla en lugar de devolver datos corruptos.

Formato del token cifrado (base64 urlsafe sobre los bytes concatenados):

    [ nonce (12 bytes) ][ ciphertext + tag (GCM) ]

La clave se provee vía `ENCRYPTION_KEY` (base64, 32 bytes = 256 bits).
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12  # tamaño recomendado para AES-GCM
KEY_BYTES = 32    # AES-256


def generate_key() -> str:
    """Genera una clave AES-256 aleatoria en base64 (para inicializar un despliegue)."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def _load_key(key_b64: str) -> bytes:
    if not key_b64:
        raise ValueError(
            "ENCRYPTION_KEY vacía. Generá una con shared.security.generate_key()."
        )
    key = base64.b64decode(key_b64)
    if len(key) != KEY_BYTES:
        raise ValueError(
            f"ENCRYPTION_KEY debe ser de {KEY_BYTES} bytes (AES-256); "
            f"se recibieron {len(key)}."
        )
    return key


class FieldCipher:
    """Cifra/descifra campos individuales (PII, datos clínicos) con AES-256-GCM.

    Pensado para encriptar columnas sensibles antes de persistirlas en PostgreSQL.

    >>> cipher = FieldCipher(generate_key())
    >>> token = cipher.encrypt("120/80")
    >>> cipher.decrypt(token)
    '120/80'
    """

    def __init__(self, key_b64: str):
        self._aes = AESGCM(_load_key(key_b64))

    def encrypt(self, plaintext: str, *, aad: bytes | None = None) -> str:
        """Cifra un string y devuelve un token base64 urlsafe.

        `aad` (associated data) se autentica pero no se cifra; útil para ligar
        el ciphertext a, por ejemplo, el ID del paciente.
        """
        nonce = os.urandom(NONCE_BYTES)
        ct = self._aes.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return base64.urlsafe_b64encode(nonce + ct).decode("ascii")

    def decrypt(self, token: str, *, aad: bytes | None = None) -> str:
        """Descifra un token producido por `encrypt`. Lanza si fue alterado."""
        raw = base64.urlsafe_b64decode(token)
        nonce, ct = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
        return self._aes.decrypt(nonce, ct, aad).decode("utf-8")
