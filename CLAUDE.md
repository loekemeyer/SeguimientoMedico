# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠ REGLA: preguntar QUIÉN habla y dejar cada pedido como tarea en su Planify

**Vale para TODOS los repos** (LK, Gestión Virgilio, Planify y cualquiera nuevo: copiar este
bloque al `CLAUDE.md` del repo nuevo). Objetivo del dueño: que ninguna tarea quede a medio
hacer sin figurar en la agenda de alguien.

1. **Al empezar la sesión, preguntar quién está hablando** (antes de hacer nada):
   *"¿Quién sos? (Thomas, Marianela, Luis, Gastón, …)"*. Si el mensaje ya lo dice, no repreguntar.
2. **Cada pedido de trabajo se registra como tarea en el Planify de esa persona**, apenas se
   empieza, con nombre MUY resumido (≤ 60 caracteres) y una nota de 1–3 líneas con el
   contexto. Queda `done=false` hasta que se cierre (punto 4). Si la sesión termina sin
   cerrar, la tarea queda en la agenda: ése es el objetivo.
3. **Excepción del dueño:** Thomas Loekemeyer NO usa Planify. Sus pedidos se cargan en el
   Planify de **Tomás Beviglia (employee_id 20)** con el nombre antepuesto por **`Th `**
   (ej. `Th Fecha estimada de entrega por zona`).

**Dónde:** proyecto Supabase de Gestión Virgilio `hrxfctzncixxqmpfhskv`, schema `planify`.
Empleados activos con Planify (`planify.employees`): Marianela Becker **38**, Luis Rial Otero
**52**, Gastón Dalponte **61**, Tomás Beviglia **20**, Gonzalez Tomas 16, Elías Irace 1,
Nazareno Rodríguez 27, Angely Asuaje 22, Viviana Gauna 4, Alan Gonzalez 5, Diego Mollo 44,
Nora Heredia 33, Juan Cruz Karaygan 51, Pablo Martos 6, Martín Cornejo 34, Martín Pregelj 15,
Romina Maturano 55, Iván Meta 58, Jhonny Cartaya 46. Si el nombre no está, buscar:
`select id, nombre from planify.employees where activo and nombre ilike '%<apellido>%'`.

```sql
-- alta (al empezar el pedido)
insert into planify.tasks (name, type, prio, time, date, note, rec, done, assignment_type,
  employee_id, department_id, system_generated, broadcast, created_at, updated_at)
values ('<resumen ≤60>', 'tarea', 'normal', '09:00', to_char(now() at time zone
  'America/Argentina/Buenos_Aires', 'YYYY-MM-DD'), '<contexto 1-3 líneas> — cargado desde
  sesión de Claude', 'none', false, 'employee', <employee_id>, null, false, false, now(), now())
returning id;
-- cierre (cuando la persona la da por terminada)
update planify.tasks set done = true, updated_at = now() where id = <id>;
```

Avisar en el chat el `id` al crearla y al cerrarla. No crear tareas para preguntas o consultas
que se responden en el momento; sólo para pedidos que implican hacer algo.

4. **Cierre por criterio propio, no sólo por "listo".** Claude evalúa si el objetivo del
   pedido se cumplió (lo entregado funciona, está commiteado/aplicado, y no quedó ninguna
   parte del pedido sin hacer). Cuando lo considere cumplido, pregunta **"¿Falta algo más
   para dar por cerrada la tarea?"** — si la persona dice que no (o no pide nada más
   dentro de esa tarea), `done=true`. Si dice "listo" antes, también se cierra. Lo que se
   pidió y quedó a medias NO se cierra: se deja abierta con la nota actualizada
   ("queda pendiente: …").

5. **Alerta de inactividad (1 hora).** Si hay tareas abiertas de esta sesión y pasa una
   hora sin mensajes, Claude escribe: *"Te estoy registrando estas tareas pendientes:
   … ¿Querés continuar alguna o damos por cerrada la charla?"* Cómo: al terminar un turno
   con tareas abiertas, si la sesión tiene `send_later` (Claude Code web/remoto) o
   `ScheduleWakeup`, armar UN recordatorio a 60 min (borrar el anterior si existía); al
   dispararse, si sigue habiendo tareas abiertas, mandar la alerta; si no, no decir nada.
   En una sesión local sin esas herramientas no hay forma de despertarse sola: en ese
   caso, al cerrar cada turno con tareas abiertas, dejar la lista escrita en el chat.

