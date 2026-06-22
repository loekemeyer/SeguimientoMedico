"""Canales de notificación: WhatsApp (Twilio) y webhooks (emergencias / ventas).

Las integraciones externas usan imports perezosos y degradan con elegancia:
si la librería/credencial no está disponible, se registra la intención en logs
en lugar de fallar. Esto permite testear la lógica de negocio sin red ni claves.
"""
from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)


def send_whatsapp_message(
    to: str,
    body: str | None = None,
    *,
    media_url: str | None = None,
    content_sid: str | None = None,
    content_variables: dict | None = None,
) -> bool:
    """Envía un mensaje de WhatsApp vía Twilio.

    - `content_sid`: ID de una plantilla aprobada (mensajes iniciados por el
      negocio, como las alertas, requieren plantilla fuera de la ventana de 24h).
    - `body`: texto libre (solo válido dentro de la ventana de 24h de sesión).
    Devuelve True si se envió, False si no hay credenciales o falla.
    """
    from shared.config import get_settings

    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token):
        logger.warning("Twilio no configurado; mensaje a %s NO enviado: %s", to, body)
        return False

    try:
        from twilio.rest import Client  # import perezoso
    except ImportError:
        logger.error("Paquete 'twilio' no instalado; no se puede enviar a %s.", to)
        return False

    client = Client(s.twilio_account_sid, s.twilio_auth_token)
    kwargs = {"from_": s.twilio_whatsapp_from, "to": _wa(to)}
    if content_sid:
        kwargs["content_sid"] = content_sid
        if content_variables:
            kwargs["content_variables"] = json.dumps(content_variables)
    elif body:
        kwargs["body"] = body
    if media_url:
        kwargs["media_url"] = [media_url]
    try:
        msg = client.messages.create(**kwargs)
    except Exception as exc:  # incluye TwilioRestException
        code = getattr(exc, "code", None)
        if code == 21654 or code == 63016:
            logger.error(
                "WhatsApp a %s NO enviado: la ventana de 24h está cerrada. "
                "Ese número debe escribir 'join <código>' al sandbox y reintentar "
                "(en producción se requiere una plantilla aprobada).", to
            )
        else:
            logger.error("WhatsApp a %s NO enviado (Twilio code=%s): %s", to, code, exc)
        return False
    logger.info("WhatsApp enviado a %s (sid=%s)", to, msg.sid)
    return True


def fire_webhook(url: str, payload: dict) -> bool:
    """Dispara un webhook POST (JSON) hacia emergencias / equipo de ventas.

    Devuelve True si respondió 2xx, False en cualquier otro caso.
    """
    if not url:
        logger.warning("Webhook sin URL; payload no enviado: %s", json.dumps(payload))
        return False
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        logger.info("Webhook OK -> %s (%s)", url, resp.status_code)
        return True
    except httpx.HTTPError as exc:
        logger.error("Webhook falló -> %s: %s", url, exc)
        return False


def _wa(number: str) -> str:
    """Normaliza un número al formato whatsapp: que espera Twilio."""
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"
