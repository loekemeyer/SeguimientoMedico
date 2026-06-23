"""Tests de la vigencia de suscripción (función pura, sin DB)."""
from datetime import datetime, timedelta, timezone

from health_monitor.api.deps import subscription_active
from health_monitor.db.models import Usuario

_NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
_FUTURO = _NOW + timedelta(days=7)
_PASADO = _NOW - timedelta(days=1)


def _user(**kw) -> Usuario:
    base = dict(activo=True, plan="trial", suscripcion_vence=None)
    base.update(kw)
    u = Usuario()
    for k, v in base.items():
        setattr(u, k, v)
    return u


def test_trial_vigente_es_activo():
    assert subscription_active(_user(plan="trial", suscripcion_vence=_FUTURO), _NOW) is True


def test_trial_vencido_no_es_activo():
    assert subscription_active(_user(plan="trial", suscripcion_vence=_PASADO), _NOW) is False


def test_cancelado_nunca_es_activo():
    assert subscription_active(_user(plan="cancelado", suscripcion_vence=_FUTURO), _NOW) is False


def test_activo_sin_fecha_es_activo():
    assert subscription_active(_user(plan="activo", suscripcion_vence=None), _NOW) is True


def test_activo_vencido_no_es_activo():
    assert subscription_active(_user(plan="activo", suscripcion_vence=_PASADO), _NOW) is False


def test_usuario_dado_de_baja_no_es_activo():
    assert subscription_active(_user(activo=False, suscripcion_vence=_FUTURO), _NOW) is False


def test_trial_sin_fecha_no_es_activo():
    # Un trial sin fecha de vencimiento no se considera vigente.
    assert subscription_active(_user(plan="trial", suscripcion_vence=None), _NOW) is False


def test_fecha_naive_se_interpreta_como_utc():
    # SQLite devuelve datetimes sin zona; deben tratarse como UTC y no romper.
    naive_futuro = _FUTURO.replace(tzinfo=None)
    assert subscription_active(_user(plan="trial", suscripcion_vence=naive_futuro), _NOW) is True
