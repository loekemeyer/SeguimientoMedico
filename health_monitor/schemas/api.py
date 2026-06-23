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

class ProgramacionLlamada(BaseModel):
    """Cuándo llamar al paciente (lo configura el usuario que contrata)."""

    llamada_activa: bool = True
    llamada_hora: str = "10:00"  # "HH:MM" hora local
    llamada_zona: str = "America/Argentina/Buenos_Aires"
    llamada_dias: list[int] = Field(default_factory=list)  # 0=lun..6=dom; vacío=todos
    # Insistencia del asistente: 1=pasivo, 2=recordar, 3=insistir amablemente.
    nivel_insistencia: int = 2

    @field_validator("llamada_hora")
    @classmethod
    def _valid_hora(cls, v: str) -> str:
        try:
            hh, mm = (int(x) for x in v.split(":"))
            assert 0 <= hh <= 23 and 0 <= mm <= 59
        except Exception:
            raise ValueError("Hora inválida; usá formato HH:MM (00:00 a 23:59)")
        return f"{hh:02d}:{mm:02d}"

    @field_validator("nivel_insistencia")
    @classmethod
    def _valid_nivel(cls, v: int) -> int:
        return v if v in (1, 2, 3) else 2


class PacienteIn(BaseModel):
    nombre: str
    telefono_whatsapp: str
    consentimiento_firmado: bool = False
    consentimiento_apoderado: str | None = None
    patologias: list[str] = Field(default_factory=list)
    limites: dict = Field(default_factory=dict)
    programacion: ProgramacionLlamada = Field(default_factory=ProgramacionLlamada)


class PacienteOut(BaseModel):
    id: int
    nombre: str
    telefono_whatsapp: str
    consentimiento_firmado: bool
    consentimiento_fecha: datetime | None = None
    patologias: list[str] = Field(default_factory=list)
    limites: dict = Field(default_factory=dict)
    programacion: ProgramacionLlamada = Field(default_factory=ProgramacionLlamada)
    activo: bool = True


# --- Medicación ---

class RutinaItemIn(BaseModel):
    # medicamento | ejercicio | presion | despertar | acostar | otro
    tipo: str = "otro"
    nombre: str  # descripción, ej "Losartán 50mg" / "Caminar 20 min" / "Tomar presión"
    frecuencia: str = ""
    horario: str = ""
    dias: list[int] = Field(default_factory=list)  # 0=lun..6=dom; vacío = todos
    activa: bool = True


class RutinaItemOut(RutinaItemIn):
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
