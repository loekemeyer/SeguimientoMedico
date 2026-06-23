"""Correlación de logs por request: un identificador único por petición.

Permite seguir una llamada/registro a través de todos los logs (clave para
depurar en producción y para una prepaga que audita). El id viaja en un
`ContextVar` (aislado por request) y se inyecta en cada línea de log.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")


def set_trace_id(value: str) -> None:
    _trace_id.set(value or "-")


def get_trace_id() -> str:
    return _trace_id.get()


class TraceIdFilter(logging.Filter):
    """Inyecta `trace_id` en cada LogRecord para poder formatearlo."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True
