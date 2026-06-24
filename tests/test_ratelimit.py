"""Tests del rate limiter en memoria (ventana deslizante)."""
from health_monitor.ratelimit import check_rate, reset


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
