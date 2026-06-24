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
from health_monitor.api.twilio_guard import verify_twilio_request
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
# Con tope de tamaño: descartamos los más viejos para no perder memoria sin límite.
_AUDIO_CACHE: dict[str, bytes] = {}
_AUDIO_CACHE_MAX = 200


def _host_audio(audio: bytes) -> str | None:
    """Guarda un audio y devuelve su URL pública (o None si no hay audio o URL)."""
    settings = get_settings()
    if not (audio and settings.public_base_url):
        return None
    token = uuid.uuid4().hex
    _AUDIO_CACHE[token] = audio
    while len(_AUDIO_CACHE) > _AUDIO_CACHE_MAX:  # dict ordenado por inserción: saco el más viejo
        del _AUDIO_CACHE[next(iter(_AUDIO_CACHE))]
    return f"{settings.public_base_url.rstrip('/')}/whatsapp/audio/{token}.mp3"


def _enviar_voz(telefono: str, texto: str) -> bool:
    """Manda el texto como audio por WhatsApp; si no se puede, manda el texto.

    Devuelve True si Twilio aceptó el envío, False si no (sin credenciales, o el
    número todavía no escribió 'join <código>' al sandbox / ventana de 24h cerrada).
    """
    url = _host_audio(voice_chat.synthesize(texto))
    if url:
        return send_whatsapp_message(telefono, media_url=url)
    return send_whatsapp_message(telefono, texto)


def _telefono(db: Session, paciente_id: int) -> str:
    p = db.get(Paciente, paciente_id)
    if p is None or not p.telefono_whatsapp_enc:
        return ""
    try:
        return FieldCipher(get_settings().encryption_key).decrypt(p.telefono_whatsapp_enc)
    except Exception:
        return ""


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

    from health_monitor.services import require_consent
    require_consent(p)  # Ley 25.326: sin consentimiento no se contacta (antes que nada)

    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token):
        return {
            "status": "no_disponible",
            "detail": ("WhatsApp todavía no está configurado (faltan las credenciales "
                       "de Twilio). Cargá TWILIO_ACCOUNT_SID y TWILIO_AUTH_TOKEN."),
        }

    # Todo lo que sigue toca servicios externos (IA, cifrado, Twilio): si algo
    # falla, devolvemos un mensaje claro en vez de un 500 ("Ocurrió un error").
    try:
        state, nombre = build_call_state(db, paciente_id)
        telefono = _telefono(db, paciente_id)
        msg, _fin = voice_chat.next_assistant_message(
            [], "", nombre=nombre or "", rutina=state.rutina_resumen,
            nivel_insistencia=state.nivel_insistencia, historial_clinico=state.historial_resumen,
            trato=state.trato, acompanante_nombre=state.acompanante_nombre,
            temas_preferidos=state.temas_preferidos, temas_evitar=state.temas_evitar,
            explorar_animo=state.explorar_animo, memoria=state.memoria,
            como_llamarlo=state.como_llamarlo,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error preparando el WhatsApp del paciente %s: %s", paciente_id, exc)
        return {"status": "error", "detail": f"No se pudo preparar el mensaje: {exc}"}

    enviado = _enviar_voz(telefono, msg)
    if not enviado:
        return {
            "status": "no_enviado",
            "detail": ("No se pudo entregar el WhatsApp. En el sandbox de Twilio, ese "
                       "número primero tiene que escribir 'join <código>' al "
                       "+14155238886; en producción se necesita una plantilla aprobada."),
        }
    conv = ConversacionWhatsApp(
        paciente_id=paciente_id,
        telefono_index=phone_index(telefono, s.encryption_key),
        estado="activa",
        historial=[{"role": "assistant", "content": msg}],
    )
    db.add(conv)
    db.commit()
    return {"status": "iniciado", "conversacion_id": conv.id}


@router.post("/incoming")
async def incoming(request: Request, db: Session = Depends(get_session)) -> Response:
    """Webhook de Twilio: llegó un mensaje de voz del paciente."""
    form = dict(await request.form())
    verify_twilio_request(request, form)  # endpoint público que muta la HCE: exige firma
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

    try:
        state, nombre = build_call_state(db, conv.paciente_id)
    except Exception as exc:
        # Paciente dado de baja / sin consentimiento / datos inconsistentes: cerramos
        # la conversación y cortamos limpio (evita 500 y la tormenta de reintentos de Twilio).
        logger.warning("Conversación %s sin paciente válido (%s): se cierra.", conv.id, exc)
        conv.estado = "cerrada"
        db.commit()
        return Response(status_code=204)
    historial_previo = list(conv.historial or [])
    respuesta, terminado = voice_chat.next_assistant_message(
        historial_previo, user_text,
        nombre=nombre or "", rutina=state.rutina_resumen,
        nivel_insistencia=state.nivel_insistencia, historial_clinico=state.historial_resumen,
        trato=state.trato, acompanante_nombre=state.acompanante_nombre,
        temas_preferidos=state.temas_preferidos, temas_evitar=state.temas_evitar,
        explorar_animo=state.explorar_animo, memoria=state.memoria,
        como_llamarlo=state.como_llamarlo,
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
