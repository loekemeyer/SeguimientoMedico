"""Modelos ORM (SQLAlchemy 2.0) — versión SaaS multi-usuario.

Cada `Usuario` (familiar/cuidador que se suscribe) gestiona uno o más
`Paciente` (la persona monitoreada). Por paciente se cargan:
  - FichaClinica     : límites de control personalizados + patologías
  - Medicacion       : medicamentos, dosis y frecuencia
  - ContactoEmergencia: a quién avisar y en qué orden de escalamiento
  - EvolucionDiaria  : histórico de llamadas con triaje

Campos PII/clínicos sensibles se persisten cifrados (sufijo `_enc`); el
cifrado/descifrado se hace en la capa de servicio, no en el modelo.
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


class Usuario(Base):
    """Cuenta que se registra y suscribe para monitorear a sus familiares."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(String(120), default="")

    # Suscripción (el cobro real se integra aparte; acá vive el estado).
    plan: Mapped[str] = mapped_column(String(32), default="trial")  # trial|activo|cancelado
    suscripcion_vence: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    pacientes: Mapped[list["Paciente"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class Paciente(Base):
    """Persona monitoreada (la que recibe las llamadas de seguimiento)."""

    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    hce_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Datos de contacto cifrados (AES-256)
    nombre_enc: Mapped[str] = mapped_column(Text)
    telefono_whatsapp_enc: Mapped[str] = mapped_column(Text)

    # Consentimiento informado (Ley 25.326) — obligatorio para operar.
    consentimiento_firmado: Mapped[bool] = mapped_column(Boolean, default=False)
    consentimiento_fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consentimiento_apoderado_enc: Mapped[str | None] = mapped_column(Text)

    # Programación de la llamada de seguimiento (la define el usuario que contrata).
    llamada_activa: Mapped[bool] = mapped_column(Boolean, default=True)
    llamada_hora: Mapped[str] = mapped_column(String(5), default="10:00")  # "HH:MM" local
    llamada_zona: Mapped[str] = mapped_column(
        String(64), default="America/Argentina/Buenos_Aires"
    )
    # Días de la semana a llamar (0=lunes ... 6=domingo). Vacío = todos los días.
    llamada_dias: Mapped[list] = mapped_column(JSON, default=list)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    usuario: Mapped["Usuario"] = relationship(back_populates="pacientes")
    ficha: Mapped["FichaClinica"] = relationship(
        back_populates="paciente", uselist=False, cascade="all, delete-orphan"
    )
    medicaciones: Mapped[list["Medicacion"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan"
    )
    contactos: Mapped[list["ContactoEmergencia"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan"
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

    # Límites de control personalizados (espejo de triage.ClinicalLimits).
    limites: Mapped[dict] = mapped_column(JSON, default=dict)
    patologias: Mapped[list] = mapped_column(JSON, default=list)  # códigos CIE-10 / texto
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    paciente: Mapped["Paciente"] = relationship(back_populates="ficha")


class Medicacion(Base):
    """Un medicamento del plan del paciente (hábito de medicación)."""

    __tablename__ = "medicacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), index=True
    )
    nombre_enc: Mapped[str] = mapped_column(Text)  # droga + dosis (cifrado)
    frecuencia: Mapped[str] = mapped_column(String(120), default="")  # ej "1 por día, a la mañana"
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    paciente: Mapped["Paciente"] = relationship(back_populates="medicaciones")


class ContactoEmergencia(Base):
    """Familiar/responsable a notificar, con su nivel de escalamiento."""

    __tablename__ = "contactos_emergencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), index=True
    )
    nombre_enc: Mapped[str] = mapped_column(Text)
    telefono_enc: Mapped[str] = mapped_column(Text)
    relacion: Mapped[str] = mapped_column(String(60), default="")  # ej "hijo"
    # Orden de escalamiento: 1 se contacta primero, luego 2, etc.
    prioridad: Mapped[int] = mapped_column(Integer, default=1)
    recibe_alertas: Mapped[bool] = mapped_column(Boolean, default=True)

    paciente: Mapped["Paciente"] = relationship(back_populates="contactos")


class EvolucionDiaria(Base):
    __tablename__ = "evolucion_diaria"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), index=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    readout: Mapped[dict] = mapped_column(JSON, default=dict)  # ClinicalReadout serializado
    nivel_alerta: Mapped[str] = mapped_column(String(16), default="VERDE")
    motivos: Mapped[list] = mapped_column(JSON, default=list)
    # Resumen legible de la llamada, para que el familiar lo lea en la app.
    resumen: Mapped[str] = mapped_column(Text, default="")
    transcripcion_enc: Mapped[str | None] = mapped_column(Text)  # cifrada

    paciente: Mapped["Paciente"] = relationship(back_populates="evoluciones")
    notificaciones: Mapped[list["Notificacion"]] = relationship(
        back_populates="evolucion", cascade="all, delete-orphan"
    )


class Notificacion(Base):
    """Registro de cada mensaje/alerta enviada, para el seguimiento del familiar.

    Toda alerta (WhatsApp al familiar, webhook a emergencias) queda asentada acá,
    así el familiar ve en la app el historial real de qué se notificó y cuándo.
    """

    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(
        ForeignKey("pacientes.id", ondelete="CASCADE"), index=True
    )
    evolucion_id: Mapped[int | None] = mapped_column(
        ForeignKey("evolucion_diaria.id", ondelete="CASCADE"), index=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    canal: Mapped[str] = mapped_column(String(20))  # whatsapp | webhook | sms
    nivel_alerta: Mapped[str] = mapped_column(String(16), default="VERDE")
    destino_enc: Mapped[str] = mapped_column(Text)  # teléfono/endpoint cifrado
    destino_label: Mapped[str] = mapped_column(String(120), default="")  # ej "Thomas (hijo)"
    contenido: Mapped[str] = mapped_column(Text, default="")  # texto del mensaje
    enviado: Mapped[bool] = mapped_column(Boolean, default=False)

    evolucion: Mapped["EvolucionDiaria"] = relationship(back_populates="notificaciones")
