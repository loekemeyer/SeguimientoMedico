"""Programador de llamadas: revisa qué pacientes corresponde llamar ahora.

Pensado para ejecutarse periódicamente (cron / worker), por ejemplo cada 5 min:

    */5 * * * *  cd /app && python scripts/run_scheduler.py

Para cada paciente en ventana horaria, dispara la llamada saliente (si Twilio
está configurado). En modo dev (sin Twilio) solo lista a quién llamaría.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from health_monitor.db.session import get_session  # noqa: E402
from health_monitor.scheduler import pacientes_a_llamar  # noqa: E402


def main() -> None:
    ahora = datetime.now(timezone.utc)
    db = next(get_session())
    try:
        pendientes = pacientes_a_llamar(db, ahora)
        if not pendientes:
            print(f"[{ahora.isoformat()}] Sin llamadas programadas para este momento.")
            return
        for p in pendientes:
            print(f"[{ahora.isoformat()}] Corresponde llamar al paciente id={p.id} "
                  f"(hora {p.llamada_hora} {p.llamada_zona}).")
            # Punto de integración: disparar la llamada saliente vía Twilio.
            # from health_monitor.main import initiate_call  (o un servicio dedicado)
    finally:
        db.close()


if __name__ == "__main__":
    main()
