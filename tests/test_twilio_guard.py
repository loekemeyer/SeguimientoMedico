"""Tests del guard de webhooks de Twilio (firma + fail-closed en producción)."""
import base64
import os

os.environ.setdefault("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import shared.config as cfg  # noqa: E402
from health_monitor.api.twilio_guard import verify_twilio_request  # noqa: E402
from shared.twilio_security import compute_twilio_signature  # noqa: E402


class _FakeURL:
    def __init__(self, path, query=""):
        self.path = path
        self.query = query


class _FakeRequest:
    def __init__(self, path, headers, query=""):
        self.url = _FakeURL(path, query)
        self.headers = headers


def _set(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    cfg.get_settings.cache_clear()


def test_dev_sin_token_omite(monkeypatch):
    _set(monkeypatch, ENVIRONMENT="dev", TWILIO_VALIDATE_SIGNATURE="true",
         TWILIO_AUTH_TOKEN="", PUBLIC_BASE_URL="https://x.test")
    # No debe lanzar: en dev sin token se omite.
    verify_twilio_request(_FakeRequest("/whatsapp/incoming", {}), {"From": "whatsapp:+1"})
    cfg.get_settings.cache_clear()


def test_prod_sin_token_falla_cerrado(monkeypatch):
    _set(monkeypatch, ENVIRONMENT="production", TWILIO_VALIDATE_SIGNATURE="true",
         TWILIO_AUTH_TOKEN="", PUBLIC_BASE_URL="https://x.test")
    with pytest.raises(HTTPException) as ei:
        verify_twilio_request(_FakeRequest("/whatsapp/incoming", {}), {})
    assert ei.value.status_code == 503
    cfg.get_settings.cache_clear()


def test_firma_invalida_rechaza(monkeypatch):
    _set(monkeypatch, ENVIRONMENT="dev", TWILIO_VALIDATE_SIGNATURE="true",
         TWILIO_AUTH_TOKEN="secrettoken", PUBLIC_BASE_URL="https://x.test")
    req = _FakeRequest("/whatsapp/incoming", {"X-Twilio-Signature": "malafirma"})
    with pytest.raises(HTTPException) as ei:
        verify_twilio_request(req, {"From": "whatsapp:+1"})
    assert ei.value.status_code == 403
    cfg.get_settings.cache_clear()


def test_firma_valida_pasa(monkeypatch):
    _set(monkeypatch, ENVIRONMENT="dev", TWILIO_VALIDATE_SIGNATURE="true",
         TWILIO_AUTH_TOKEN="secrettoken", PUBLIC_BASE_URL="https://x.test")
    params = {"From": "whatsapp:+1", "Body": "hola"}
    url = "https://x.test/whatsapp/incoming"
    firma = compute_twilio_signature("secrettoken", url, params)
    req = _FakeRequest("/whatsapp/incoming", {"X-Twilio-Signature": firma})
    verify_twilio_request(req, params)  # no lanza
    cfg.get_settings.cache_clear()
