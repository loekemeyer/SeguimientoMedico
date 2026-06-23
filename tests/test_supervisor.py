"""Tests del Supervisor: el aviso a la familia se adapta a crisis emocional vs médica.

No requiere red: sin Twilio configurado, `send_whatsapp_message`/`fire_webhook`
degradan a `enviado=False`, pero el `contenido` del mensaje igual se construye y es
lo que verificamos.
"""
from health_monitor.agents import supervisor
from health_monitor.triage import AlertLevel, TriageResult


def _contactos():
    return [{"telefono": "+5491100000000", "label": "Hija", "recibe_alertas": True}]


def _whatsapps(registros):
    return [r for r in registros if r["canal"] == "whatsapp"]


def test_roja_emocional_usa_mensaje_de_contencion_con_linea_de_ayuda():
    result = TriageResult(
        paciente_id=1,
        level=AlertLevel.ROJA,
        reasons=["Riesgo emocional grave: posible ideación suicida o autolesión"],
    )
    registros = supervisor.dispatch_alerts(
        result, contactos=_contactos(), ficha_resumen="", paciente_nombre="Rosa",
        riesgo_suicida=True,
    )
    msg = _whatsapps(registros)[0]["contenido"]
    assert "135" in msg or "línea de ayuda" in msg.lower()  # incluye recurso de crisis
    assert "compañía" in msg.lower() or "no lo dejes solo" in msg.lower()
    # NO debe enmarcarlo como una urgencia médica clásica.
    assert "signo de alarma" not in msg.lower()


def test_roja_medica_mantiene_el_mensaje_de_emergencia_medica():
    result = TriageResult(
        paciente_id=1,
        level=AlertLevel.ROJA,
        reasons=["Síntoma de alarma: dolor de pecho"],
    )
    registros = supervisor.dispatch_alerts(
        result, contactos=_contactos(), ficha_resumen="", paciente_nombre="Rosa",
        riesgo_suicida=False,
    )
    msg = _whatsapps(registros)[0]["contenido"]
    assert "signo de alarma" in msg.lower()
    assert "135" not in msg
