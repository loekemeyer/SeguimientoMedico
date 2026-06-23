"""Muestra el reporte de la última llamada guardada (para revisar la prueba).

Lee la MISMA base SQLite que usa el servidor (local.db) y muestra, de la última
evolución registrada:
  - Semáforo (nivel de alerta) y motivos del triaje
  - RELATO empático (lo que contó el paciente, para la familia)
  - Resumen clínico + métricas extraídas (presión, glucemia, ánimo, etc.)
  - Transcripción completa (descifrada)

Uso:
    python scripts/ver_reporte.py            # última llamada de cualquier paciente
    python scripts/ver_reporte.py 1          # última llamada del paciente id=1
    python scripts/ver_reporte.py 1 5        # últimas 5 llamadas del paciente id=1
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Misma base que el servidor (run_app.sh / test_call_ai.py).
os.environ.setdefault("DATABASE_URL", "sqlite:///./local.db")

from sqlalchemy import select  # noqa: E402

from health_monitor.db.models import EvolucionDiaria  # noqa: E402
from health_monitor.db.session import get_session  # noqa: E402
from shared.config import get_settings  # noqa: E402
from shared.security import FieldCipher  # noqa: E402

_SEMAFORO = {"VERDE": "🟢", "AMARILLA": "🟡", "AMARILLO": "🟡", "ROJA": "🔴", "ROJO": "🔴"}


def _fmt_metricas(readout: dict) -> list[str]:
    """Arma líneas legibles solo con las métricas que aparecieron."""
    if not readout:
        return []
    etiquetas = {
        "presion_sistolica": "Presión sistólica",
        "presion_diastolica": "Presión diastólica",
        "glucemia": "Glucemia",
        "saturacion_oxigeno": "Saturación O₂",
        "adherencia_medicacion": "Adherencia a la medicación",
        "estado_animo": "Estado de ánimo",
        "sintomas": "Síntomas",
        "sintomas_alarma": "⚠️  Síntomas de alarma",
    }
    lineas: list[str] = []
    for clave, etiqueta in etiquetas.items():
        valor = readout.get(clave)
        if valor in (None, "", [], "desconocido"):
            continue
        if isinstance(valor, list):
            valor = ", ".join(str(v) for v in valor)
        lineas.append(f"    {etiqueta}: {valor}")
    return lineas


def _mostrar(evo: EvolucionDiaria, cipher: FieldCipher) -> None:
    semaforo = _SEMAFORO.get((evo.nivel_alerta or "").upper(), "⚪")
    fecha = evo.fecha.strftime("%d/%m/%Y %H:%M") if evo.fecha else "s/f"
    print("\n" + "=" * 64)
    print(f"  Paciente {evo.paciente_id}  |  {fecha}  |  {semaforo} {evo.nivel_alerta}")
    print("=" * 64)

    if evo.motivos:
        print("\n  MOTIVOS DEL TRIAJE:")
        for m in evo.motivos:
            print(f"    • {m}")

    print("\n  💚 RELATO (para la familia):")
    print(f"    {evo.relato.strip() if evo.relato else '— (vacío)'}")

    print("\n  📋 RESUMEN CLÍNICO:")
    print(f"    {evo.resumen.strip() if evo.resumen else '— (vacío)'}")

    metricas = _fmt_metricas(evo.readout or {})
    if metricas:
        print("\n  📊 MÉTRICAS:")
        print("\n".join(metricas))

    if evo.transcripcion_enc:
        try:
            transcript = cipher.decrypt(evo.transcripcion_enc)
        except Exception as exc:  # clave distinta a la de cuando se guardó
            transcript = f"(no se pudo descifrar: {exc})"
        print("\n  📝 TRANSCRIPCIÓN:")
        print(f"    {transcript}")
    print("=" * 64 + "\n")


def main() -> None:
    paciente_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    limite = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    cipher = FieldCipher(get_settings().encryption_key)
    db = next(get_session())
    try:
        stmt = select(EvolucionDiaria).order_by(EvolucionDiaria.id.desc()).limit(limite)
        if paciente_id is not None:
            stmt = (
                select(EvolucionDiaria)
                .where(EvolucionDiaria.paciente_id == paciente_id)
                .order_by(EvolucionDiaria.id.desc())
                .limit(limite)
            )
        evos = list(db.scalars(stmt).all())
    finally:
        db.close()

    if not evos:
        print("\n✗ No hay llamadas registradas todavía en local.db.")
        print("  ¿Colgaste la llamada? El reporte se guarda al terminar la llamada.\n")
        return

    for evo in reversed(evos):  # más vieja primero, última al final
        _mostrar(evo, cipher)


if __name__ == "__main__":
    main()
