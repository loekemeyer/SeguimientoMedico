# Estado del proyecto y próximos pasos

> Documento para que cualquier persona del equipo entienda **qué se hizo**,
> **cómo verlo** y **qué falta**. Última actualización: ver historial de git.

## 1. Qué es

**SeguimientoMedico** es un backend + app web (SaaS) de acompañamiento de salud.
Un familiar/cuidador se registra, carga a la persona a cuidar con su rutina
(medicamentos, ejercicios, tomas de presión, horarios), y el sistema hace
llamadas de seguimiento y envía alertas por WhatsApp según el estado detectado
(triaje Verde / Amarilla / Roja).

---

## 2. Cómo VER lo que se hizo

### a) El código (sin instalar nada)
Repositorio en GitHub, rama `main`:
- **https://github.com/loekemeyer/SeguimientoMedico**
- Empezá por el `README.md` (visión general y arquitectura).
- El historial de commits cuenta la evolución paso a paso.

### b) Verlo FUNCIONANDO (en GitHub Codespaces, gratis, desde el navegador)
1. En el repo, botón verde **Code → Codespaces → Create codespace on main**.
2. Esperá a que instale todo (automático).
3. En la terminal, probá cualquiera de estas:

   **La app web (login + panel de familiares):**
   ```bash
   bash scripts/run_app.sh
   ```
   Después abrí el puerto **8001** que ofrece Codespaces ("Open in Browser").
   Creá una cuenta y agregá una persona con su rutina.

   **El flujo de alertas (sin servicios pagos):**
   ```bash
   python scripts/demo_local.py
   ```
   Simula 3 llamadas (Verde/Amarilla/Roja) y muestra los avisos que se enviarían.

   **Los tests automáticos:**
   ```bash
   pytest
   ```

---

## 3. Qué está HECHO ✅

- **Cuentas multi-usuario** (registro/login con token) — cada usuario ve solo sus pacientes.
- **App web** con diseño propio: acceso, panel de personas, detalle con
  rutina, contactos, programación e historial.
- **Carga de la persona a cuidar** con el nombre que el admin quiera (ej. "Papá").
- **Módulo Rutina**: medicamentos, ejercicios, tomas de presión, horarios de
  despertarse/acostarse — con tipo, frecuencia, horario y días (por defecto todos).
- **Programación de llamadas** por paciente (hora, zona, días).
- **Triaje automático** Verde/Amarilla/Roja con límites personalizados.
- **Alertas por WhatsApp** a los contactos de emergencia — **probado y funcionando**
  (mensajes reales recibidos). Los mensajes nombran al paciente como lo guarda el admin.
- **Registro de cada notificación** enviada (para seguimiento del familiar).
- **Cifrado AES-256** de datos sensibles + interoperabilidad **HL7/FHIR**.
- **Botones** "Llamar ahora" y "Editar" en la app.
- **Endurecimiento de seguridad**:
  - Validación de la **firma de Twilio** (`X-Twilio-Signature`) en los webhooks,
    y **token firmado de corta duración** para el WebSocket de Media Streams.
  - `JWT_SECRET` **obligatorio** en producción (`ENVIRONMENT=production`).
  - **Control de suscripción**: un plan vencido/cancelado puede leer sus datos
    pero no crear pacientes ni iniciar llamadas (respuesta `402`).
- **Suite de tests** automáticos en verde.

### Servicios externos ya conectados
- **Twilio** (WhatsApp sandbox): credenciales OK, envío de WhatsApp funcionando.
- **OpenAI**: credenciales OK (modelo `gpt-realtime-mini`).

---

## 4. Qué FALTA para la LLAMADA DE PRUEBA por voz

La app puede llamar y reproducir un mensaje de voz (`scripts/test_call.py`).
Para que funcione faltan estos pasos en la cuenta de Twilio:

1. **Completar el "Compliance Profile"** (perfil de cumplimiento) — elegir
   *Individual Profile* y cargar los datos. (Quedó a medio hacer.)
2. **Comprar un número de teléfono** con capacidad **Voice** (Phone Numbers →
   Buy a number → Country: United States → Capabilities: Voice). Gratis con el
   saldo del trial.
3. **Verificar el número de destino** (en trial solo se puede llamar a números
   verificados): Phone Numbers → Manage → **Verified Caller IDs**.
4. En el `.env`, completar:
   ```
   TWILIO_VOICE_FROM=+1XXXXXXXXXX   # el número comprado en el paso 2
   ```
5. Ejecutar:
   ```bash
   python scripts/test_call.py +54911XXXXXXXX
   ```
   El teléfono debería sonar y escuchar un mensaje en español.

---

## 5. Qué FALTA para PRODUCCIÓN (más adelante)

- **Llamada con IA conversacional** (que el paciente charle con el asistente):
  conectar Twilio Media Streams ↔ OpenAI Realtime. Requiere URL pública y
  pruebas del puente de audio (`health_monitor/realtime/media_stream.py`).
- **Plantillas de WhatsApp aprobadas por Meta** para los avisos proactivos
  (fuera del sandbox de pruebas).
- **Cobro / suscripción** (ej. MercadoPago) y **deploy en la nube** 24/7.
- **PostgreSQL** gestionada en producción (hoy se usa SQLite para desarrollo).
- Pulido de la app (edición de contactos/rutina, más validaciones, etc.).

---

## 6. Configuración (resumen técnico)

- Variables de entorno: copiar `.env.example` a `.env` y completar.
- Claves a generar: `ENCRYPTION_KEY` y `JWT_SECRET` (comandos en `.env.example`).
- Para desarrollo, usar `DATABASE_URL=sqlite:///./local.db`.
- Scripts útiles en `scripts/`:
  `run_app.sh`, `demo_local.py`, `check_connections.py`,
  `send_test_whatsapp.py`, `list_whatsapp_templates.py`, `test_call.py`,
  `run_scheduler.py`.