6. **Propagar la regla a todo repo nuevo.** Si en una charla se agrega o se toca por
   primera vez un repo que NO tiene este bloque en su `CLAUDE.md` (se lo trae de referencia,
   se lo crea, o se le hace un cambio), copiarle este bloque entero (creando el `CLAUDE.md`
   si no existe) y commitearlo en ese repo, avisando en el chat. Así el dueño no tiene que
   pedirlo cada vez. Fuente canónica del bloque: `CLAUDE.md` de `loekemeyer/pagina-LK-copia`.

## Commands

```bash
pip install -r requirements.txt

# Tests (config in pyproject.toml: testpaths=["tests"], pythonpath=["."])
pytest                              # full suite
pytest tests/test_triage.py         # single file
pytest tests/test_triage.py::test_evaluar_metricas_normales   # single test
pytest -k "fhir"                    # by keyword

# Dev server (genera .dev_secrets.env la primera vez, SQLite local, puerto 8001)
bash scripts/run_app.sh

# Demo end-to-end sin Twilio / OpenAI / red (Verde / Amarilla / Roja)
python scripts/demo_local.py

# PostgreSQL local (opcional, schema en health_monitor/db/)
docker compose up -d db
```

No hay lint/format configurado (sin ruff, black, mypy, ni Makefile).

**`.dev_secrets.env` es persistente a propósito** (`scripts/run_app.sh:11-22`): regenerar `ENCRYPTION_KEY` deja ilegibles los datos cifrados de corridas anteriores. Está en `.gitignore`.

## Arquitectura

### Orquestación de la llamada (`health_monitor/agents/orchestrator.py`)

Tres agentes comparten un `CallState` (dataclass con paciente_id, límites clínicos, transcript, readout, triaje, alertas). El grafo:

```
saludar → conversar → extraer (Clínico) → supervisar (Supervisor) ─┬─ ROJA → interrumpir → cerrar
                                                                    └─ resto  → cerrar
```

Si `langgraph` está instalado compila un `StateGraph` real; si no, corre un runner secuencial equivalente con la misma lógica y el mismo `CallState`. **La orquestación es testeable sin la dependencia** — este patrón se repite en todo el proyecto.

- **Contenedor** (`agents/companion.py`): construye la sesión Realtime (OpenAI o Gemini según `realtime_provider`). Inyecta voz, trato, temas_preferidos/evitar y memoria previa del paciente al system prompt.
- **Clínico** (`agents/clinical.py`): extrae `ClinicalReadout` del transcript. Si hay `OPENAI_API_KEY` usa LLM con structured output; si no, regex heurística determinística. Detecta síntomas de alarma y ideación suicida (lista en el módulo).
- **Supervisor** (`agents/supervisor.py`): triaje **determinístico** contra `ClinicalLimits` (Verde/Amarilla/Roja), arma resumen para familia, dispara alertas. La IA nunca decide la acción médica — la regla de triaje es código auditable, no LLM.

`run_post_call()` se llama al final de `realtime/media_stream.py`. Durante la llamada, `live_critical_check()` escanea el transcript parcial para señales rojas y puede interrumpir.

### Modo degradado (lazy imports)

El core funciona y se testea sin Twilio / OpenAI / LangGraph / websockets. Cada integración externa está envuelta en `try: import X ... except ImportError: fallback/log`. Lugares clave:

- `realtime/media_stream.py` — websockets / OpenAI Realtime.
- `agents/orchestrator.py` — langgraph (fallback secuencial).
- `agents/clinical.py` — OpenAI (fallback heurístico).
- `memoria.py` — OpenAI (fallback append+truncate a 1800 chars).
- `health_monitor/main.py` — Twilio (`Client` se importa solo al iniciar una llamada; sin credenciales devuelve 503).
- `shared/notifications.py` — Twilio WhatsApp (sin credenciales loguea y retorna False).

**Si agregás una dependencia externa, seguí este patrón** — los tests no instalan integraciones pagas.

### Cifrado de campos (Ley 25.326, AR)

`shared/security.py` implementa `FieldCipher` con **AES-256-GCM** (nonce 12 bytes random + tag, base64 urlsafe). Todos los campos PII/clínicos en `db/models.py` llevan sufijo `_enc` (`nombre_enc`, `telefono_whatsapp_enc`, `memoria_enc`, etc.). El servicio (`health_monitor/services.py`) descifra al cargar y re-cifra al guardar.

