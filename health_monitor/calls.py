"""Disparo de llamadas de voz salientes y motor del scheduler automático.

Separa la DECISIÓN (scheduler.pacientes_a_llamar) de la ACCIÓN (discar por Twilio),
con un `caller` inyectable para poder testear el scheduler sin telefonía real.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from health_monitor.db.models import Paciente
from health_monitor.scheduler import pacientes_a_llamar
from shared.config import get_settings
from shared.security import FieldCipher

logger = logging.getLogger(__name__)


def iniciar_llamada_voz(paciente: Paciente, settings=None) -> str:
    """Inicia la llamada de voz saliente vía Twilio y devuelve el call_sid.

    Lanza si Twilio / la URL pública no están configurados, o si la API falla.
    """
    settings = settings or get_settings()
    if not (settings.twilio_account_sid and settings.twilio_auth_token
            and settings.public_base_url):
        raise RuntimeError("Twilio o public_base_url no configurados")
    from twilio.rest import Client  # import perezoso

    cipher = FieldCipher(settings.encryption_key)
    numero = cipher.decrypt(paciente.telefono_whatsapp_enc)
    if settings.twilio_voice_from:  # número de voz: llamada telefónica normal
        to, desde = numero, settings.twilio_voice_from
    else:  # fallback: voz por WhatsApp
        to, desde = f"whatsapp:{numero}", settings.twilio_whatsapp_from
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        to=to, from_=desde,
        url=f"{settings.public_base_url}/twilio/voice?paciente_id={paciente.id}",
    )
    return call.sid


def disparar_llamadas_pendientes(
    db: Session,
    ahora: datetime | None = None,
    *,
    caller: Callable[[Paciente], str] | None = None,
    cooldown_horas: int = 12,
) -> list[dict]:
    """Dispara las llamadas que corresponden ahora, evitando discar dos veces.

    `caller(paciente) -> call_sid` permite inyectar un disparador de prueba.
    La idempotencia se apoya en `Paciente.ultima_llamada_programada`: si ya se
    disparó dentro de `cooldown_horas`, se saltea (evita doble discado en ventanas
    contiguas o tras un reinicio del worker). Devuelve un registro por intento.
    """
    ahora = ahora or datetime.now(timezone.utc)
    caller = caller or iniciar_llamada_voz
    registros: list[dict] = []
    for p in pacientes_a_llamar(db, ahora):
        ultima = p.ultima_llamada_programada
        if ultima is not None:
            ult = ultima if ultima.tzinfo else ultima.replace(tzinfo=timezone.utc)
            if ahora - ult < timedelta(hours=cooldown_horas):
                continue  # ya se llamó hace poco
        try:
            sid = caller(p)
            p.ultima_llamada_programada = ahora
            db.commit()
            registros.append({"paciente_id": p.id, "status": "llamando", "detail": sid})
            logger.info("Scheduler: llamada disparada al paciente %s (sid=%s).", p.id, sid)
        except Exception as exc:  # un fallo en uno no frena a los demás
            db.rollback()
            registros.append({"paciente_id": p.id, "status": "error", "detail": str(exc)})
            logger.error("Scheduler: no se pudo llamar al paciente %s: %s", p.id, exc)
    return registros
