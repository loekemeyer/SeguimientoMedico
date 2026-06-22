"""Esquemas Pydantic de entrada/salida de la API REST (auth + CRUD)."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Autenticación ---

class RegistroIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    nombre: str = ""

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Email inválido")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioOut(BaseModel):
    id: int
    email: str
    nombre: str
    plan: str
    suscripcion_vence: datetime | None = None


# --- Pacientes ---

class PacienteIn(BaseModel):
    nombre: str
    telefono_whatsapp: str
    consentimiento_firmado: bool = False
    consentimiento_apoderado: str | None = None
    patologias: list[str] = Field(default_factory=list)
    limites: dict = Field(default_factory=dict)


class PacienteOut(BaseModel):
    id: int
    nombre: str
    telefono_whatsapp: str
    consentimiento_firmado: bool
    consentimiento_fecha: datetime | None = None
    patologias: list[str] = Field(default_factory=list)
    limites: dict = Field(default_factory=dict)
    activo: bool = True


# --- Medicación ---

class MedicacionIn(BaseModel):
    nombre: str  # droga + dosis, ej "Losartán 50mg"
    frecuencia: str = ""
    activa: bool = True


class MedicacionOut(MedicacionIn):
    id: int


# --- Contactos de emergencia ---

class ContactoIn(BaseModel):
    nombre: str
    telefono: str
    relacion: str = ""
    prioridad: int = 1
    recibe_alertas: bool = True


class ContactoOut(ContactoIn):
    id: int


# --- Evolución / historial ---

class EvolucionOut(BaseModel):
    id: int
    fecha: datetime
    nivel_alerta: str
    motivos: list[str] = Field(default_factory=list)
    readout: dict = Field(default_factory=dict)
