"""Lista las plantillas de WhatsApp (Content templates) de tu cuenta Twilio.

Cada plantilla tiene un ContentSid (empieza con HX...) que es lo que necesita el
sistema para mandar mensajes proactivos (alertas).

Uso (desde la raíz del repo, con el .env completo):

    python scripts/list_whatsapp_templates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import get_settings  # noqa: E402


def main() -> None:
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token):
        print("✗ Faltan credenciales de Twilio en el .env")
        sys.exit(1)
    try:
        from twilio.rest import Client
    except ImportError:
        print("✗ Falta la librería: pip install twilio")
        sys.exit(1)

    client = Client(s.twilio_account_sid, s.twilio_auth_token)
    try:
        contents = client.content.v1.contents.list(limit=50)
    except Exception as exc:
        print(f"✗ No se pudieron listar las plantillas: {exc}")
        sys.exit(1)

    if not contents:
        print("No hay plantillas en tu cuenta todavía.")
        print("Creá una en: Messaging → Content Template Builder (o avisame y la creamos).")
        return

    print(f"Plantillas encontradas ({len(contents)}):\n")
    for c in contents:
        print(f"  ContentSid : {c.sid}")
        print(f"  Nombre     : {c.friendly_name}")
        print(f"  Idioma     : {getattr(c, 'language', '-')}")
        # Muestra el texto de la plantilla si está disponible.
        types = getattr(c, "types", None) or {}
        for tipo, cfg in types.items():
            body = cfg.get("body") if isinstance(cfg, dict) else None
            if body:
                print(f"  Texto      : {body}")
        print("  " + "-" * 50)

    print("\nCopiá el ContentSid (HX...) de la plantilla que quieras usar y")
    print("pegalo en el .env como:  TWILIO_CONTENT_SID=HX...")


if __name__ == "__main__":
    main()
