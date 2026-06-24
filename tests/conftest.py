"""Configuración compartida de los tests."""
import pytest


@pytest.fixture(autouse=True)
def _reset_ratelimit():
    """Limpia el rate limiter entre tests (su estado es global por proceso)."""
    from health_monitor.ratelimit import reset

    reset()
    yield
    reset()
