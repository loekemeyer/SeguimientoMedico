#!/usr/bin/env python3
"""Genera el PDF de avances de SeguimientoMedico desde la activación agéntica."""
import re
import unicodedata
from fpdf import FPDF

TEAL = (13, 148, 136)
TEAL_DARK = (15, 95, 88)
INK = (30, 41, 49)
SLATE = (90, 105, 115)
LINE = (210, 220, 220)
BGSOFT = (236, 248, 246)
RED = (198, 60, 60)

def san(s: str) -> str:
    """Mapea puntuación unicode a ASCII y saca lo no-latin1 (emojis)."""
    repl = {"—": "-", "–": "-", "•": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
            "→": "->", "←": "<-", "…": "...", "×": "x", "≥": ">=", "≤": "<=",
            "🇦🇷": "AR", "✓": "[ok]", "✗": "[x]", "💛": "", "🧠": "", "📊": "",
            "👵": "", "☎️": "", "💊": "", "🔔": "", "📞": ""}
    for a, b in repl.items():
        s = s.replace(a, b)
    out = []
    for ch in s:
        if ch in "\n\t":
            out.append(ch); continue
        try:
            ch.encode("latin-1"); out.append(ch)
        except UnicodeEncodeError:
            # quitar emojis y símbolos raros; conservar acentos castellanos
            d = unicodedata.normalize("NFKD", ch)
            asc = d.encode("latin-1", "ignore").decode("latin-1")
            out.append(asc)
    return "".join(out)


class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*SLATE)
        self.cell(0, 8, san("SeguimientoMedico - Reporte de avances"), align="L")
        self.cell(0, 8, "2026-06-24", align="R")
        self.ln(10)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*SLATE)
        self.cell(0, 8, f"Pagina {self.page_no()}", align="C")

    # --- helpers de contenido ---
    def h1(self, txt):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 17)
        self.set_text_color(*TEAL_DARK)
        self.multi_cell(0, 9, san(txt))
        self.ln(1)
        y = self.get_y()
        self.set_draw_color(*TEAL)
        self.set_line_width(0.6)
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(3)

    def h2(self, txt):
        self.ln(1)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 12.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 7, san(txt))
        self.ln(1)

    def body(self, txt):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.6, san(txt))
        self.ln(1)

    def bullet(self, txt, color=TEAL):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10.5)
        self.set_text_color(*color)
        x = self.get_x()
        self.cell(5, 5.6, san("-"))
        self.set_text_color(*INK)
        self.set_x(x + 5)
        self.multi_cell(0, 5.6, san(txt))

    def kpi_row(self, items):
        # items: list of (label, value)
        n = len(items)
        gap = 4
        w = (self.w - self.l_margin - self.r_margin - gap * (n - 1)) / n
        x0 = self.get_x(); y0 = self.get_y()
        for i, (lab, val) in enumerate(items):
            x = x0 + i * (w + gap)
            self.set_xy(x, y0)
            self.set_fill_color(*BGSOFT)
            self.set_draw_color(*LINE)
            self.rect(x, y0, w, 18, "DF")
            self.set_xy(x + 2, y0 + 2.5)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*SLATE)
            self.cell(w - 4, 4, san(lab))
            self.set_xy(x + 2, y0 + 7.5)
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(*TEAL_DARK)
            self.cell(w - 4, 8, san(val))
        self.set_xy(x0, y0 + 18 + 3)


