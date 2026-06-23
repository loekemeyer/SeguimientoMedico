"""Reglas de triaje del Agente Supervisor (The Gatekeeper).

Lógica de negocio determinística y auditable: compara las métricas extraídas
(`ClinicalReadout`) contra los límites personalizados de la ficha clínica del
paciente (`ClinicalLimits`) y clasifica el riesgo en tres niveles.

Esta lógica **no** la decide el LLM: es código revisable y testeable, requisito
para un sistema de salud. El LLM solo provee la extracción de variables.

Jerarquía (gana siempre el nivel más grave):

    ROJA    → parámetro crítico o síntoma de alarma  → emergencia + familia
    AMARILLA→ desvío leve / no adherencia / desánimo  → aviso preventivo familia
    VERDE   → estable                                 → registrar y cerrar
"""
from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field

from health_monitor.schemas.clinical import (
    AdherenceState,
    ClinicalReadout,
    EmotionalRisk,
    MoodState,
)


class AlertLevel(IntEnum):
    """Niveles de alerta. El orden numérico permite tomar el máximo (más grave)."""

    VERDE = 0
    AMARILLA = 1
    ROJA = 2


class ClinicalLimits(BaseModel):
    """Límites médicos personalizados del paciente (de `Tabla_Ficha_Clinica`).

    Cada par (min, max) define el rango aceptable. Fuera de los límites "duros"
    se dispara ROJA; el margen `*_margen_amarillo` define una franja de
    pre-alerta (AMARILLA) por dentro del límite duro.
    """

    paciente_id: int

    # Presión arterial sistólica (mmHg)
    sistolica_min: int = 90
    sistolica_max: int = 140
    sistolica_critica_max: int = 180
    sistolica_critica_min: int = 80

    # Presión arterial diastólica (mmHg)
    diastolica_min: int = 60
    diastolica_max: int = 90
    diastolica_critica_max: int = 120

    # Glucemia (mg/dL)
    glucemia_min: int = 70
    glucemia_max: int = 180
    glucemia_critica_min: int = 54
    glucemia_critica_max: int = 300

    # Frecuencia cardíaca (lpm)
    fc_min: int = 50
    fc_max: int = 100
    fc_critica_min: int = 40
    fc_critica_max: int = 130

    # Saturación de oxígeno (%)
    spo2_min: int = 94
    spo2_critica_min: int = 90

    # Temperatura corporal (°C). Febrícula/fiebre y baja temperatura. En adultos
    # mayores la fiebre puede ser signo de infección; la hipotermia es crítica.
    temp_min: float = 36.0
    temp_max: float = 37.8
    temp_critica_min: float = 35.0
    temp_critica_max: float = 39.0

    # Dolor (escala 0-10). Por encima de este umbral se marca AMARILLA (dolor
    # significativo que conviene revisar; el adulto mayor suele subreportarlo).
    dolor_max: int = 6

    # Peso (kg): aumento brusco respecto de la última medición (en ≤7 días) que
    # marca AMARILLA. Un salto rápido suele indicar retención de líquidos /
    # descompensación cardíaca.
    peso_delta_amarillo: float = 2.0


class TriageResult(BaseModel):
    """Resultado del triaje: nivel global + razones que lo justifican."""

    paciente_id: int
    level: AlertLevel
    reasons: list[str] = Field(default_factory=list)

    @property
    def level_name(self) -> str:
        return self.level.name


