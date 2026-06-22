"""Verifica que las credenciales de Twilio y OpenAI funcionen — SIN gastar (casi) nada.

- Twilio: consulta los datos de la cuenta (gratis) y muestra el saldo del trial.
- OpenAI: lista los modelos disponibles (gratis) y chequea que el modelo
  Realtime esté accesible. NO hace llamadas de audio (eso sí cobraría).

Uso (desde la raíz del repo, con el .env completo):

    python scripts/check_connections.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import get_settings  # noqa: E402

OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"


def check_encryption(s) -> bool:
    print("\n[1/3] Clave de cifrado (ENCRYPTION_KEY)")
    if not s.encryption_key:
        print(f"  {FAIL} Falta. Generala con:")
        print('      python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"')
        return False
    try:
        from shared.security import FieldCipher

        FieldCipher(s.encryption_key).encrypt("test")
        print(f"  {OK} Clave válida (AES-256).")
        return True
    except Exception as exc:
        print(f"  {FAIL} Clave inválida: {exc}")
        return False


def check_twilio(s) -> bool:
    print("\n[2/3] Twilio (telefonía / WhatsApp)")
    if not (s.twilio_account_sid and s.twilio_auth_token):
        print(f"  {FAIL} Faltan TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN en el .env")
        return False
    try:
        from twilio.rest import Client
    except ImportError:
        print(f"  {FAIL} Falta instalar la librería: pip install twilio")
        return False
    try:
        client = Client(s.twilio_account_sid, s.twilio_auth_token)
        acct = client.api.accounts(s.twilio_account_sid).fetch()
        print(f"  {OK} Credenciales OK. Cuenta '{acct.friendly_name}' ({acct.status}).")
        try:
            bal = client.balance.fetch()
            print(f"  {OK} Saldo disponible: {bal.balance} {bal.currency}")
        except Exception:
            print(f"  {WARN} No se pudo leer el saldo (no es bloqueante).")
        if not s.twilio_whatsapp_from:
            print(f"  {WARN} TWILIO_WHATSAPP_FROM vacío (usá el número del Sandbox de WhatsApp).")
        return True
    except Exception as exc:
        print(f"  {FAIL} Las credenciales no funcionan: {exc}")
        return False


def check_openai(s) -> bool:
    print("\n[3/3] OpenAI (cerebro de voz — Realtime API)")
    if not s.openai_api_key:
        print(f"  {FAIL} Falta OPENAI_API_KEY en el .env")
        return False
    try:
        from openai import OpenAI
    except ImportError:
        print(f"  {FAIL} Falta instalar la librería: pip install openai")
        return False
    try:
        client = OpenAI(api_key=s.openai_api_key)
        models = {m.id for m in client.models.list().data}
        print(f"  {OK} Credencial OK. {len(models)} modelos disponibles.")
        target = s.openai_realtime_model
        if target in models:
            print(f"  {OK} El modelo Realtime '{target}' está accesible.")
        else:
            realtime = [m for m in models if "realtime" in m]
            if realtime:
                print(f"  {WARN} '{target}' no aparece, pero hay otros Realtime: {realtime[:3]}")
            else:
                print(f"  {WARN} No se ven modelos Realtime. Verificá que tu cuenta tenga acceso/crédito.")
        return True
    except Exception as exc:
        print(f"  {FAIL} La credencial no funciona: {exc}")
        return False


def main() -> None:
    s = get_settings()
    print("=" * 60)
    print("  Chequeo de conexiones — Twilio / OpenAI")
    print("  (no realiza llamadas de audio: este chequeo es gratis)")
    print("=" * 60)

    results = [check_encryption(s), check_twilio(s), check_openai(s)]

    print("\n" + "=" * 60)
    if all(results):
        print(f"  {OK} Todo listo. Podés avanzar con la primera llamada de prueba.")
    else:
        print(f"  {WARN} Faltan cosas por configurar (ver arriba). Completá el .env y reintentá.")
    print("=" * 60)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
