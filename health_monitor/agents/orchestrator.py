"""Orquestación de la llamada como máquina de estados (LangGraph).

Los tres agentes comparten un estado de conversación (`CallState`). El grafo:

    saludar ─▶ conversar ─┬─▶ extraer ─▶ supervisar ─┬─▶ cerrar
         ▲                │                           │
         └── (turno) ◀────┘            (ROJA) ────────┴─▶ interrumpir ─▶ cerrar

Si `langgraph` está instalado se compila un grafo real; si no, se ejecuta la
misma lógica con un runner secuencial equivalente (mismo `CallState`). Así la
orquestación es testeable sin la dependencia.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from health_monitor.agents import clinical, supervisor
from health_monitor.schemas.clinical import ClinicalReadout
from health_monitor.triage import AlertLevel, ClinicalLimits, TriageResult

logger = logging.getLogger(__name__)


@dataclass
class CallState:
    """Estado compartido entre los agentes durante una llamada."""

    paciente_id: int
    limits: ClinicalLimits
    paciente_nombre: str = ""
    # Cada contacto: {"telefono": str, "label": str, "recibe_alertas": bool}
    contactos: list[dict] = field(default_factory=list)
    ficha_resumen: str = ""
    rutina_resumen: str = ""  # texto con la rutina del paciente para guiar la charla
    historial_resumen: str = ""  # qué pasó en la última llamada (contexto para el agente)
    nivel_insistencia: int = 2  # 1=pasivo, 2=recordar, 3=insistir (lo fija el admin)

    transcript: str = ""
    readout: ClinicalReadout | None = None
    triage: TriageResult | None = None
    resumen: str = ""
    interrupted: bool = False
    # Lista de registros de notificación enviados (para persistir y mostrar).
    alerts_dispatched: list[dict] | None = None
    finished: bool = False


# --- Nodos del grafo (funciones puras sobre el estado) ---

def node_extract(state: CallState) -> CallState:
    """Agente 2: extrae métricas de la transcripción acumulada."""
    state.readout = clinical.extract_readout(state.paciente_id, state.transcript)
    return state


def node_supervise(state: CallState) -> CallState:
    """Agente 3: triaje + decisión de interrumpir."""
    assert state.readout is not None
    state.triage = supervisor.assess(state.readout, state.limits)
    if supervisor.should_interrupt_call(state.triage):
        state.interrupted = True
    return state


def node_dispatch(state: CallState) -> CallState:
    """Arma el resumen y dispara las alertas según el nivel de triaje."""
    assert state.triage is not None and state.readout is not None
    state.resumen = supervisor.build_resumen(
        state.readout, state.triage, state.paciente_nombre
    )
    state.alerts_dispatched = supervisor.dispatch_alerts(
        state.triage,
        contactos=state.contactos,
        ficha_resumen=state.ficha_resumen,
        paciente_nombre=state.paciente_nombre,
    )
    state.finished = True
    return state


def run_post_call(state: CallState) -> CallState:
    """Pipeline al cerrar la llamada (o ante evento crítico en vivo).

    Equivale a recorrer extract → supervise → dispatch. Si `langgraph` está
    disponible se usa el grafo compilado; si no, el runner secuencial.
    """
    graph = _try_build_langgraph()
    if graph is not None:
        result = graph.invoke(state)
        return result if isinstance(result, CallState) else CallState(**result)
    # Fallback secuencial.
    return node_dispatch(node_supervise(node_extract(state)))


def _try_build_langgraph():
    """Compila el StateGraph de LangGraph si la librería está instalada."""
    try:
        from langgraph.graph import END, START, StateGraph  # import perezoso
    except ImportError:
        return None
    try:
        g = StateGraph(CallState)
        g.add_node("extract", node_extract)
        g.add_node("supervise", node_supervise)
        g.add_node("dispatch", node_dispatch)
        g.add_edge(START, "extract")
        g.add_edge("extract", "supervise")
        g.add_edge("supervise", "dispatch")
        g.add_edge("dispatch", END)
        return g.compile()
    except Exception as exc:  # pragma: no cover
        logger.warning("No se pudo compilar LangGraph (%s); uso runner secuencial.", exc)
        return None


def live_critical_check(state: CallState, partial_transcript: str) -> bool:
    """Chequeo en vivo durante la llamada: ¿hay que interrumpir YA?

    Se ejecuta sobre transcripción parcial mientras el paciente habla. Devuelve
    True si el supervisor detecta nivel ROJA (síntoma de alarma o crítico).
    """
    state.transcript = partial_transcript
    readout = clinical.extract_readout(state.paciente_id, partial_transcript)
    triage = supervisor.assess(readout, state.limits)
    return triage.level == AlertLevel.ROJA
