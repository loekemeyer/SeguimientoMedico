# Publicar la app online (Render) — URL fija, sin rm/run_app.sh

Con esto la app queda en una URL permanente (`https://...onrender.com`), accesible
desde cualquier celular, sin levantar nada en Codespaces. Es **gratis** e incluye
una base **PostgreSQL** (los datos persisten entre reinicios, a diferencia del SQLite
local). Cada `git push` a la rama vuelve a desplegar solo.

> No lo puedo hacer yo por vos porque necesito tu cuenta de hosting. Pero dejé todo
> en `render.yaml` para que sea de (casi) 1 clic. Son ~5 minutos.

## Pasos (1 sola vez)

1. **Generá la clave de cifrado.** En la terminal de Codespaces:
   ```bash
   python -c "from shared.security import generate_key; print(generate_key())"
   ```
   Copiá la cadena que imprime (base64 largo). Es tu **ENCRYPTION_KEY**.

2. Entrá a **https://render.com** y registrate con tu cuenta de **GitHub** (gratis).

3. Botón **New +** → **Blueprint**.

4. Elegí el repo **loekemeyer/SeguimientoMedico** y la rama
   **`claude/charming-knuth-ud3pq5`**. Render detecta `render.yaml` y muestra lo que
   va a crear (1 web + 1 base PostgreSQL).

5. Te va a pedir el valor de **ENCRYPTION_KEY** (es la única variable manual): pegá la
   que generaste en el paso 1. `JWT_SECRET` y la base de datos se crean solos.

6. **Apply / Create**. Render construye y despliega en ~3-5 min. Al terminar te da la
   URL pública, tipo `https://seguimientomedico.onrender.com`.

7. Abrí esa URL en el celular → **ya está online**. (Para instalarla como app: menú del
   navegador → "Agregar a la pantalla de inicio".)

## A tener en cuenta

- **Plan free:** la web se "duerme" tras un rato de inactividad; la primera visita
  después tarda ~30-60s en despertar. La base PostgreSQL free dura 90 días.
- **Llamadas por teléfono (plan Teléfono):** necesitan además las credenciales de
  Twilio cargadas como variables de entorno en Render: `TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN`, `TWILIO_VOICE_FROM` y `PUBLIC_BASE_URL` (la URL de Render).
  La app, el login y el chat por código funcionan sin eso.
- **Mercado Pago:** los links de los dos planes ya vienen por defecto. Para cambiarlos,
  cargá `MERCADOPAGO_SUSCRIPCION_URL` (App) y `MERCADOPAGO_SUSCRIPCION_URL_TELEFONO`
  (Teléfono) como variables de entorno en Render.
- **Rama, no main:** el deploy sale de `claude/charming-knuth-ud3pq5` (no toqué main).
