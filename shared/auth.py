"""Autenticación: hash de contraseñas y tokens de sesión firmados.

Usa solo la librería estándar (sin dependencias extra):
  - Contraseñas: PBKDF2-HMAC-SHA256 con salt aleatorio (200k iteraciones).
  - Tokens: payload JSON firmado con HMAC-SHA256 (estilo JWT, formato body.sig).

El secreto de firma viene de `JWT_SECRET` (.env). En desarrollo cae a un valor
inseguro con advertencia; en producción debe configurarse uno fuerte.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 200_000
_DEV_SECRET = "dev-insecure-secret-cambiar-en-produccion"


def _secret() -> str:
    from shared.config import get_settings

    settings = get_settings()
    if settings.jwt_secret:
        return settings.jwt_secret
    if settings.environment.strip().lower() in ("prod", "production"):
        raise RuntimeError(
            "JWT_SECRET es obligatorio con ENVIRONMENT=production. "
            'Generá uno con: python -c "import secrets;print(secrets.token_urlsafe(48))"'
        )
    logger.warning("JWT_SECRET vacío: usando secreto de desarrollo (INSEGURO).")
    return _DEV_SECRET


def signing_secret() -> str:
    """Secreto activo para firmar tokens fuera de este módulo (p. ej. el WS de Twilio).

    Comparte la misma política que los tokens de sesión: lanza en producción si
    falta `JWT_SECRET`, y en desarrollo cae al secreto de dev con advertencia.
    """
    return _secret()


# --- Contraseñas ---

def hash_password(password: str) -> str:
    """Devuelve un hash almacenable: pbkdf2_sha256$iter$salt$hash (todo base64)."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str) -> bool:
    """Verifica una contraseña contra el hash almacenado (tiempo constante)."""
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        assert algo == "pbkdf2_sha256"
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), _b64d(salt_b64), int(iters)
        )
        return hmac.compare_digest(dk, _b64d(hash_b64))
    except Exception:
        return False


# --- Tokens de sesión ---

def create_access_token(user_id: int, expires_in: int = 7 * 24 * 3600) -> str:
    """Token firmado con el id de usuario y vencimiento (default 7 días)."""
    payload = {"sub": user_id, "exp": int(time.time()) + expires_in}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _sign(body)
    return f"{body}.{sig}"


def decode_token(token: str) -> dict:
    """Valida la firma y el vencimiento; devuelve el payload. Lanza si es inválido."""
    body, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(body)):
        raise ValueError("Firma de token inválida")
    payload = json.loads(_b64d(body))
    if payload.get("exp", 0) < time.time():
        raise ValueError("Token vencido")
    return payload


# --- Helpers ---

def _sign(body: str) -> str:
    return _b64e(hmac.new(_secret().encode(), body.encode(), hashlib.sha256).digest())


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
