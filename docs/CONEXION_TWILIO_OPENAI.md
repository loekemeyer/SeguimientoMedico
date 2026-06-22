# Guía: conectar Twilio y OpenAI para llamadas reales

Esta guía te lleva paso a paso a obtener las credenciales y dejarlas cargadas.
Está pensada para alguien **sin experiencia técnica**.

---

## ⚠️ Antes que nada: ¿es gratis?

Seamos honestos para que no te lleves sorpresas en la tarjeta:

| Servicio | ¿Hay opción gratis? | Detalle |
|----------|---------------------|---------|
| **Twilio** | ✅ Sí (trial) | Te dan crédito de prueba (~USD 15) + un Sandbox de WhatsApp gratis para testear. Alcanza para varias pruebas. |
| **OpenAI Realtime** | ❌ No tiene capa gratis | Hay que cargar crédito (mínimo suele ser USD 5). Cada minuto de llamada cuesta centavos, así que con USD 5 hacés muchas pruebas. |

**Conclusión:** la parte de telefonía la probás gratis con el trial de Twilio. El
"cerebro de voz" (OpenAI) requiere cargar un mínimo de crédito (~USD 5). No
existe forma 100% gratuita de hacer la llamada con IA de voz hoy.

> Mientras no cargues nada, el sistema sigue funcionando en **modo demo**
> (`python scripts/demo_local.py`) sin costo.

---

## Paso 1 — Crear cuenta en Twilio

1. Entrá a **https://www.twilio.com/try-twilio** y registrate (es gratis).
2. Verificá tu email y tu número de teléfono.
3. Cuando entres al **Console** (panel principal), en la página de inicio vas a
   ver dos datos. Copialos:
   - **Account SID** (empieza con `AC...`)
   - **Auth Token** (hacé clic en "Show" para verlo)

### Activar el Sandbox de WhatsApp (gratis, para pruebas)

4. En el menú buscá: **Messaging → Try it out → Send a WhatsApp message**.
5. Te va a mostrar un número de Twilio y un código tipo `join algo-algo`.
6. Desde **tu** WhatsApp, mandá ese mensaje (`join algo-algo`) al número que
   indica. Eso "conecta" tu WhatsApp al sandbox para poder probar.
7. Anotá el número del sandbox (formato `whatsapp:+1...`).

---

## Paso 2 — Crear cuenta en OpenAI

1. Entrá a **https://platform.openai.com** y registrate / iniciá sesión.
2. Andá a **Settings → Billing** y cargá un crédito mínimo (USD 5 alcanza).
3. Andá a **API keys** (https://platform.openai.com/api-keys) →
   **Create new secret key**.
4. Copiá la clave (empieza con `sk-...`). **Solo se muestra una vez**, guardala.

---

## Paso 3 — Cargar todo en el archivo `.env`

En tu Codespace (o tu PC), en la terminal:

```bash
cp .env.example .env
```

Después abrí el archivo `.env` (clic en él en el explorador de la izquierda) y
completá estas líneas con lo que copiaste:

```env
# Clave de cifrado: generala con el comando de abajo y pegá el resultado
ENCRYPTION_KEY=

TWILIO_ACCOUNT_SID=AC...        # del Paso 1
TWILIO_AUTH_TOKEN=...           # del Paso 1
TWILIO_WHATSAPP_FROM=whatsapp:+1...   # número del sandbox (Paso 1)

OPENAI_API_KEY=sk-...           # del Paso 2
```

Para generar la `ENCRYPTION_KEY`, corré esto y pegá el resultado en el `.env`:

```bash
python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
```

> 🔒 El `.env` **nunca** se sube a GitHub (está protegido en `.gitignore`).
> Tus claves quedan solo en tu entorno.

---

## Paso 4 — Verificar que todo conecta (gratis)

```bash
pip install -r requirements.txt   # instala twilio y openai (si no lo hiciste)
python scripts/check_connections.py
```

Si ves tres ✓ verdes, las credenciales funcionan. Si algo falla, el script te
dice exactamente qué corregir. **Este chequeo no gasta crédito.**

---

## Paso 5 — Próximo (cuando los chequeos den verde)

Recién ahí tiene sentido conectar el flujo de llamada en vivo (Twilio Media
Streams ↔ Realtime API), que es donde empieza a consumir crédito de OpenAI.
Avisame cuando llegues al Paso 4 con todo en verde y seguimos con eso.

> Nota técnica: el código ya está preparado para Programmable Voice (llamada a un
> teléfono) con Media Streams. El "WhatsApp calling" tiene requisitos extra de
> habilitación; para la primera prueba conviene una llamada telefónica común a tu
> número verificado del trial, que es lo más rápido y barato de testear.
