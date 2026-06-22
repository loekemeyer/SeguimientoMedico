"""Modelos ORM (SQLAlchemy 2.0) de la Historia Clínica Electrónica (HCE).

Tres tablas según la especificación:
  - pacientes          (contacto, ID HCE, teléfonos de familiares)
  - ficha_clinica      (límites médicos personalizados, medicación requerida)
  - evolucion_diaria   (registros diarios cuantitativos + estado de ánimo)

Campos PII/clínicos sensibles se persisten cifrados (ver `shared.security`).
Aquí se almacena el texto cifrado en columnas `*_enc`; el cifrado/descifrado
se hace en la capa de servicio, no en el modelo, para mantenerlo explícito.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Paciente(Base):
    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    hce_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Datos de contacto cifrados (AES-256)
    nombre_enc: Mapped[str] = mapped_column(Text)
    telefono_whatsapp_enc: Mapped[str] = mapped_column(Text)
    # Lista de teléfonos de familiares a cargo (cada uno cifrado), como JSON.
    familiares_enc: Mapped[list] = mapped_column(JSON, default=list)

    # Consentimiento informado (Ley 25.326) — obligatorio para operar.
    consentimiento_firmado: Mapped[bool] = mapped_column(Boolean, default=False)
    consentimiento_fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consentimiento_apoderado_enc: Mapped[str | None] = mapped_column(Text)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    ficha: Mapped["FichaClinica"] = relationship(
        back_populates="paciente", uselist=False, cascade="all, delete-orphan"
    )
    evoluciones: Mapped[list["EvolucionDiaria"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan"
    )


class FichaClinica(Base):
    __tablename__ = "ficha_clinica"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), unique=True
    )

    # Límites médicos personalizados (espejo de triage.ClinicalLimits).
    # Se guardan como JSON para flexibilidad por patología.
    limites: Mapped[dict] = mapped_column(JSON, default=dict)

    # Medicación requerida: lista de {droga, dosis, frecuencia} (cifrada como JSON).
    medicacion_enc: Mapped[list] = mapped_column(JSON, default=list)

    patologias: Mapped[list] = mapped_column(JSON, default=list)  # CIE-10 codes
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    paciente: Mapped["Paciente"] = relationship(back_populates="ficha")


class EvolucionDiaria(Base):
    __tablename__ = "evolucion_diaria"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), index=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Readout clínico estructurado (ClinicalReadout serializado).
    readout: Mapped[dict] = mapped_column(JSON, default=dict)

    # Resultado del triaje.
    nivel_alerta: Mapped[str] = mapped_column(String(16), default="VERDE")
    motivos: Mapped[list] = mapped_column(JSON, default=list)

    # Transcripción de la llamada (cifrada — dato sensible).
    transcripcion_enc: Mapped[str | None] = mapped_column(Text)

    paciente: Mapped["Paciente"] = relationship(back_populates="evoluciones")
