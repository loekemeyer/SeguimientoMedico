"""Agente 3: Supervisor (The Gatekeeper) — triaje, resumen y alertas.

Compara el readout clínico contra los límites del paciente, decide el nivel de
alerta, arma un resumen legible de la llamada y registra cada notificación
(Human-in-the-loop):

  ROJA     → corta la llamada con contención, webhook a emergencias + WhatsApp familia
  AMARILLA → registra y avisa preventivamente a la familia por WhatsApp
  VERDE    → registra y cierra

Cada notificación se devuelve como registro estructurado para que la capa de
servicio la persista y el familiar la vea en la app (seguimiento real).
La acción médica nunca la decide la IA: solo entrega la alerta al humano.
"""
from __future__ import annotations

import logging

from health_monitor.schemas.clinical import AdherenceState, ClinicalReadout, MoodState
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


def build_resumen(
    readout: ClinicalReadout, result: TriageResult, paciente_nombre: str = ""
) -> str:
    """Arma un resumen legible de la llamada para que lo lea el familiar."""
    # Usa el nombre tal cual lo guardó el admin (puede ser "Papá", "Abuela Rosa", etc.).
    quien = paciente_nombre.strip() if paciente_nombre.strip() else "El paciente"
    partes: list[str] = []

    if readout.presion_sistolica and readout.presion_diastolica:
        partes.append(f"presión {readout.presion_sistolica}/{readout.presion_diastolica}")
    if readout.glucemia:
        partes.append(f"glucemia {readout.glucemia} mg/dL")
    if readout.saturacion_oxigeno:
        partes.append(f"saturación {readout.saturacion_oxigeno}%")

    if readout.adherencia_medicacion == AdherenceState.TOMO_TODO:
        partes.append("tomó la medicación")
    elif readout.adherencia_medicacion == AdherenceState.NO_TOMO:
        partes.append("no tomó la medicación")
    elif readout.adherencia_medicacion == AdherenceState.TOMO_PARCIAL:
        partes.append("tomó parcialmente la medicación")

    animo = {
        MoodState.BIEN: "ánimo bien",
        MoodState.DECAIDO: "ánimo decaído",
        MoodState.ANGUSTIADO: "ánimo angustiado",
    }.get(readout.estado_animo)
    if animo:
        partes.append(animo)

    detalle = "; ".join(partes) if partes else "sin datos cuantitativos registrados"
    encabezado = {
        AlertLevel.VERDE: f"{quien} estable.",
        AlertLevel.AMARILLA: f"Atención con {quien}.",
        AlertLevel.ROJA: f"ALERTA con {quien}.",
    }[result.level]
    return f"{encabezado} {detalle.capitalize()}."


def dispatch_alerts(
    result: TriageResult,
    *,
    contactos: list[dict],
    ficha_resumen: str,
    paciente_nombre: str = "",
    emergencia_webhook: str | None = None,
) -> list[dict]:
    """Ejecuta el protocolo de notificación y devuelve el registro de cada envío.

    `contactos` es una lista de dicts: {telefono, label, recibe_alertas}.
    Cada elemento del resultado: {canal, nivel, destino, destino_label, contenido, enviado}.
    """
    quien = paciente_nombre.strip() if paciente_nombre.strip() else "el paciente"
    nivel = result.level.name
    registros: list[dict] = []

    destinatarios = [c for c in contactos if c.get("recibe_alertas", True)]

    if result.level == AlertLevel.ROJA:
        motivo = result.reasons[0] if result.reasons else "ver ficha clínica"
        url = emergencia_webhook or get_settings().emergency_webhook
        payload = {
            "tipo": "alerta_roja",
            "paciente_id": result.paciente_id,
            "paciente_nombre": paciente_nombre,
            "motivos": result.reasons,
            "ficha_resumen": ficha_resumen,
        }
        registros.append({
            "canal": "webhook", "nivel": nivel,
            "destino": url or "(sin URL)", "destino_label": "Central de emergencias",
            "contenido": f"Alerta roja: {motivo}",
            "enviado": fire_webhook(url, payload),
        })
        msg = (
            f"🔴 URGENTE — {quien}: en la llamada de seguimiento de hoy detectamos "
            f"un signo de alarma ({motivo}). Ya dimos aviso al servicio de emergencias. "
            f"Por favor, comunicate con {quien} o con emergencias cuanto antes."
        )
        for c in destinatarios:
            registros.append({
                "canal": "whatsapp", "nivel": nivel,
                "destino": c["telefono"], "destino_label": c.get("label", ""),
                "contenido": msg,
                "enviado": send_whatsapp_message(c["telefono"], msg),
            })

    elif result.level == AlertLevel.AMARILLA:
        resumen = "; ".join(result.reasons)
        msg = (
            f"🟡 Seguimiento de {quien} — aviso preventivo de hoy: {resumen}. "
            f"No es una urgencia, pero conviene estar atentos y, si podés, "
            f"pasar a ver a {quien} o llamarlo."
        )
        for c in destinatarios:
            registros.append({
                "canal": "whatsapp", "nivel": nivel,
                "destino": c["telefono"], "destino_label": c.get("label", ""),
                "contenido": msg,
                "enviado": send_whatsapp_message(c["telefono"], msg),
            })

    else:  # VERDE
        logger.info("Paciente %s estable; sin notificaciones.", result.paciente_id)

    return registros
