"""Modo WhatsApp por voz — seguimiento asíncrono y económico (sin minutos de tel.).

Endpoints:
  POST /whatsapp/iniciar/{paciente_id}  (admin) arranca la conversación con el
       primer mensaje de voz.
  POST /whatsapp/incoming               webhook de Twilio: llega un audio del
       paciente → se transcribe, se responde con audio y, al cerrar, corre el
       triaje + alertas + se guarda en la HCE (reusa el pipeline de la llamada).
  GET  /whatsapp/audio/{token}          sirve el audio TTS para que WhatsApp lo baje.
"""
from __future__ import annotations

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_monitor.agents.orchestrator import run_post_call
from health_monitor.api.deps import require_active_subscription
from health_monitor.db.models import ConversacionWhatsApp, Paciente, Usuario
from health_monitor.db.session import get_session
from health_monitor.services import build_call_state, persist_evolucion
from health_monitor.whatsapp import voice_chat
from shared.config import get_settings
from shared.notifications import send_whatsapp_message
from shared.security import FieldCipher, phone_index

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Audios TTS efímeros para que WhatsApp los descargue (token -> bytes mp3).
_AUDIO_CACHE: dict[str, bytes] = {}


def _host_audio(audio: bytes) -> str | None:
    """Guarda un audio y devuelve su URL pública (o None si no hay audio o URL)."""
    settings = get_settings()
    if not (audio and settings.public_base_url):
        return None
    token = uuid.uuid4().hex
    _AUDIO_CACHE[token] = audio
    return f"{settings.public_base_url.rstrip('/')}/whatsapp/audio/{token}.mp3"


def _enviar_voz(telefono: str, texto: str) -> None:
    """Manda el texto como audio por WhatsApp; si no se puede, manda el texto."""
    url = _host_audio(voice_chat.synthesize(texto))
    if url:
        send_whatsapp_message(telefono, media_url=url)
    else:
        send_whatsapp_message(telefono, texto)


def _telefono(db: Session, paciente_id: int) -> str:
    p = db.get(Paciente, paciente_id)
    return FieldCipher(get_settings().encryption_key).decrypt(p.telefono_whatsapp_enc)


@router.get("/audio/{token}")
def get_audio(token: str) -> Response:
    audio = _AUDIO_CACHE.get(token.removesuffix(".mp3"))
    if audio is None:
        raise HTTPException(404, "Audio no disponible")
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/iniciar/{paciente_id}")
def iniciar(
    paciente_id: int,
    user: Usuario = Depends(require_active_subscription),
    db: Session = Depends(get_session),
) -> dict:
    """Arranca un seguimiento por mensajes de voz de WhatsApp (lo dispara el admin)."""
    p = db.get(Paciente, paciente_id)
    if p is None or p.usuario_id != user.id:
        raise HTTPException(404, "Paciente no encontrado")

    state, nombre = build_call_state(db, paciente_id)
    telefono = _telefono(db, paciente_id)
    msg, _fin = voice_chat.next_assistant_message(
        [], "", nombre=nombre or "", rutina=state.rutina_resumen,
        nivel_insistencia=state.nivel_insistencia, historial_clinico=state.historial_resumen,
        trato=state.trato, acompanante_nombre=state.acompanante_nombre,
        temas_preferidos=state.temas_preferidos, temas_evitar=state.temas_evitar,
    )
    conv = ConversacionWhatsApp(
        paciente_id=paciente_id,
        telefono_index=phone_index(telefono, get_settings().encryption_key),
        estado="activa",
        historial=[{"role": "assistant", "content": msg}],
    )
    db.add(conv)
    db.commit()
    _enviar_voz(telefono, msg)
    return {"status": "iniciado", "conversacion_id": conv.id}


@router.post("/incoming")
async def incoming(request: Request, db: Session = Depends(get_session)) -> Response:
    """Webhook de Twilio: llegó un mensaje de voz del paciente."""
    form = dict(await request.form())
    settings = get_settings()
    desde = (form.get("From") or "").replace("whatsapp:", "").strip()

    conv = db.scalars(
        select(ConversacionWhatsApp)
        .where(
            ConversacionWhatsApp.telefono_index == phone_index(desde, settings.encryption_key),
            ConversacionWhatsApp.estado == "activa",
        )
        .order_by(ConversacionWhatsApp.id.desc())
    ).first()
    if conv is None:
        return Response(status_code=204)  # nadie esperando una respuesta de ese número

    # Transcribir el audio del paciente (o usar el texto si mandó texto).
    user_text = ""
    media_url = form.get("MediaUrl0")
    if media_url:
        try:
            r = httpx.get(
                media_url,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                timeout=30,
            )
            user_text = voice_chat.transcribe(r.content)
        except Exception as exc:
            logger.error("No se pudo bajar/transcribir el audio: %s", exc)
    user_text = user_text or (form.get("Body") or "").strip()

    state, nombre = build_call_state(db, conv.paciente_id)
    historial_previo = list(conv.historial or [])
    respuesta, terminado = voice_chat.next_assistant_message(
        historial_previo, user_text,
        nombre=nombre or "", rutina=state.rutina_resumen,
        nivel_insistencia=state.nivel_insistencia, historial_clinico=state.historial_resumen,
        trato=state.trato, acompanante_nombre=state.acompanante_nombre,
        temas_preferidos=state.temas_preferidos, temas_evitar=state.temas_evitar,
    )

    nuevo = historial_previo
    if user_text:
        nuevo = nuevo + [{"role": "user", "content": user_text}]
    conv.historial = nuevo + [{"role": "assistant", "content": respuesta}]

    _enviar_voz(_telefono(db, conv.paciente_id), respuesta)

    if terminado:
        conv.estado = "cerrada"
        dicho = " ".join(m["content"] for m in conv.historial if m["role"] == "user")
        state.transcript = dicho
        state = run_post_call(state)
        persist_evolucion(db, state)  # extrae métricas + triaje + alertas + HCE
    else:
        db.commit()

    return Response(status_code=204)
