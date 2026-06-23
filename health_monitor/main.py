"""FastAPI — Proyecto 1: Sistema de Acompañamiento y Monitoreo Crónico.

Expone:
  GET  /health                       healthcheck
  POST /calls/{paciente_id}/initiate inicia la llamada saliente (Twilio)
  POST /twilio/voice                 webhook TwiML que arranca el Media Stream
  WS   /twilio/media-stream          stream bidireccional de audio en tiempo real

La acción médica nunca la decide la IA (Human-in-the-loop): el sistema solo
recolecta, evalúa y notifica al humano responsable.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from health_monitor import __version__
from health_monitor.agents.orchestrator import run_post_call
from health_monitor.api import auth as auth_routes
from health_monitor.api import patients as patients_routes
from health_monitor.api.deps import require_active_subscription
from health_monitor.db.models import Paciente, Usuario
from health_monitor.db.session import get_session
from health_monitor.realtime.media_stream import MediaStreamBridge
from health_monitor.services import (
    build_call_state,
    persist_evolucion,
    require_consent,
)
from shared.auth import signing_secret
from shared.config import get_settings
from shared.twilio_security import (
    is_valid_twilio_signature,
    make_stream_token,
    verify_stream_token,
)

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="SeguimientoMedico — Health Monitor", version=__version__)
app.include_router(auth_routes.router)
app.include_router(patients_routes.router)


@app.on_event("startup")
def _startup() -> None:
    """Crea las tablas si no existen (cómodo en dev; en prod usar migraciones)."""
    try:
        from health_monitor.db.session import create_all
        create_all()
    except Exception as exc:  # la app igual sirve el frontend aunque la DB no esté
        logger.warning("No se pudieron crear/verificar las tablas al iniciar: %s", exc)


@app.get("/health")
def health() -> dict:
    """Healthcheck con la versión en curso para confirmar el build desplegado."""
    return {"status": "ok", "service": "health_monitor", "version": __version__}


# Frontend (app web para los familiares). Se monta al final para que las rutas
# de la API tengan prioridad; el resto sirve los archivos estáticos.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="frontend")


@app.post("/calls/{paciente_id}/initiate")
def initiate_call(
    paciente_id: int,
    user: Usuario = Depends(require_active_subscription),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Inicia una llamada saliente de seguimiento hacia el WhatsApp del paciente.

    Requiere usuario autenticado y dueño del paciente. Verifica el consentimiento
    informado (Ley 25.326) ANTES de llamar.
    """
    paciente = db.get(Paciente, paciente_id)
    if paciente is None or not paciente.activo or paciente.usuario_id != user.id:
        raise HTTPException(404, "Paciente no encontrado o inactivo")
    require_consent(paciente)

    settings = get_settings()
    if not (settings.twilio_account_sid and settings.public_base_url):
        return JSONResponse(
            {"detail": "Twilio no configurado; no se inició la llamada (modo dev)."},
            status_code=503,
        )

    from twilio.rest import Client  # import perezoso

    from shared.security import FieldCipher
    cipher = FieldCipher(settings.encryption_key)
    to_number = cipher.decrypt(paciente.telefono_whatsapp_enc)

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        to=f"whatsapp:{to_number}",
        from_=settings.twilio_whatsapp_from,
        url=f"{settings.public_base_url}/twilio/voice?paciente_id={paciente_id}",
    )
    return JSONResponse({"call_sid": call.sid, "paciente_id": paciente_id})


def _twilio_public_url(request: Request, settings) -> str:
    """Reconstruye la URL pública exacta que Twilio firmó (base + path + query)."""
    url = (settings.public_base_url or "").rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    return url


def _verify_twilio_signature(request: Request, params: dict, settings) -> None:
    """Valida el header X-Twilio-Signature; 403 si no coincide.

    En desarrollo (sin TWILIO_AUTH_TOKEN configurado) se omite con advertencia,
    para no frenar la demo ni los tests locales.
    """
    if not settings.twilio_auth_token:
        logger.warning("TWILIO_AUTH_TOKEN ausente; se omite validación de firma (modo dev).")
        return
    signature = request.headers.get("X-Twilio-Signature", "")
    url = _twilio_public_url(request, settings)
    if not is_valid_twilio_signature(settings.twilio_auth_token, signature, url, params):
        logger.warning("Firma de Twilio inválida en %s", request.url.path)
        raise HTTPException(status_code=403, detail="Firma de Twilio inválida")


@app.post("/twilio/voice")
async def twilio_voice(request: Request) -> Response:
    """Webhook TwiML: instruye a Twilio a abrir el Media Stream hacia el WS.

    Verifica la firma de Twilio y entrega al stream un token firmado de corta
    duración, que el WebSocket exige antes de operar (el WS no lleva firma).
    """
    settings = get_settings()
    form = dict(await request.form())
    _verify_twilio_signature(request, form, settings)

    paciente_id = request.query_params.get("paciente_id", "")
    ws_url = f"{settings.public_base_url.replace('https://', 'wss://')}/twilio/media-stream"
    token = make_stream_token(signing_secret(), int(paciente_id or 0))
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<Stream url="{ws_url}">'
        f'<Parameter name="paciente_id" value="{paciente_id}"/>'
        f'<Parameter name="token" value="{token}"/>'
        "</Stream></Connect></Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/twilio/media-stream")
async def media_stream(ws: WebSocket) -> None:
    """WebSocket bidireccional: puentea el audio Twilio <-> Realtime API."""
    await ws.accept()

    # El primer mensaje "start" trae los custom parameters (paciente_id + token).
    first = json.loads(await ws.receive_text())
    custom = first.get("start", {}).get("customParameters", {})
    paciente_id = int(custom.get("paciente_id", 0))

    # El WS no lleva firma de Twilio: exigimos el token emitido por /twilio/voice.
    if not verify_stream_token(signing_secret(), custom.get("token", ""), paciente_id):
        logger.warning("WS media-stream sin token válido (paciente %s); se cierra.", paciente_id)
        await ws.close(code=1008)  # 1008 = policy violation
        return

    db = next(get_session())
    try:
        state, nombre = build_call_state(db, paciente_id)
    except Exception as exc:
        logger.error("No se pudo preparar la llamada %s: %s", paciente_id, exc)
        await ws.close()
        return

    bridge = MediaStreamBridge(ws, state, nombre=nombre)
    try:
        await bridge.run()
    finally:
        # Al cerrar la llamada: extracción + triaje + alertas + persistencia.
        state.transcript = bridge.full_transcript
        state = run_post_call(state)
        persist_evolucion(db, state)
        db.close()