def main():
    pdf = PDF(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(18, 16, 18)

    # ---------- PORTADA ----------
    pdf.add_page()
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, pdf.w, 78, "F")
    pdf.set_xy(18, 24)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 14, "SeguimientoMedico")
    pdf.set_xy(18, 42)
    pdf.set_font("Helvetica", "", 15)
    pdf.cell(0, 10, san("Reporte de avances - sesion agentica"))
    pdf.set_xy(18, 56)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "24 de junio de 2026")

    pdf.set_xy(18, 92)
    pdf.set_font("Helvetica", "", 11.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 6, san(
        "Este documento resume todo lo construido desde que se activo el trabajo "
        "con agentes expertos: una auditoria multi-experto del codigo, la "
        "resolucion de los problemas criticos de seguridad, el modulo de "
        "administrador (inteligencia de negocio), nuevas funciones del producto, "
        "y la documentacion estrategica de escala y marketing."))
    pdf.ln(3)
    pdf.kpi_row([("Versiones publicadas", "0.4.9 -> 0.4.22"),
                 ("Tests automatizados", "206 (verde)"),
                 ("Items criticos resueltos", "8")])
    pdf.kpi_row([("Expertos en auditoria", "6 en paralelo"),
                 ("Hallazgos -> backlog", "71 -> 40"),
                 ("Commits de la sesion", "14+")])

    pdf.ln(2)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*TEAL_DARK)
    pdf.multi_cell(0, 6, san("Veredicto de la auditoria"))
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(*SLATE)
    pdf.multi_cell(0, 5.4, san(
        "\"El nucleo cripto (AES-256-GCM, PBKDF2, HMAC) y el CRUD estan solidos. "
        "Se cerraron los agujeros que rompian flujos reales y bloqueaban cobrar: "
        "login del paciente fuerza-bruteable, falta de rate limiting, el chat "
        "pago sin validar suscripcion, y webhooks sin firma. Todo incremental y "
        "commiteable de a uno; ningun item es reescritura.\""))

    # ---------- 1. METODO AGENTICO ----------
    pdf.add_page()
    pdf.h1("1. El metodo: auditoria con 6 expertos en paralelo")
    pdf.body(
        "Se lanzo un workflow que puso a trabajar en paralelo a seis ingenieros "
        "expertos, cada uno con una mirada distinta sobre el codigo. Cada experto "
        "leyo los archivos reales y entrego hallazgos concretos (archivo, problema, "
        "fix y esfuerzo). Un septimo agente sintetizo los 71 hallazgos en un backlog "
        "unico, priorizado y accionable de 40 items.")
    pdf.h2("Las seis miradas")
    for t in [
        "Seguridad & Privacidad - tokens, cifrado, fuerza bruta, firma de webhooks.",
        "UX / PWA para adultos mayores - claridad, accesibilidad, estados de error.",
        "Correctitud backend & gating de pago - flujos, validaciones, casos borde.",
        "Escalabilidad a 1k-10k - migraciones, indices, archivado de historial.",
        "Pagos, negocio & modulo BI - cobro, rentabilidad, instrumentacion.",
        "Robustez del frontend - null-safety, errores de red, sesion persistente.",
    ]:
        pdf.bullet(t)
    pdf.ln(1)
    pdf.body(
        "Esa lista priorizada es la que guio el resto de la sesion: primero lo "
        "critico de seguridad, despues lo que faltaba para que el producto se "
        "sienta terminado, y por ultimo escala, negocio e instrumentacion.")

    # ---------- 2. SEGURIDAD ----------
    pdf.add_page()
    pdf.h1("2. Endurecimiento de seguridad (lo critico)")
    secs = [
        ("Firma de Twilio en /whatsapp/incoming",
         "Era un webhook publico que modificaba la historia clinica sin verificar "
         "firma. Ahora exige X-Twilio-Signature, con un guard compartido que ademas "
         "falla-cerrado en produccion (si esta mal configurado, rechaza)."),
        ("El chat pago valida la suscripcion de la familia",
         "La charla con IA es la funcion paga. Ahora un turno real valida que la "
         "familia tenga suscripcion vigente; si no, responde con carino y sin gastar "
         "API. El saludo inicial y la prueba de 14 dias siguen gratis."),
        ("Secretos fail-closed en produccion",
         "Fuera de entornos de desarrollo, si falta JWT_SECRET o el token de Twilio, "
         "la app deja de operar en vez de firmar con una clave publica. decode_token "
         "valida formato; el indice de telefono exige la clave de cifrado."),
        ("Rate limiting + anti fuerza-bruta del login",
         "Limitador en memoria: login familiar 8/min, registro 5/h, login del "
         "paciente 5/min por codigo y 20/min por IP. Ademas la clave rotativa de 2 "
         "digitos ahora tiene una sola combinacion valida casi todo el tiempo "
         "(1/100 en vez de 2/100)."),
        ("Bug de login por email (mayusculas)",
         "El registro guardaba el email sin normalizar y el login comparaba en "
         "minusculas: un email con mayusculas no podia entrar. Corregido."),
    ]
    for t, d in secs:
        pdf.h2(t)
        pdf.body(d)

    # ---------- 3. PRODUCTO ----------
    pdf.add_page()
    pdf.h1("3. Nuevas funciones del producto")
    feats = [
        ("Chat real del paciente (Acompanado)",
         "El boton 'Hablar' ahora abre una charla real con IA (OpenAI), con una "
         "personalidad calida en espanol rioplatense, personalizada con el nombre, "
         "el trato (vos/usted), el acompanante y los temas preferidos. Si falla la "
         "red, responde con carino y nunca rompe la pantalla."),
        ("Graficos de tendencia (sparklines)",
         "En el detalle de cada persona, mini-graficos de presion, peso y animo que "
         "muestran como vienen evolucionando los ultimos dias."),
        ("Telefono con bandera AR +54",
         "Los campos de telefono ya no piden escribir el codigo de pais: bandera "
         "argentina por defecto, cambiable, y el numero se arma solo."),
        ("Robustez del frontend",
         "El avatar ya no rompe con nombres vacios (antes deslogueaba). El arranque "
         "tolera tokens vencidos o la API caida sin dejar la pantalla en blanco. "
         "Candado anti doble-tap en login, registro y alta. Indicador 'escribiendo' "
         "en el chat."),
        ("Revision de cajas de texto",
         "Se verificaron los 57 campos del formulario: todos con estilo correcto, "
         "ninguno como caja cruda del navegador."),
    ]
    for t, d in feats:
        pdf.h2(t)
        pdf.body(d)

    # ---------- 4. MODULO ADMINISTRADOR / BI ----------
    pdf.add_page()
    pdf.h1("4. Modulo de administrador (inteligencia de negocio)")
    pdf.body(
        "Un panel privado, visible solo para el dueno (validado por email), que "
        "responde: cuanto cuesta y cuanto deja cada cliente, y como mejorar la "
        "rentabilidad.")
    pdf.h2("Que incluye")
    for t in [
        "Instrumentacion de uso (tabla EventoUso, append-only): se registra cada "
        "accion que cuesta plata (chat, llamada, login) con su costo estimado.",
        "KPIs del negocio: ingreso mensual, costo del periodo, margen y clientes "
        "activos/total.",
        "Rentabilidad por cliente: ingreso vs costo, margen, mix de modulos, "
        "ultima actividad; ordenado por lo que da perdida primero.",
        "Asesor de rentabilidad: recomendaciones concretas (clientes en perdida, "
        "planes a mover, inactivos, trials por convertir) que funcionan sin IA, "
        "mas una narrativa opcional con IA.",
        "Pantalla en la app: KPIs, asesor y tabla de clientes, accesible desde "
        "'Cuenta' solo si el backend reconoce al usuario como dueno.",
    ]:
        pdf.bullet(t)

    pdf.h2("Gating de negocio por plan")
    pdf.body(
        "Las llamadas telefonicas (las mas caras) ahora exigen el plan Telefono: un "
        "cliente que pago el plan App ya no puede disparar el costo del plan caro. "
        "Las cuentas de obra social operan siempre (las cubre el prestador) y la "
        "prueba gratis puede usar todo.")

    # ---------- 5. ESCALA Y ESTRATEGIA ----------
    pdf.add_page()
    pdf.h1("5. Documentacion estrategica")
    pdf.h2("Arquitectura para escalar a 1.000 - 10.000 clientes")
    pdf.body(
        "Documento que define como guardar la informacion para crecer sin "
        "reescribir: separar datos vivos de historicos, migraciones versionadas "
        "(Alembic), Postgres real con pool, indices, archivado hot/cold del "
        "historial y transcripciones a object storage, cifrado por sobre (envelope "
        "encryption con KMS), y - lo mas urgente - instrumentar el uso desde hoy "
        "(ya hecho) para no perder datos despues.")
    pdf.h2("Estrategia de marketing")
    pdf.body(
        "Como presentar el producto a clientes: propuesta de valor ('tu viejo "
        "acompanado todos los dias, vos tranquilo'), segmentos (hijos que cuidan a "
        "distancia, adultos mayores, obras sociales B2B), posicionamiento frente a "
        "las alternativas, pricing y empaquetado, copy listo para landing y "
        "anuncios, manejo de objeciones, canales de adquisicion, embudo con KPIs "
        "ligados al panel BI, guion de venta y un plan de lanzamiento a 90 dias.")

    # ---------- 6. HISTORIAL DE VERSIONES ----------
    pdf.add_page()
    pdf.h1("6. Historial de versiones de esta sesion")
    versions = [
        ("0.4.9", "Arreglo del bug de llamada (numero plano + from de voz), campo Hora, carrusel mobile"),
        ("0.4.10", "Chat real del paciente con OpenAI"),
        ("0.4.11", "Badge de estado junto al nombre"),
        ("0.4.12", "Graficos de tendencia (sparklines)"),
        ("0.4.13", "Instrumentacion de uso (EventoUso)"),
        ("0.4.14", "Panel BI: endpoints de rentabilidad"),
        ("0.4.15", "[sec] Firma Twilio en /whatsapp/incoming + revision de cajas de texto"),
        ("0.4.16", "[sec] El chat valida la suscripcion de la familia"),
        ("0.4.17", "[sec] Secretos fail-closed en produccion"),
        ("0.4.18", "[sec] Rate limiting + endurecer login del paciente"),
        ("0.4.19", "Robustez del frontend (avatar, bootstrap, doble-submit, typing)"),
        ("0.4.20", "Gate de llamadas por plan + obra social siempre activa + indice"),
        ("0.4.21", "Asesor agentico de rentabilidad (/bi/asesor)"),
        ("0.4.22", "Panel del dueno (BI) en el frontend"),
    ]
    pdf.set_font("Helvetica", "", 10)
    for v, d in versions:
        pdf.set_x(pdf.l_margin)
        pdf.set_text_color(*TEAL_DARK)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(16, 6, v)
        pdf.set_text_color(*INK)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_x(pdf.l_margin + 16)
        pdf.multi_cell(0, 6, san(d))

    pdf.ln(2)
    pdf.h2("Que sigue (del backlog priorizado)")
    for t in [
        "Adoptar Alembic (prerequisito para aplicar cambios de esquema en prod).",
        "Webhook de MercadoPago: que el pago active la suscripcion solo.",
        "Estados de offline / reintentar e iconos PNG de la PWA.",
        "Sacar el scheduler del proceso web y archivar el historial a object storage.",
    ]:
        pdf.bullet(t)
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 9.5)
    pdf.set_text_color(*SLATE)
    pdf.multi_cell(0, 5, san(
        "Todo el codigo esta en la rama claude/charming-knuth-ud3pq5 y en main "
        "(Render despliega solo). 206 tests automatizados en verde."))

    out = "/tmp/claude-0/-home-user-SeguimientoMedico/7dcb15f6-d9b6-500a-8656-1717f304bba9/scratchpad/SeguimientoMedico_avances.pdf"
    pdf.output(out)
    print("OK", out)


if __name__ == "__main__":
    main()
