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
    # Cómo entra: cuenta privada o vinculado a la cartilla de una obra social/prepaga.
    tipo_cuenta: str = "privado"  # privado | obra_social
    obra_social: str = ""
    nro_afiliado: str = ""

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Email inválido")
        return v

    @field_validator("tipo_cuenta")
    @classmethod
    def _valid_tipo(cls, v: str) -> str:
        return v if v in ("privado", "obra_social") else "privado"


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
    tipo_cuenta: str = "privado"
    obra_social: str = ""
    afiliacion_validada: bool = False


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


_VOCES_VALIDAS = {"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"}


class PersonalidadAcompanante(BaseModel):
    """Cómo es y cómo suena el acompañante para este paciente (personalización).

    Es lo que más ayuda a que la charla se sienta a medida y no robótica.
    """

    voz: str = "coral"
    velocidad: float = 0.9  # 0.25–1.5 (más bajo = más pausado)
    trato: str = "vos"  # vos | usted
    acompanante_nombre: str = ""  # cómo se presenta, ej "Sofía"
    temas_preferidos: str = ""  # temas que le gustan, texto libre (ej "fútbol, los nietos")
    temas_evitar: str = ""  # temas a evitar, texto libre

    @field_validator("voz")
    @classmethod
    def _valid_voz(cls, v: str) -> str:
        return v if v in _VOCES_VALIDAS else "coral"

    @field_validator("velocidad")
    @classmethod
    def _valid_velocidad(cls, v: float) -> float:
        return min(1.5, max(0.25, float(v)))

    @field_validator("trato")
    @classmethod
    def _valid_trato(cls, v: str) -> str:
        return v if v in ("vos", "usted") else "vos"


class PacienteIn(BaseModel):
    nombre: str
    telefono_whatsapp: str
    consentimiento_firmado: bool = False
    consentimiento_apoderado: str | None = None
    patologias: list[str] = Field(default_factory=list)
    limites: dict = Field(default_factory=dict)
    programacion: ProgramacionLlamada = Field(default_factory=ProgramacionLlamada)
    personalidad: PersonalidadAcompanante = Field(default_factory=PersonalidadAcompanante)


class PacienteOut(BaseModel):
    id: int
    nombre: str
    telefono_whatsapp: str
    consentimiento_firmado: bool
    consentimiento_fecha: datetime | None = None
    patologias: list[str] = Field(default_factory=list)
    limites: dict = Field(default_factory=dict)
    programacion: ProgramacionLlamada = Field(default_factory=ProgramacionLlamada)
    personalidad: PersonalidadAcompanante = Field(default_factory=PersonalidadAcompanante)
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
    aviso: str = "mensaje"  # mensaje (WhatsApp) | llamada | ninguno

    @field_validator("aviso")
    @classmethod
    def _valid_aviso(cls, v: str) -> str:
        return v if v in ("mensaje", "llamada", "ninguno") else "mensaje"


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
    relato: str = ""  # qué contó el paciente (narrativo/emocional)
