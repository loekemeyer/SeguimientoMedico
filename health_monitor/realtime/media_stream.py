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


def _arg(evt: dict, key: str, default: str = "") -> str:
    """Lee un argumento (viene como JSON string) de un evento de function call."""
    try:
        return json.loads(evt.get("arguments") or "{}").get(key, default)
    except Exception:
        return default


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
            await openai_ws.send(json.dumps(build_realtime_session_config(
                voice=self.state.voz,
                nombre=self.nombre or self.state.paciente_nombre,
                rutina=self.state.rutina_resumen,
                nivel_insistencia=self.state.nivel_insistencia,
                historial=self.state.historial_resumen,
                speed=self.state.voz_velocidad,
                trato=self.state.trato,
                acompanante_nombre=self.state.acompanante_nombre,
                temas_preferidos=self.state.temas_preferidos,
                temas_evitar=self.state.temas_evitar,
                explorar_animo=self.state.explorar_animo,
                memoria=self.state.memoria,
                como_llamarlo=self.state.como_llamarlo,
            )))
            await self._send_opening_line()
            logger.info("Sesión Realtime abierta y saludo enviado; conversación en curso.")
            # Cuando UNA de las dos corrutinas termina —p. ej. el paciente cuelga y
            # Twilio cierra el WS (Starlette se traga el WebSocketDisconnect, así que
            # _twilio_to_openai simplemente retorna)— hay que CANCELAR la otra. Si se
            # usara `gather`, quedaría esperando para siempre a la corrutina que sigue
            # leyendo de OpenAI, y el bloque que persiste el reporte (en main.py)
            # nunca correría. Por eso esperamos a la PRIMERA que termina y cancelamos.
            tasks = [
                asyncio.create_task(self._twilio_to_openai()),
                asyncio.create_task(self._openai_to_twilio()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:  # error al cerrar la otra punta: no es fatal
                    logger.debug("Tarea de reenvío cancelada con: %s", exc)
            for task in done:
                if task.exception() is not None:
                    logger.error("Reenvío de audio terminó con error: %s", task.exception())
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
                "instructions": (
                    "Abrí la llamada: saludá con calidez "
                    f"({opening_line(self.nombre, self.state.acompanante_nombre)}) "
                    "y enseguida empezá a repasar la rutina por el primer ítem, "
                    "con una sola pregunta."
                ),
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

            elif etype == "response.function_call_arguments.done":
                if await self._handle_function_call(evt):
                    return  # end_call → terminar el reenvío

    async def _maybe_interrupt(self) -> None:
        """Chequeo crítico en vivo. Ante una urgencia, inyecta una guía de contención.

        Distingue crisis emocional (NO cortar, quedarse y contener) de urgencia
        médica (avisar y acompañar). Nunca cuelga de golpe.
        """
        partial = " ".join(self.transcript_parts)
        # El chequeo es síncrono y liviano; se corre en un thread para no bloquear.
        kind = await asyncio.to_thread(
            orchestrator.live_critical_check, self.state, partial
        )
        if not kind or self.state.interrupted:
            return
        self.state.interrupted = True
        if kind == "emocional":
            logger.warning("Riesgo emocional en vivo (paciente %s): contención + aviso.",
                           self.state.paciente_id)
            instrucciones = (
                "La persona expresó algo muy delicado a nivel emocional. Con muchísima "
                "calma y cariño, QUEDATE con ella: validá lo que siente, agradecele que "
                "te lo haya confiado, y preguntale con suavidad si en este momento está "
                "a salvo y si tiene a alguien cerca. NO cortes la llamada por ningún "
                "motivo. Si confirmás que está en riesgo, usá la herramienta "
                "`escalar_a_familia` para avisar ahora mismo. Seguí acompañando."
            )
        else:
            logger.warning("Evento crítico médico en vivo (paciente %s): contención.",
                           self.state.paciente_id)
            instrucciones = (
                "Con calma y contención, decile que notaste algo importante para su "
                "salud y que vas a avisar ahora mismo a quien puede ayudarlo. No lo "
                "alarmes de más. Quedate acompañándolo; no cortes de golpe."
            )
        await self._openai_ws.send(json.dumps({
            "type": "response.create",
            "response": {"instructions": instrucciones},
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

    async def _handle_function_call(self, evt: dict) -> bool:
        """Ejecuta la herramienta que pidió el modelo. Devuelve True si hay que colgar."""
        name = evt.get("name")
        call_id = evt.get("call_id") or evt.get("item_id")
        if name == "end_call":
            logger.info("El asistente pidió terminar la llamada (end_call).")
            await self._hangup()
            return True
        if name == "escalar_a_familia":
            motivo = _arg(evt, "motivo", "una situación que necesita atención")
            ok = await asyncio.to_thread(self._do_escalar, motivo)
            salida = ("Listo: avisé a la familia." if ok
                      else "No pude avisar a la familia en este momento.")
            await self._send_function_output(call_id, salida)
        return False

    def _do_escalar(self, motivo: str) -> bool:
        """Avisa en vivo a los contactos del paciente (lo dispara el agente)."""
        from shared.notifications import send_whatsapp_message

        quien = self.state.paciente_nombre or "el paciente"
        msg = (f"🔴 {quien} — en la llamada de acompañamiento de hoy detectamos algo "
               f"importante: {motivo}. Por favor, comunicate con {quien} cuanto antes.")
        enviados = 0
        for c in self.state.contactos:
            if c.get("recibe_alertas", True) and c.get("telefono"):
                if send_whatsapp_message(c["telefono"], msg):
                    enviados += 1
        logger.warning("Escalamiento en vivo (paciente %s): %s (%d aviso/s).",
                       self.state.paciente_id, motivo, enviados)
        return enviados > 0

    async def _send_function_output(self, call_id: str | None, output: str) -> None:
        """Devuelve a OpenAI el resultado de la herramienta y pide que el modelo siga."""
        if call_id:
            await self._openai_ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call_id, "output": output},
            }))
        await self._openai_ws.send(json.dumps({"type": "response.create"}))

    @property
    def full_transcript(self) -> str:
        return " ".join(self.transcript_parts)
