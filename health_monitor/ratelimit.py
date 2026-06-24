"""Rate limiting liviano en memoria (por proceso).

Ventana deslizante por clave. Suficiente para frenar fuerza bruta en una
instancia (login del familiar y del paciente, registro, webhooks). Para
multi-instancia hay que respaldarlo en Redis/DB — ver docs/ARQUITECTURA_ESCALA.md.

Sin dependencias externas: usa una cola de timestamps por clave y la poda al
vuelo. `now` es inyectable para los tests.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_HITS: dict[str, deque[float]] = defaultdict(deque)


def _now() -> float:
    return time.monotonic()


def client_ip(request: Request) -> str:
    """IP del cliente respetando el proxy de Render (X-Forwarded-For)."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def check_rate(key: str, *, limit: int, window: float, now: float | None = None) -> bool:
    """True si el intento entra dentro del límite (y lo registra); False si lo excede."""
    t = now if now is not None else _now()
    dq = _HITS[key]
    cutoff = t - window
    while dq and dq[0] < cutoff:
        dq.popleft()
    if not dq:
        # No dejamos crecer el dict con claves muertas.
        _HITS.pop(key, None)
        dq = _HITS[key]
    if len(dq) >= limit:
        return False
    dq.append(t)
    return True


def enforce(
    request: Request,
    *,
    bucket: str,
    identity: str = "",
    limit: int,
    window: float,
    include_ip: bool = True,
    detail: str = "Demasiados intentos. Esperá un momento y probá de nuevo.",
) -> None:
    """Aplica el límite; lanza 429 si se excede.

    Clave = bucket + identidad (+ IP si `include_ip`). Con `include_ip=False` el
    límite es GLOBAL por identidad y NO se puede evadir rotando `X-Forwarded-For`:
    es lo que frena la fuerza bruta sobre un secreto de bajo espacio (la clave
    rotativa de 2 dígitos) cuando se conoce el código de acceso.
    """
    key = f"{bucket}|{identity}"
    if include_ip:
        key = f"{key}|{client_ip(request)}"
    if not check_rate(key, limit=limit, window=window):
        raise HTTPException(status_code=429, detail=detail)


def reset() -> None:
    """Limpia el estado (para tests)."""
    _HITS.clear()
