"""Llamada de prueba CONVERSACIONAL: el sistema te llama y charlás con la IA.

A diferencia de `scripts/test_call.py` (que reproduce un mensaje grabado), esta
llamada conecta el audio en vivo con la Realtime API de OpenAI a través del
servidor (Twilio Media Streams <-> WebSocket).

REQUISITOS (todo en el .env, y el servidor corriendo y público):
  - El servidor levantado y con el puerto 8001 PÚBLICO:
        bash scripts/run_app.sh
  - En el .env:
        TWILIO_VOICE_FROM=+1...                      (tu número de voz de Twilio)
        PUBLIC_BASE_URL=https://....app.github.dev    (la URL pública del server)
        OPENAI_API_KEY=sk-...                         (con crédito; la voz cobra)
        TWILIO_VALIDATE_SIGNATURE=false               (para la prueba en Codespaces)
  - El número de destino VERIFICADO en Twilio (cuenta trial).

Usa la MISMA base SQLite que el servidor (local.db) y se asegura de que exista
un paciente con consentimiento para armar la llamada.

Uso:
    python scripts/test_call_ai.py +5491162521635
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# El servidor (run_app.sh) usa local.db; el disparador debe usar la MISMA base
# para que el paciente exista cuando el WebSocket arme el estado de la llamada.
os.environ["DATABASE_URL"] = "sqlite:///./local.db"

from shared.config import get_settings  # noqa: E402


def _ensure_paciente(db, settings) -> tuple[int, str]:
    """Devuelve (id, nombre) de un paciente con consentimiento; crea uno si no hay."""
    from health_monitor.db.models import FichaClinica, Paciente, Usuario
    from shared.auth import hash_password
    from shared.security import FieldCipher

    cipher = FieldCipher(settings.encryption_key)
    p = (
        db.query(Paciente)
        .filter(Paciente.consentimiento_firmado.is_(True), Paciente.activo.is_(True))
        .first()
    )
    if p is not None:
        return p.id, (cipher.decrypt(p.nombre_enc) if p.nombre_enc else "paciente")

    user = db.query(Usuario).filter_by(email="voicetest@seguimiento.app").one_or_none()
    if user is None:
        user = Usuario(
            email="voicetest@seguimiento.app",
            password_hash=hash_password("voicetest1234"),
            nombre="Prueba de Voz",
            plan="trial",
        )
        db.add(user)
        db.flush()
    p = Paciente(
        usuario_id=user.id,
        hce_id="VOICE-TEST",
        nombre_enc=cipher.encrypt("Alejandro"),
        telefono_whatsapp_enc=cipher.encrypt("+540000000000"),
        consentimiento_firmado=True,
        consentimiento_fecha=datetime.now(timezone.utc),
    )
    p.ficha = FichaClinica(limites={}, patologias=["I10"])
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id, "Alejandro"


def main() -> None:
    destino = sys.argv[1] if len(sys.argv) > 1 else ""
    if not destino:
        print("✗ Pasá el número de destino. Ej: python scripts/test_call_ai.py +5491162521635")
        sys.exit(1)

    s = get_settings()
    faltan = []
    if not (s.twilio_account_sid and s.twilio_auth_token):
        faltan.append("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN")
    if not s.twilio_voice_from:
        faltan.append("TWILIO_VOICE_FROM (tu número de voz de Twilio)")
    if not s.public_base_url:
        faltan.append("PUBLIC_BASE_URL (la URL pública del servidor)")
    if not s.openai_api_key:
        faltan.append("OPENAI_API_KEY")
    if faltan:
        print("✗ Faltan estas variables en el .env:")
        for f in faltan:
            print(f"    - {f}")
        sys.exit(1)

    from health_monitor.db.session import create_all, get_session

    create_all()
    db = next(get_session())
    try:
        pid, nombre = _ensure_paciente(db, s)
    finally:
        db.close()

    base = s.public_base_url.rstrip("/")
    webhook = f"{base}/twilio/voice?paciente_id={pid}"

    try:
        from twilio.rest import Client
    except ImportError:
        print("✗ Falta la librería: pip install twilio")
        sys.exit(1)

    print(f"Paciente para la llamada : id={pid} ({nombre})")
    print(f"Webhook de voz           : {webhook}")
    print(f"Llamando a {destino} desde {s.twilio_voice_from} ...")
    try:
        client = Client(s.twilio_account_sid, s.twilio_auth_token)
        call = client.calls.create(to=destino, from_=s.twilio_voice_from, url=webhook)
        print(f"✓ Llamada iniciada (sid={call.sid}). ¡Atendé y hablá con la IA! 🎧")
        print("  Mirá los logs del servidor (la otra terminal) para ver la conexión.")
    except Exception as exc:
        print(f"✗ No se pudo iniciar la llamada: {exc}")
        print("  Revisá: número de destino verificado, TWILIO_VOICE_FROM válido, "
              "y PUBLIC_BASE_URL correcta.")
        sys.exit(1)


if __name__ == "__main__":
    main()
