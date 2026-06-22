"""Endpoints de autenticación: registro, login y datos del usuario."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.api.deps import get_current_user
from health_monitor.db.models import Usuario
from health_monitor.db.session import get_session
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
def register(data: RegistroIn, db: Session = Depends(get_session)) -> TokenOut:
    if db.scalar(select(Usuario).where(Usuario.email == data.email)):
        raise HTTPException(status_code=409, detail="Ese email ya está registrado")
    user = Usuario(
        email=data.email,
        password_hash=hash_password(data.password),
        nombre=data.nombre,
        plan="trial",
        suscripcion_vence=datetime.now(timezone.utc) + timedelta(days=_TRIAL_DAYS),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_session)) -> TokenOut:
    user = db.scalar(select(Usuario).where(Usuario.email == data.email.strip().lower()))
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
    )
