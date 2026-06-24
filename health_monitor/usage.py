"""Registro de eventos de uso facturables — base del módulo BI del dueño.

Append-only y **best-effort**: si registrar un evento falla, NUNCA rompe la
acción principal (se descarta el evento y sigue). Cada acción que cuesta plata o
marca actividad del cliente llama a ``registrar_evento``. La estimación de costo
es aproximada y configurable; lo importante es tener el dato desde hoy.

Ver docs/ARQUITECTURA_ESCALA.md §5 y §6.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from health_monitor.db.models import EventoUso

# Tarifas estimadas (USD aprox., ajustables). Solo para estimar costo por cliente;
# no son facturación real. Afinar con los precios vigentes de Twilio/OpenAI.
COSTO_LLAMADA_POR_MIN = 0.04      # Twilio voz + Realtime API, aprox.
COSTO_WHATSAPP_POR_MSG = 0.01     # conversación/plantilla, aprox.
COSTO_CHAT_POR_1K_TOKENS = 0.0006  # gpt-4o-mini (entrada+salida), aprox.

# Tipos de evento (mantener en sync con el panel BI).
LLAMADA = "llamada"
WHATSAPP = "whatsapp"
CHAT_MSG = "chat_msg"
LOGIN_PACIENTE = "login_paciente"
ALERTA_FAMILIA = "alerta_familia"
INFO_CARGADA = "info_cargada"


def estimar_costo_chat(tokens: float) -> float:
    return round((tokens / 1000.0) * COSTO_CHAT_POR_1K_TOKENS, 6)


def estimar_costo_llamada(minutos: float) -> float:
    return round(minutos * COSTO_LLAMADA_POR_MIN, 6)


def estimar_tokens(*textos: str) -> int:
    """Estimación grosera de tokens (~4 chars/token) para acotar costo de chat."""
    chars = sum(len(t or "") for t in textos)
    return int(chars / 4 * 1.3) + 1


def registrar_evento(
    db: Session,
    *,
    tipo: str,
    modulo: str = "",
    usuario_id: int | None = None,
    paciente_id: int | None = None,
    unidades: float = 0.0,
    costo_estimado: float = 0.0,
    meta: dict | None = None,
    commit: bool = True,
) -> EventoUso | None:
    """Inserta un evento de uso. Best-effort: ante error, descarta y devuelve None."""
    try:
        ev = EventoUso(
            tipo=tipo,
            modulo=modulo,
            usuario_id=usuario_id,
            paciente_id=paciente_id,
            unidades=unidades,
            costo_estimado=costo_estimado,
            meta=meta or {},
        )
        db.add(ev)
        if commit:
            db.commit()
        return ev
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None
