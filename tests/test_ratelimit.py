"""Tests del rate limiter en memoria (ventana deslizante)."""
import pytest
from fastapi import HTTPException

from health_monitor.ratelimit import check_rate, enforce, reset


class _Req:
    """Request mínimo para client_ip(): headers + client.host."""
    def __init__(self, xff: str = "", host: str = "9.9.9.9"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": host})()


def test_enforce_sin_ip_no_se_evade_rotando_xff():
    # include_ip=False: el cupo es por identidad (código), sin importar la IP.
    # Un atacante que rota X-Forwarded-For NO consigue presupuesto nuevo.
    reset()
    enforce(_Req(xff="1.1.1.1"), bucket="b", identity="cod", limit=2, window=60, include_ip=False)
    enforce(_Req(xff="2.2.2.2"), bucket="b", identity="cod", limit=2, window=60, include_ip=False)
    with pytest.raises(HTTPException):
        enforce(_Req(xff="3.3.3.3"), bucket="b", identity="cod", limit=2, window=60, include_ip=False)


def test_enforce_con_ip_da_cupo_por_ip():
    # include_ip=True (default): cada IP tiene su propio cupo (límite por-IP).
    reset()
    enforce(_Req(xff="1.1.1.1"), bucket="b", identity="cod", limit=1, window=60)
    enforce(_Req(xff="2.2.2.2"), bucket="b", identity="cod", limit=1, window=60)
    with pytest.raises(HTTPException):
        enforce(_Req(xff="1.1.1.1"), bucket="b", identity="cod", limit=1, window=60)


def test_permite_hasta_el_limite_y_luego_bloquea():
    reset()
    t = 1000.0
    # limit=3 en ventana de 60s
    assert check_rate("k", limit=3, window=60, now=t)
    assert check_rate("k", limit=3, window=60, now=t + 1)
    assert check_rate("k", limit=3, window=60, now=t + 2)
    assert not check_rate("k", limit=3, window=60, now=t + 3)  # 4º excede


def test_la_ventana_se_libera_con_el_tiempo():
    reset()
    t = 1000.0
    for i in range(3):
        assert check_rate("k", limit=3, window=60, now=t + i)
    assert not check_rate("k", limit=3, window=60, now=t + 3)
    # pasado el window, vuelve a permitir
    assert check_rate("k", limit=3, window=60, now=t + 61)


def test_claves_independientes():
    reset()
    t = 1000.0
    assert check_rate("a", limit=1, window=60, now=t)
    assert not check_rate("a", limit=1, window=60, now=t)
    assert check_rate("b", limit=1, window=60, now=t)  # otra clave, su propio cupo
