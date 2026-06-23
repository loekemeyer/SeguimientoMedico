"""Configuración central cargada desde variables de entorno (.env).

Usa pydantic-settings para validar y tipar la configuración. Los valores
sensibles (claves, tokens) nunca se hardcodean: provienen del entorno.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Seguridad
    encryption_key: str = ""  # AES-256 en base64 (32 bytes)
    jwt_secret: str = ""  # secreto para firmar tokens de sesión

    # Base de datos
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/seguimiento"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_voice_from: str = ""  # número de voz de Twilio (trial) para llamadas
    twilio_content_sid: str = ""  # plantilla aprobada para mensajes proactivos
    public_base_url: str = ""

    # Cerebro de IA
    realtime_provider: str = "openai"  # openai | gemini
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-realtime-mini"
    gemini_api_key: str = ""
    gemini_realtime_model: str = "gemini-2.0-flash-live"

    # Triaje / alertas
    emergency_webhook: str = ""  # central de emergencias / médico de guardia

    # Operación
    environment: str = "dev"  # dev | production (en production, JWT_SECRET es obligatorio)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuración (cacheado)."""
    return Settings()
