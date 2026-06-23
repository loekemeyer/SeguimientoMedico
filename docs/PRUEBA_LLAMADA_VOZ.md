# Prueba de la llamada conversacional (voz con IA)

Guía para terminar de probar la llamada donde el paciente **conversa con la IA**
(no el mensaje grabado, que ya funciona con `scripts/test_call.py`).

---

## 1. El bloqueo actual: el puerto de Codespaces

Para que la conversación funcione, **Twilio tiene que poder entrar a tu servidor**.
En Codespaces el puerto 8001 debe estar en **Público** (accesible sin login).

**Síntoma de que NO está bien:** la llamada entra, escuchás un *"application error"*
en inglés y corta; y en el log del server **no aparece** la línea
`Twilio pidió /twilio/voice`. Eso significa que Twilio golpeó la puerta y nadie
le abrió (Codespaces le pidió login y Twilio no sabe loguearse).

### Cómo verificarlo (test definitivo)
Desde el **celular** (sin la sesión de GitHub), abrí en el navegador:

```
<PUBLIC_BASE_URL>/health
```

- ✅ Si ves `{"status":"ok",...}` → el puerto está accesible.
- ❌ Si te pide **login de GitHub** o da error → hay que hacerlo público.

### Cómo hacerlo público
Pestaña **PORTS / PUERTOS** → puerto **8001** → click derecho →
**Port Visibility → Public**.

> ⚠️ Importante: **cada vez que reiniciás el server, el puerto puede volver a
> Private.** Reconfirmá que esté en **Public** después de reiniciar.

### Plan B si Codespaces no coopera
Si aun en Público Twilio no entra, usar **ngrok** (expone el puerto con una URL
pública sin login):
```bash
# instalar ngrok una vez, con tu authtoken de ngrok.com, y luego:
ngrok http 8001
```
Copiás la URL `https://....ngrok-free.app` que te da y la ponés como
`PUBLIC_BASE_URL` en el `.env` (y reiniciás el server).

---

## 2. Qué se arregló en el código

Bugs que igual te iban a cortar la llamada aunque el puerto funcionara:

- **WebSocket:** ahora espera el evento `start` de Twilio. Antes leía el primer
  mensaje (`connected`) y se cerraba al toque sin los parámetros.
- **Conexión OpenAI:** tolera distintas versiones de la librería `websockets`
  (`additional_headers` vs `extra_headers`), y registra el error si falla.
- **Idioma:** la IA tiene instrucción explícita de hablar **siempre en español**.
- **Logging:** el server ahora registra cada paso (Twilio llega → WS conecta →
  OpenAI conecta → conversación), para diagnosticar al instante.

---

## 3. Reintentar la prueba (paso a paso)

```bash
# 1) Traer el último código a main
git fetch origin && git merge origin/claude/charming-knuth-ud3pq5 && git push origin main

# 2) Reiniciar el server limpio (mata lo viejo y levanta de nuevo)
pkill -9 -f uvicorn 2>/dev/null; fuser -k 8001/tcp 2>/dev/null; sleep 4; (nohup bash scripts/run_app.sh > /tmp/server.log 2>&1 &); sleep 8; echo "=== LOG ==="; cat /tmp/server.log

# 3) >>> Asegurar que el puerto 8001 esté en PÚBLICO (pestaña PORTS) <<<
#    y verificar con el celular:  <PUBLIC_BASE_URL>/health

# 4) Disparar la llamada conversacional
python scripts/test_call_ai.py +5491162521635
```

### Leer qué pasó
Después de atender (o si corta), mirá el log:
```bash
tail -40 /tmp/server.log
```
- Si ves `Twilio pidió /twilio/voice` → Twilio entró ✅ (el puerto está bien).
- Si además ves `WS media-stream OK` y `Sesión Realtime abierta` → la IA conectó.
- Si ves un error después de esos → copialo y se ajusta.
- Si **no ves** `Twilio pidió /twilio/voice` → es el puerto (volver al punto 1).
