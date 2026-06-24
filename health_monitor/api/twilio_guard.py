"""Guard reutilizable para los webhooks de Twilio.

Centraliza la validación de firma `X-Twilio-Signature` para TODOS los endpoints
que reciben webhooks de Twilio (`/twilio/voice`, `/whatsapp/incoming`). Antes la
lógica vivía sólo en `main.py` y `/whatsapp/incoming` quedaba sin proteger,
pese a que muta la HCE. Acá vive una sola vez, sin import circular.

Falla-cerrado en producción: si la validación está desactivada o falta el
`TWILIO_AUTH_TOKEN`, en `environment=production` se rechaza con 503 (config
inválida) en vez de aceptar requests sin verificar. En dev se omite con aviso.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from shared.config import get_settings
from shared.twilio_security import is_valid_twilio_signature

logger = logging.getLogger(__name__)


def _es_produccion(environment: str) -> bool:
    return (environment or "").strip().lower() in ("production", "prod")


def public_url(request: Request, base_url: str) -> str:
    """Reconstruye la URL pública exacta que Twilio firmó (base + path + query)."""
    url = (base_url or "").rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    return url


def verify_twilio_request(request: Request, params: dict) -> None:
    """Valida la firma del webhook; 403 si no coincide, 503 si está mal config en prod."""
    s = get_settings()
    es_prod = _es_produccion(s.environment)

    if not s.twilio_validate_signature:
        if es_prod:
            logger.error("twilio_validate_signature DESACTIVADO en producción: rechazo el webhook.")
            raise HTTPException(status_code=503, detail="Webhook de Twilio mal configurado")
        logger.warning("Validación de firma de Twilio DESACTIVADA (modo dev).")
        return

    if not s.twilio_auth_token:
        if es_prod:
            logger.error("TWILIO_AUTH_TOKEN ausente en producción: rechazo el webhook.")
            raise HTTPException(status_code=503, detail="Webhook de Twilio mal configurado")
        logger.warning("TWILIO_AUTH_TOKEN ausente; se omite validación de firma (modo dev).")
        return

    signature = request.headers.get("X-Twilio-Signature", "")
    url = public_url(request, s.public_base_url)
    if not is_valid_twilio_signature(s.twilio_auth_token, signature, url, params):
        logger.warning("Firma de Twilio inválida en %s", request.url.path)
        raise HTTPException(status_code=403, detail="Firma de Twilio inválida")
