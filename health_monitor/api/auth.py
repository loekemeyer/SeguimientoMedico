"""Endpoints de autenticación: registro, login y datos del usuario."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.api.deps import get_current_user
from health_monitor.db.models import Usuario
from health_monitor.db.session import get_session
from health_monitor.ratelimit import enforce
from health_monitor.schemas.api import (
    LoginIn,
    RegistroIn,
    TokenOut,
    UsuarioOut,
)
from shared.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_TRIAL_DAYS = 14


@router.post("/register", response_model=TokenOut, status_code=201)
def register(data: RegistroIn, request: Request, db: Session = Depends(get_session)) -> TokenOut:
    enforce(request, bucket="register", limit=5, window=3600,
            detail="Muchos registros desde acá. Probá de nuevo en un rato.")
    email = data.email.strip().lower()  # normalizar: el login compara en minúsculas
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status_code=409, detail="Ese email ya está registrado")

    user = Usuario(
        email=email,
        password_hash=hash_password(data.password),
        nombre=data.nombre,
        tipo_cuenta=data.tipo_cuenta,
        plan="trial",
        suscripcion_vence=datetime.now(timezone.utc) + timedelta(days=_TRIAL_DAYS),
    )
    if data.tipo_cuenta == "obra_social":
        from health_monitor.cartilla import validar_afiliacion
        from shared.config import get_settings
        from shared.security import FieldCipher

        user.obra_social = data.obra_social.strip()
        if data.nro_afiliado.strip():
            cipher = FieldCipher(get_settings().encryption_key)
            user.nro_afiliado_enc = cipher.encrypt(data.nro_afiliado.strip())
        user.afiliacion_validada = validar_afiliacion(data.obra_social, data.nro_afiliado)

    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_session)) -> TokenOut:
    email = data.email.strip().lower()
    enforce(request, bucket="login", identity=email, limit=8, window=60,
            detail="Demasiados intentos. Esperá un minuto y probá de nuevo.")
    user = db.scalar(select(Usuario).where(Usuario.email == email))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UsuarioOut)
def me(user: Usuario = Depends(get_current_user)) -> UsuarioOut:
    return UsuarioOut(
        id=user.id,
        email=user.email,
        nombre=user.nombre,
        plan=user.plan,
        suscripcion_vence=user.suscripcion_vence,
        tipo_cuenta=user.tipo_cuenta,
        obra_social=user.obra_social,
        afiliacion_validada=user.afiliacion_validada,
    )
