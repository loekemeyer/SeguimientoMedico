"""Programación de llamadas: decide qué pacientes corresponde llamar ahora.

El usuario que contrata configura, por paciente, la hora local, la zona horaria
y los días de la semana. Un proceso externo (cron, worker o `scripts/run_scheduler.py`)
invoca `pacientes_a_llamar` periódicamente (p. ej. cada 5 minutos) y dispara las
llamadas para los que entran en la ventana horaria.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.db.models import Paciente

VENTANA_MIN = 5  # tolerancia en minutos alrededor de la hora programada


def debe_llamar(paciente: Paciente, ahora_utc: datetime, ventana_min: int = VENTANA_MIN) -> bool:
    """¿Corresponde llamar a este paciente en este momento?

    Considera: llamada activa, consentimiento firmado, día de la semana y la hora
    local (con tolerancia de `ventana_min`).
    """
    if not (paciente.activo and paciente.llamada_activa):
        return False
    if not paciente.consentimiento_firmado:
        return False

    try:
        tz = ZoneInfo(paciente.llamada_zona)
    except Exception:
        tz = ZoneInfo("America/Argentina/Buenos_Aires")
    local = ahora_utc.astimezone(tz)

    # Días: vacío = todos los días.
    if paciente.llamada_dias and local.weekday() not in paciente.llamada_dias:
        return False

    try:
        hh, mm = (int(x) for x in paciente.llamada_hora.split(":"))
    except Exception:
        return False
    objetivo = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diff_min = abs((local - objetivo).total_seconds()) / 60
    return diff_min <= ventana_min


def pacientes_a_llamar(db: Session, ahora_utc: datetime | None = None) -> list[Paciente]:
    """Devuelve los pacientes que deben ser llamados en este momento."""
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    activos = db.scalars(
        select(Paciente).where(Paciente.activo.is_(True), Paciente.llamada_activa.is_(True))
    ).all()
    return [p for p in activos if debe_llamar(p, ahora_utc)]
