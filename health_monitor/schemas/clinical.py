"""Esquema estructurado de métricas clínicas extraídas de la llamada.

Este es el objeto JSON que produce el **Agente 2 (Clínico)** a partir de la
transcripción del diálogo. Es la frontera entre el lenguaje natural y los datos
cuantitativos que consume el **Agente 3 (Supervisor)** para el triaje.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class MoodState(str, Enum):
    """Estado de ánimo auto-reportado o inferido durante la conversación."""

    BIEN = "bien"
    ESTABLE = "estable"
    DECAIDO = "decaido"
    ANGUSTIADO = "angustiado"
    DESCONOCIDO = "desconocido"


class AdherenceState(str, Enum):
    """Adherencia a la medicación prescrita."""

    TOMO_TODO = "tomo_todo"
    TOMO_PARCIAL = "tomo_parcial"
    NO_TOMO = "no_tomo"
    DESCONOCIDO = "desconocido"


class EmotionalRisk(str, Enum):
    """Riesgo emocional detectado en la conversación (seguridad psicológica).

    Es una dimensión SEPARADA del estado de ánimo: el ánimo describe cómo está la
    persona; esto marca una señal de seguridad que puede requerir contención y
    aviso inmediato. Se evalúa con criterio conservador (ante la duda, NINGUNO).
    """

    NINGUNO = "ninguno"
    # Angustia/crisis aguda, desesperanza marcada o soledad extrema, SIN contenido
    # explícito de querer morir o hacerse daño.
    ANGUSTIA_AGUDA = "angustia_aguda"
    # Ideación o intención suicida, deseo de morir, o autolesión (explícito).
    RIESGO_SUICIDA = "riesgo_suicida"


class ClinicalReadout(BaseModel):
    """Variables médicas estructuradas de una llamada de seguimiento.

    Todos los campos clínicos son opcionales: una llamada puede no obtener
    todas las métricas. `None` significa "no se pudo extraer", lo que el
    triaje trata distinto de un valor fuera de rango.
    """

    paciente_id: int = Field(..., description="ID del paciente en la HCE")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Signos vitales
    presion_sistolica: int | None = Field(None, ge=40, le=300, description="mmHg")
    presion_diastolica: int | None = Field(None, ge=20, le=200, description="mmHg")
    frecuencia_cardiaca: int | None = Field(None, ge=20, le=250, description="lpm")
    glucemia: int | None = Field(None, ge=20, le=800, description="mg/dL")
    saturacion_oxigeno: int | None = Field(None, ge=50, le=100, description="SpO2 %")
    temperatura: float | None = Field(None, ge=30.0, le=45.0, description="°C")
    dolor: int | None = Field(None, ge=0, le=10, description="Intensidad del dolor 0-10")
    peso: float | None = Field(None, ge=20.0, le=400.0, description="kg")

    # Estado subjetivo / conductual
    adherencia_medicacion: AdherenceState = AdherenceState.DESCONOCIDO
    estado_animo: MoodState = MoodState.DESCONOCIDO
    # Seguridad emocional: señal de crisis/riesgo (independiente del ánimo).
    riesgo_emocional: EmotionalRisk = EmotionalRisk.NINGUNO
    # Evento: la persona reportó una caída (alta incidencia y riesgo en adultos mayores).
    caida_reportada: bool = False

    # Síntomas reportados (texto libre normalizado)
    sintomas: list[str] = Field(default_factory=list)

    # Banderas de alarma detectadas directamente por el agente clínico
    # (p. ej. dolor de pecho, dificultad para respirar, mareo, confusión).
    sintomas_alarma: list[str] = Field(default_factory=list)

    notas_libres: str | None = None