- `phone_index()` produce un hash HMAC-SHA256 determinístico para buscar por teléfono sin descifrar.
- **Fail-closed**: si falta `ENCRYPTION_KEY` la app no arranca. En producción, si falta `JWT_SECRET` y `ENVIRONMENT=production`, tampoco. Mantener este comportamiento.
- **Nunca regenerar `ENCRYPTION_KEY` con datos existentes** — los descifra a la nada.

### API SaaS multi-tenant (`health_monitor/api/`)

- **Modelo**: `Usuario` (familiar/cuidador) → N `Paciente`. JWT Bearer, hash de password.
- **Guards** en `deps.py`: `get_current_user` (401), `require_active_subscription` (402 si vencida o cancelada; cuentas de obra social bypassean tiers pagos), `require_plan_telefono` (sólo plan telefónico puede iniciar llamadas).
- **Planes**: `app` vs `telefono`; pagos vía links de Mercado Pago (no-code) con webhook opcional.
- **Consentimiento**: `Paciente.consentimiento_firmado=True` + fecha es requisito legal para cualquier llamada. No hay bypass para demo ni tests.

### Pipeline de voz Twilio ↔ OpenAI/Gemini (`realtime/media_stream.py`)

WebSocket bidireccional, audio mulaw/8000, latencia <1s, **sin transcripción intermedia para "pensar"** (audio-to-audio nativo en el modelo Realtime). La transcripción se acumula en paralelo solo para alimentar al Clínico y al live check del Supervisor.

`MediaStreamBridge.run()` corre dos tasks concurrentes (Twilio→Realtime, Realtime→Twilio). El endpoint `/twilio/voice` (`main.py`) emite un **token firmado de corta duración** que se pasa a Twilio como custom param; el WS `/twilio/media-stream` valida ese token antes de abrir el stream de audio (`shared/twilio_security.py`). El WS no usa Bearer.

### Base de datos

SQLAlchemy 2.0 ORM. `db/session.py` crea el engine con `pool_pre_ping=True`; para SQLite añade `check_same_thread=False`. **No hay Alembic** — `db/migrate.py::apply_safe_migrations()` agrega columnas/índices faltantes de forma idempotente al startup. Sirve hasta que el esquema necesite drops/renames.

`DATABASE_URL` decide SQLite (default dev) vs Postgres (render.yaml). El demo y los tests usan SQLite.

### Triaje y alertas

`triage/rules.py` define `AlertLevel` y la función `evaluate()` que compara `ClinicalReadout` contra `ClinicalLimits` (mínimos/máximos por paciente, templated por patología en `triage/plantillas.py` — hipertensión, diabetes, IC).

- **VERDE**: log en `EvolucionDiaria` (+ resumen opcional a familia).
- **AMARILLA**: WhatsApp a familia + webhook.
- **ROJA**: interrumpe la llamada con contención, dispara webhook de emergencia, WhatsApp a contactos.

`supervisor.dispatch_alerts()` recorre `ContactoEmergencia` por prioridad y graba cada `Notificacion` en DB (auditoría + visibilidad para la app del familiar). Para agregar un canal nuevo de alerta, tocar `shared/notifications.py` + el dispatch del supervisor.

### FHIR

`health_monitor/schemas/fhir.py::readout_to_fhir_bundle()` arma un Bundle HL7 FHIR R4 con `Observation` (LOINC: 85354-9 presión, 2339-0 glucemia, 59408-5 SpO2, 8310-5 temp, 29463-7 peso). **Sin librería FHIR**: solo dicts/JSON — cero acoplamiento. Para agregar métricas, extender este módulo.

### Deploy (`render.yaml`)

Python 3.11, `uvicorn health_monitor.main:app --host 0.0.0.0 --port $PORT`. Postgres se aprovisiona automáticamente y se inyecta `DATABASE_URL`. `JWT_SECRET` se autogenera. **`ENCRYPTION_KEY` se pega a mano** después del deploy (si la regenerás más tarde, los datos previos se vuelven ilegibles).

## Convenciones a respetar

- Frontend en `health_monitor/static/` se monta como `StaticFiles` en `/` desde `main.py`.
- Memoria del paciente truncada a ~1800 chars antes de inyectarse al prompt (`memoria.py`).
- Tests aislados por fixture autouse en `tests/conftest.py` (no se ensucia estado entre tests).
- Personalización del Contenedor (voz, trato, nombre del acompañante, temas) vive en el `Paciente` y se aplica en `companion._build_instructions`.
- Comentarios y docstrings en español — mantener el estilo.
