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

from health_monitor.calls import disparar_llamadas_pendientes  # noqa: E402
from health_monitor.db.session import get_session  # noqa: E402


def main() -> None:
    ahora = datetime.now(timezone.utc)
    db = next(get_session())
    try:
        registros = disparar_llamadas_pendientes(db, ahora)
        if not registros:
            print(f"[{ahora.isoformat()}] Sin llamadas para disparar en este momento.")
            return
        for r in registros:
            print(f"[{ahora.isoformat()}] Paciente {r['paciente_id']}: "
                  f"{r['status']} ({r['detail']}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
