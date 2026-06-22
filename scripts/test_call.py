"""Llamada de prueba: el sistema te llama y te habla (sin IA conversacional).

Usa TwiML inline con <Say> (voz en español), así NO necesita URL pública ni el
puente de audio en tiempo real. Sirve para confirmar que el sistema puede llamar
de verdad al teléfono. La conversación con IA se prueba aparte.

Requisitos:
  - TWILIO_VOICE_FROM en el .env = tu número de voz de Twilio (el del trial, +1...)
  - En cuenta trial, el número de destino debe estar VERIFICADO en Twilio.

Uso:
    python scripts/test_call.py +5491131181594
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import get_settings  # noqa: E402

MENSAJE = (
    "Hola, le hablo del servicio de acompañamiento Seguimiento Médico. "
    "Lo llamo para ver cómo se está sintiendo hoy. "
    "Esta es una llamada de prueba. Que tenga un muy buen día."
)


def main() -> None:
    destino = sys.argv[1] if len(sys.argv) > 1 else ""
    if not destino:
        print("✗ Pasá el número de destino. Ej: python scripts/test_call.py +5491131181594")
        sys.exit(1)

    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token):
        print("✗ Faltan credenciales de Twilio en el .env")
        sys.exit(1)
    if not s.twilio_voice_from:
        print("✗ Falta TWILIO_VOICE_FROM en el .env (tu número de voz de Twilio, +1...).")
        print("  Lo encontrás en Twilio: Phone Numbers → Manage → Active numbers.")
        sys.exit(1)

    try:
        from twilio.rest import Client
    except ImportError:
        print("✗ Falta la librería: pip install twilio")
        sys.exit(1)

    # Voz neural en español (Amazon Polly) vía TwiML inline.
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Say voice="Polly.Mia-Neural" language="es-MX">'
        f"{MENSAJE}"
        "</Say></Response>"
    )

    print(f"Llamando a {destino} desde {s.twilio_voice_from} ...")
    try:
        client = Client(s.twilio_account_sid, s.twilio_auth_token)
        call = client.calls.create(to=destino, from_=s.twilio_voice_from, twiml=twiml)
        print(f"✓ Llamada iniciada (sid={call.sid}). ¡Tu teléfono debería sonar!")
    except Exception as exc:
        print(f"✗ No se pudo llamar: {exc}")
        print("  Revisá: número de destino verificado en Twilio (trial), formato +549..., "
              "y que TWILIO_VOICE_FROM sea un número de voz válido.")
        sys.exit(1)


if __name__ == "__main__":
    main()
