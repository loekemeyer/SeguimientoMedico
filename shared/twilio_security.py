"""Seguridad de los webhooks de Twilio.

Dos protecciones, ambas con la librería estándar (sin depender del paquete
`twilio`), para que la lógica sea testeable sin esa dependencia:

1) **Firma de los webhooks HTTP** (p. ej. `/twilio/voice`). Twilio firma cada
   request con HMAC-SHA1 sobre la URL pública más los parámetros POST ordenados,
   usando el Auth Token como clave. Validarla evita que un tercero que conozca
   la URL dispare el flujo de llamadas.

2) **Token firmado del WebSocket de Media Streams.** Twilio NO firma el
   handshake del WebSocket; por eso `/twilio/voice` (ya validado) inyecta en el
   TwiML un token de corta duración que el WS exige y verifica antes de operar.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time


# --- Firma de webhooks HTTP (X-Twilio-Signature) ---

def compute_twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Reproduce el algoritmo de firma de Twilio (HMAC-SHA1, base64 estándar).

    Para webhooks POST form-encoded: a la URL se le concatenan los pares
    clave+valor de los parámetros, ordenados por clave, sin separadores.
    """
    payload = url
    for key in sorted(params):
        payload += key + str(params[key])
    digest = hmac.new(
        auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def is_valid_twilio_signature(
    auth_token: str, signature: str, url: str, params: dict[str, str]
) -> bool:
    """Compara (en tiempo constante) la firma recibida con la esperada."""
    if not (auth_token and signature):
        return False
    expected = compute_twilio_signature(auth_token, url, params)
    return hmac.compare_digest(expected, signature)


# --- Token de corta duración para el WebSocket de Media Streams ---

def make_stream_token(secret: str, paciente_id: int, *, ttl: int = 600) -> str:
    """Token firmado (HMAC-SHA256) que liga el WS a un paciente y vence pronto.

    Formato: ``paciente_id.exp.firma`` (todo en una cadena sin espacios).
    """
    exp = int(time.time()) + ttl
    body = f"{paciente_id}.{exp}"
    return f"{body}.{_sign(secret, body)}"


def verify_stream_token(secret: str, token: str, paciente_id: int) -> bool:
    """Valida firma, vencimiento y que el token corresponda al paciente dado."""
    try:
        pid_str, exp_str, sig = token.split(".")
    except (ValueError, AttributeError):
        return False
    body = f"{pid_str}.{exp_str}"
    if not hmac.compare_digest(sig, _sign(secret, body)):
        return False
    try:
        if int(exp_str) < time.time():
            return False
    except ValueError:
        return False
    return pid_str == str(paciente_id)


def _sign(secret: str, body: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
