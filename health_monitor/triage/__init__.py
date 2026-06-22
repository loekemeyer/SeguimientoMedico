"""Lógica de triaje jerárquico (Agente Supervisor)."""

from health_monitor.triage.rules import (
    AlertLevel,
    ClinicalLimits,
    TriageResult,
    evaluate,
)

__all__ = ["AlertLevel", "ClinicalLimits", "TriageResult", "evaluate"]