def evaluate(
    readout: ClinicalReadout,
    limits: ClinicalLimits,
    *,
    peso_anterior: float | None = None,
    dias_desde_peso: int | None = None,
) -> TriageResult:
    """Evalúa un readout clínico contra los límites del paciente.

    Acumula todas las razones y devuelve el nivel más grave detectado.
    `peso_anterior`/`dias_desde_peso` permiten detectar un aumento brusco de peso
    comparando con la última medición (si se conoce).
    """
    findings: list[tuple[AlertLevel, str]] = []

    # --- Síntomas de alarma → siempre ROJA ---
    for sintoma in readout.sintomas_alarma:
        findings.append((AlertLevel.ROJA, f"Síntoma de alarma: {sintoma}"))

    # --- Presión sistólica ---
    s = readout.presion_sistolica
    if s is not None:
        if s >= limits.sistolica_critica_max or s <= limits.sistolica_critica_min:
            findings.append((AlertLevel.ROJA, f"Presión sistólica crítica: {s} mmHg"))
        elif s > limits.sistolica_max or s < limits.sistolica_min:
            findings.append((AlertLevel.AMARILLA, f"Presión sistólica fuera de rango: {s} mmHg"))

    # --- Presión diastólica ---
    d = readout.presion_diastolica
    if d is not None:
        if d >= limits.diastolica_critica_max:
            findings.append((AlertLevel.ROJA, f"Presión diastólica crítica: {d} mmHg"))
        elif d > limits.diastolica_max or d < limits.diastolica_min:
            findings.append((AlertLevel.AMARILLA, f"Presión diastólica fuera de rango: {d} mmHg"))

    # --- Glucemia ---
    g = readout.glucemia
    if g is not None:
        if g <= limits.glucemia_critica_min or g >= limits.glucemia_critica_max:
            findings.append((AlertLevel.ROJA, f"Glucemia crítica: {g} mg/dL"))
        elif g < limits.glucemia_min or g > limits.glucemia_max:
            findings.append((AlertLevel.AMARILLA, f"Glucemia fuera de rango: {g} mg/dL"))

    # --- Frecuencia cardíaca ---
    fc = readout.frecuencia_cardiaca
    if fc is not None:
        if fc <= limits.fc_critica_min or fc >= limits.fc_critica_max:
            findings.append((AlertLevel.ROJA, f"Frecuencia cardíaca crítica: {fc} lpm"))
        elif fc < limits.fc_min or fc > limits.fc_max:
            findings.append((AlertLevel.AMARILLA, f"Frecuencia cardíaca fuera de rango: {fc} lpm"))

    # --- Saturación de oxígeno ---
    spo2 = readout.saturacion_oxigeno
    if spo2 is not None:
        if spo2 <= limits.spo2_critica_min:
            findings.append((AlertLevel.ROJA, f"Saturación de oxígeno crítica: {spo2}%"))
        elif spo2 < limits.spo2_min:
            findings.append((AlertLevel.AMARILLA, f"Saturación de oxígeno baja: {spo2}%"))

    # --- Temperatura corporal ---
    t = readout.temperatura
    if t is not None:
        if t >= limits.temp_critica_max or t <= limits.temp_critica_min:
            findings.append((AlertLevel.ROJA, f"Temperatura crítica: {t} °C"))
        elif t > limits.temp_max or t < limits.temp_min:
            findings.append((AlertLevel.AMARILLA, f"Temperatura fuera de rango: {t} °C"))

    # --- Dolor (0-10) ---
    dolor = readout.dolor
    if dolor is not None and dolor > limits.dolor_max:
        findings.append((AlertLevel.AMARILLA, f"Dolor significativo: {dolor}/10"))

    # --- Caída reportada (riesgo de lesión oculta; alta relevancia en mayores) ---
    if readout.caida_reportada:
        findings.append((AlertLevel.AMARILLA, "Reportó una caída"))

    # --- Peso: aumento brusco vs la última medición (posible retención/ICC) ---
    if readout.peso is not None and peso_anterior is not None:
        delta = readout.peso - peso_anterior
        reciente = dias_desde_peso is None or dias_desde_peso <= 7
        if delta >= limits.peso_delta_amarillo and reciente:
            findings.append((
                AlertLevel.AMARILLA,
                f"Aumento de peso brusco: +{delta:.1f} kg desde la última medición",
            ))

    # --- Adherencia a la medicación ---
    if readout.adherencia_medicacion == AdherenceState.NO_TOMO:
        findings.append((AlertLevel.AMARILLA, "No tomó la medicación prescrita"))
    elif readout.adherencia_medicacion == AdherenceState.TOMO_PARCIAL:
        findings.append((AlertLevel.AMARILLA, "Adherencia parcial a la medicación"))

    # --- Seguridad emocional (riesgo psicológico) → prioridad máxima ---
    # Va antes que el ánimo: una señal de riesgo pesa más que el ánimo general.
    if readout.riesgo_emocional == EmotionalRisk.RIESGO_SUICIDA:
        findings.append((
            AlertLevel.ROJA,
            "Riesgo emocional grave: posible ideación suicida o autolesión",
        ))
    elif readout.riesgo_emocional == EmotionalRisk.ANGUSTIA_AGUDA:
        findings.append((
            AlertLevel.AMARILLA,
            "Crisis emocional aguda / angustia marcada",
        ))

    # --- Estado de ánimo ---
    if readout.estado_animo == MoodState.ANGUSTIADO:
        findings.append((AlertLevel.AMARILLA, "Estado de ánimo: angustiado"))
    elif readout.estado_animo == MoodState.DECAIDO:
        findings.append((AlertLevel.AMARILLA, "Estado de ánimo: decaído"))

    if not findings:
        return TriageResult(
            paciente_id=readout.paciente_id,
            level=AlertLevel.VERDE,
            reasons=["Todos los parámetros dentro de rango. Paciente estable."],
        )

    level = max(level for level, _ in findings)
    # Ordena las razones por gravedad descendente para legibilidad del humano.
    reasons = [reason for lvl, reason in sorted(findings, key=lambda x: -x[0])]
    return TriageResult(paciente_id=readout.paciente_id, level=level, reasons=reasons)
