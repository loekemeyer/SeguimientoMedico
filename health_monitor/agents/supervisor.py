"""Agente 3: Supervisor (The Gatekeeper) — triaje y disparo de alertas.

Compara el readout clínico contra los límites del paciente, decide el nivel de
alerta y ejecuta el protocolo correspondiente (Human-in-the-loop):

  ROJA     → corta la llamada con contención, webhook a emergencias + aviso familia
  AMARILLA → registra y avisa preventivamente a la familia por WhatsApp
  VERDE    → registra y cierra

La acción médica nunca la decide la IA: el supervisor solo entrega la alerta con
la ficha resumida al humano responsable.
"""
from __future__ import annotations

import logging

from health_monitor.schemas.clinical import ClinicalReadout
from health_monitor.triage import AlertLevel, ClinicalLimits, TriageResult, evaluate
from shared.config import get_settings
from shared.notifications import fire_webhook, send_whatsapp_message

logger = logging.getLogger(__name__)


def assess(readout: ClinicalReadout, limits: ClinicalLimits) -> TriageResult:
    """Evalúa el riesgo (delegado a la lógica determinística de triaje)."""
    return evaluate(readout, limits)


def should_interrupt_call(result: TriageResult) -> bool:
    """¿Hay peligro inminente que justifique interrumpir la llamada en vivo?"""
    return result.level == AlertLevel.ROJA


def dispatch_alerts(
    result: TriageResult,
    *,
    familiares: list[str],
    ficha_resumen: str,
    emergencia_webhook: str | None = None,
) -> dict:
    """Ejecuta el protocolo de notificación según el nivel. Devuelve qué se hizo.

    `familiares` y `ficha_resumen` ya deben venir descifrados por la capa de
    servicio. No se loguea PII en claro.
    """
    actions: dict[str, list[str]] = {"webhooks": [], "whatsapp": []}

    if result.level == AlertLevel.ROJA:
        payload = {
            "tipo": "alerta_roja",
            "paciente_id": result.paciente_id,
            "motivos": result.reasons,
            "ficha_resumen": ficha_resumen,
        }
        url = emergencia_webhook or get_settings().emergency_webhook  # central emergencias
        if fire_webhook(url, payload):
            actions["webhooks"].append("emergencias")
        for fam in familiares:
            if send_whatsapp_message(
                fam,
                "🔴 URGENTE: detectamos un parámetro crítico en el seguimiento. "
                "Ya avisamos al servicio de emergencias. "
                f"Motivo: {result.reasons[0] if result.reasons else 'ver ficha'}.",
            ):
                actions["whatsapp"].append(fam)

    elif result.level == AlertLevel.AMARILLA:
        resumen = "; ".join(result.reasons)
        for fam in familiares:
            if send_whatsapp_message(
                fam,
                "🟡 Aviso preventivo del seguimiento de hoy: "
                f"{resumen}. No es una emergencia, pero conviene estar atentos.",
            ):
                actions["whatsapp"].append(fam)

    else:  # VERDE
        logger.info("Paciente %s estable; sin notificaciones.", result.paciente_id)

    return actions
