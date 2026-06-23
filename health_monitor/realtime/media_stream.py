"""Puente de audio bidireccional: Twilio Media Streams <-> Realtime API.

Flujo (latencia < 1s, sin pasar por texto intermedio):

    WhatsApp ──audio mulaw/8000──▶ Twilio ──WS──▶ FastAPI (este puente)
                                                      │
                                                      ├──▶ Realtime API (OpenAI/Gemini)
                                                      │     audio-to-audio nativo
                                                      ◀── audio mulaw/8000 ──┘
    WhatsApp ◀──audio──── Twilio ◀──WS──── FastAPI

El puente reenvía frames de audio en ambas direcciones y, en paralelo, acumula
la transcripción que emite la Realtime API para alimentar al Agente Clínico y
al Supervisor (chequeo crítico en vivo → posible interrupción).

Twilio Media Streams envía mensajes JSON con eventos:
  - "start"  : metadata del stream (streamSid, callSid, custom parameters)
  - "media"  : { payload: base64(mulaw) }
  - "stop"   : fin del stream

La Realtime API de OpenAI espera/produce frames como eventos JSON
(`input_audio_buffer.append`, `response.audio.delta`, etc.).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging

from health_monitor.agents import orchestrator
from health_monitor.agents.companion import build_realtime_session_config, opening_line
from shared.config import get_settings

logger = logging.getLogger(__name__)

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"


class MediaStreamBridge:
    """Conecta un WebSocket de Twilio con la sesión Realtime de OpenAI.

    `twilio_ws` es el WebSocket (FastAPI/Starlette) hacia Twilio.
    `state` es el CallState de la llamada (para el chequeo crítico en vivo).
    """

    def __init__(self, twilio_ws, state: orchestrator.CallState, *, nombre: str | None = None):
        self.twilio_ws = twilio_ws
        self.state = state
        self.nombre = nombre
        self.stream_sid: str | None = None
        self.call_sid: str | None = None
        self.transcript_parts: list[str] = []
        self._openai_ws = None

    async def run(self) -> None:
        """Orquesta las dos corrutinas de reenvío hasta que la llamada termina."""
        settings = get_settings()
        if not settings.openai_api_key:
            logger.error("OPENAI_API_KEY ausente; no se puede abrir la sesión Realtime.")
            return
        try:
            import websockets  # import perezoso
        except ImportError:
            logger.error("Paquete 'websockets' no instalado; puente no disponible.")
            return

        url = OPENAI_REALTIME_URL.format(model=settings.openai_realtime_model)
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
        }
        logger.info("Conectando a OpenAI Realtime (modelo %s)...", settings.openai_realtime_model)
        try:
            openai_ws = await self._connect_openai(websockets, url, headers)
        except Exception as exc:
            logger.error("No se pudo conectar a OpenAI Realtime: %s", exc)
            return

        self._openai_ws = openai_ws
        try:
            await openai_ws.send(json.dumps(build_realtime_session_config()))
            await self._send_opening_line()
            logger.info("Sesión Realtime abierta y saludo enviado; conversación en curso.")
            await asyncio.gather(
                self._twilio_to_openai(),
                self._openai_to_twilio(),
            )
        except Exception as exc:
            logger.error("Error durante la conversación en vivo: %s", exc)
        finally:
            try:
                await openai_ws.close()
            except Exception:
                pass

    async def _connect_openai(self, websockets, url, headers):
        """Abre el WS hacia OpenAI tolerando distintas versiones de `websockets`.

        Las versiones nuevas usan `additional_headers`; las previas, `extra_headers`.
        """
        try:
            return await websockets.connect(url, additional_headers=headers)
        except TypeError:
            return await websockets.connect(url, extra_headers=headers)

    async def _send_opening_line(self) -> None:
        """Indica al modelo que abra la conversación con el saludo del contenedor."""
        await self._openai_ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "instructions": f"Saludá para abrir la llamada diciendo: {opening_line(self.nombre)}",
            },
        }))

    async def _twilio_to_openai(self) -> None:
        """Reenvía el audio entrante del paciente hacia la Realtime API."""
        async for raw in self.twilio_ws.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "start":
                self.stream_sid = msg["start"]["streamSid"]
            elif event == "media":
                await self._openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": msg["media"]["payload"],  # ya viene base64(mulaw)
                }))
            elif event == "stop":
                break

    async def _openai_to_twilio(self) -> None:
        """Reenvía el audio del modelo a Twilio y acumula la transcripción."""
        async for raw in self._openai_ws:
            evt = json.loads(raw)
            etype = evt.get("type")

            # GA emite "response.output_audio.delta"; la beta usaba "response.audio.delta".
            if etype in ("response.output_audio.delta", "response.audio.delta"):
                await self.twilio_ws.send_text(json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": evt["delta"]},
                }))

            elif etype in (
                "conversation.item.input_audio_transcription.completed",
                "response.output_audio_transcript.done",
                "response.audio_transcript.done",
            ):
                text = evt.get("transcript", "")
                if text:
                    self.transcript_parts.append(text)
                    await self._maybe_interrupt()

            elif etype == "response.function_call_arguments.done" and evt.get("name") == "end_call":
                logger.info("El asistente pidió terminar la llamada (end_call).")
                await self._hangup()
                return

    async def _maybe_interrupt(self) -> None:
        """Chequeo crítico en vivo: si el supervisor marca ROJA, interrumpe."""
        partial = " ".join(self.transcript_parts)
        # El chequeo es síncrono y liviano; se corre en un thread para no bloquear.
        critical = await asyncio.to_thread(
            orchestrator.live_critical_check, self.state, partial
        )
        if critical and not self.state.interrupted:
            self.state.interrupted = True
            logger.warning("Evento crítico en vivo (paciente %s): interrumpiendo.",
                           self.state.paciente_id)
            await self._openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "instructions": (
                        "Con calma y contención, decile que notaste algo importante "
                        "y que vas a avisar ahora mismo a quien puede ayudarlo. "
                        "Despedite con calidez."
                    ),
                },
            }))

    async def _hangup(self) -> None:
        """Cuelga la llamada vía la API REST de Twilio (cuando el asistente cierra)."""
        settings = get_settings()
        if not (self.call_sid and settings.twilio_account_sid and settings.twilio_auth_token):
            return

        def _do() -> None:
            from twilio.rest import Client
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            client.calls(self.call_sid).update(status="completed")

        # Pausa breve para que termine de reproducirse la despedida antes de cortar.
        await asyncio.sleep(2)
        try:
            await asyncio.to_thread(_do)
            logger.info("Llamada %s finalizada por el asistente.", self.call_sid)
        except Exception as exc:
            logger.error("No se pudo colgar la llamada %s: %s", self.call_sid, exc)

    @property
    def full_transcript(self) -> str:
        return " ".join(self.transcript_parts)
