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
    # Validar la firma X-Twilio-Signature de los webhooks. Desactivar SOLO en
    # entornos de prueba (p. ej. Codespaces) donde la URL pública puede no
    # coincidir exactamente con la que Twilio firmó.
    twilio_validate_signature: bool = True

    # Cerebro de IA
    realtime_provider: str = "openai"  # openai | gemini
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-realtime-mini"
    gemini_api_key: str = ""
    gemini_realtime_model: str = "gemini-2.0-flash-live"

    # Triaje / alertas
    emergency_webhook: str = ""  # central de emergencias / médico de guardia

    # Pagos / suscripción (pasarela: Mercado Pago por default). Sin token, el módulo
    # de pagos queda inerte y la app igual funciona (el estado vive en Usuario).
    mercadopago_access_token: str = ""

    # Operación
    environment: str = "dev"  # dev | production (en production, JWT_SECRET es obligatorio)
    log_level: str = "INFO"

    # Scheduler de llamadas automáticas. Desactivado por defecto: solo cuando se
    # prende (y Twilio está configurado) el sistema disca solo en el horario
    # programado de cada paciente.
    scheduler_enabled: bool = False
    scheduler_intervalo_min: int = 5  # cada cuánto revisa la agenda


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuración (cacheado)."""
    return Settings()
