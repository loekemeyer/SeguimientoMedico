"""Envía UN mensaje de WhatsApp de prueba usando el sandbox de Twilio.

Sirve para confirmar que las credenciales y el número del sandbox funcionan,
enviando un mensaje real a un teléfono que ya se haya unido al sandbox
(con el "join ...").

Uso (desde la raíz del repo, con el .env completo):

    python scripts/send_test_whatsapp.py +5491131181594

Si no pasás número, usa la variable TEST_WHATSAPP_TO del entorno.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import get_settings  # noqa: E402
from shared.notifications import send_whatsapp_message  # noqa: E402


def main() -> None:
    destino = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TEST_WHATSAPP_TO", "")
    if not destino:
        print("✗ Pasá el número de destino. Ej: python scripts/send_test_whatsapp.py +5491131181594")
        sys.exit(1)

    s = get_settings()
    print("Configuración detectada:")
    print(f"  From (sandbox) : {s.twilio_whatsapp_from or '(vacío!)'}")
    print(f"  To             : {destino}")
    print(f"  Twilio SID     : {'OK' if s.twilio_account_sid else 'FALTA'}")
    print()

    # Usa TU plantilla (TWILIO_CONTENT_SID del .env) si está configurada;
    # si no, prueba con la plantilla de muestra de Twilio.
    if s.twilio_content_sid:
        content_sid = s.twilio_content_sid
        # Tu plantilla debe tener UNA variable {{1}}.
        variables = {"1": "Prueba de SeguimientoMedico ✅"}
        print(f"Enviando con tu plantilla (.env): {content_sid}")
    else:
        content_sid = "HXb5b62575e6e4ff6129ad7c8efe1f983e"
        variables = {"1": "12/1", "2": "3pm"}
        print(f"Enviando con plantilla de muestra: {content_sid}")
    enviado = send_whatsapp_message(destino, content_sid=content_sid, content_variables=variables)

    if enviado:
        print("✓ Mensaje enviado. Revisá el WhatsApp del número de destino.")
    else:
        print("✗ No se envió. Revisá:")
        print("  - Que el .env tenga TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM")
        print("  - Que el número de destino se haya unido al sandbox (mandó el 'join ...')")
        print("  - Que esté instalada la librería: pip install twilio")
        sys.exit(1)


if __name__ == "__main__":
    main()
