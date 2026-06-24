"""Acompañante: acceso del paciente con su código + clave rotativa de 2 dígitos.

El paciente entra a SU app ("Acompañante") con:
  - su **código de acceso** de 6 dígitos (fijo; lo ve el familiar en el panel), y
  - una **clave rotativa** de 2 dígitos que cambia cada 30s y aparece en el panel
    del familiar. Es un segundo factor: el familiar se la dicta o está al lado.

La clave rotativa es determinística (HMAC del código + la ventana de 30s con el
secreto del servidor): el panel del familiar y el login del paciente calculan la
misma sin guardar nada. La sesión del paciente NO caduca (se loguea una sola vez).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from shared.auth import signing_secret

VENTANA_SEG = 30  # la clave rotativa cambia cada 30 segundos


def clave_rotativa(codigo_acceso: str, *, ahora: float | None = None) -> str:
    """Clave de 2 dígitos (00–99), determinística por código y ventana de 30s."""
    t = int(ahora if ahora is not None else time.time())
    ventana = t // VENTANA_SEG
    msg = f"{codigo_acceso}:{ventana}".encode()
    dig = hmac.new(signing_secret().encode(), msg, hashlib.sha256).digest()
    return f"{dig[0] % 100:02d}"


def segundos_restantes(*, ahora: float | None = None) -> int:
    """Segundos hasta que la clave rotativa cambie (para el contador del panel)."""
    t = int(ahora if ahora is not None else time.time())
    return VENTANA_SEG - (t % VENTANA_SEG)


def clave_valida(codigo_acceso: str, clave: str, *, ahora: float | None = None) -> bool:
    """Valida la clave aceptando la ventana actual y la anterior (tolerancia al borde)."""
    if not clave:
        return False
    t = ahora if ahora is not None else time.time()
    validas = {
        clave_rotativa(codigo_acceso, ahora=t),
        clave_rotativa(codigo_acceso, ahora=t - VENTANA_SEG),
    }
    return clave.strip() in validas
