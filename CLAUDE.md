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

## REGLA: auditar en Supabase cada problema del repo y su solucion

**Vale para TODOS los repos** (igual que la regla de Planify: copiar este bloque al `CLAUDE.md`
de cualquier repo nuevo). Objetivo: que cada error que tuvo un repositorio quede con su causa,
su correccion y el/los commits donde se arreglo, para no volver a pisar el mismo pozo.

**Donde:** proyecto Supabase `hrxfctzncixxqmpfhskv`, schema `github_repo_problemas`.
Se escribe con el MCP de Supabase (`execute_sql`), no con la anon key.

### Que se audita y que NO

Regla corta: **si ya estaba pusheado y andaba mal, se audita.** Si es trabajo nuevo, no.

| Se registra | NO se registra |
|---|---|
| Bug en codigo ya pusheado que llego al usuario | Feature nueva o pedido de cambio |
| Dato corrupto o mal migrado en la base | Refactor pedido por el usuario |
| Config o credencial rota o filtrada | Bug que introducis y arreglas antes de pushear |
| Performance degradada, query que no escala | Duda o consulta que se responde en el momento |
| Tabla derivada desincronizada de su madre | Ajuste de estilo o texto |

### Cuando

1. **Al detectar el problema** (antes de tocar nada): `registrar_problema` devuelve el id.
2. **Al pushear el fix**: `cerrar_problema` con el sha del commit.
3. **Si el fix necesita mas commits**: `agregar_commit` por cada uno. Un problema puede tener N
   commits; NO abrir un problema nuevo por el segundo pase del mismo fix.
4. Una sesion de Claude puede abarcar **varios** problemas: `sesion_id` no es unico.

### SQL

```sql
-- 1) al detectar
select github_repo_problemas.registrar_problema(
  p_repo          => 'owner/repo',            -- en minuscula
  p_titulo        => '<sintoma en <=120 chars>',
  p_descripcion   => '<que se rompio y como se manifesto>',
  p_categoria     => 'bug',                   -- bug|datos|seguridad|performance|config|ux|deuda_tecnica|documentacion
  p_severidad     => 'alto',                  -- critico|alto|medio|bajo
  p_modulo        => 'Carpeta/Modulo',
  p_archivos      => array['ruta/relativa.html'],
  p_sesion_id     => '<id de la sesion de Claude>',
  p_detectado_por => '<usuario> (claude-remote)',
  p_detectado_en  => now()                    -- fecha REAL si es carga historica
);

-- 2) al pushear el fix
select github_repo_problemas.cerrar_problema(
  p_id            => <id>,
  p_correccion    => '<que se cambio>',
  p_commit_sha    => '<sha corto>',
  p_branch        => '<branch>',
  p_commit_url    => 'https://github.com/owner/repo/commit/<sha>',
  p_causa_raiz    => '<por que paso, no que paso>',
  p_corregido_por => '<usuario> (claude-remote)',
  p_mensaje       => '<subject del commit>'
);

-- 3) commits extra del mismo problema
select github_repo_problemas.agregar_commit(<id>, '<sha>', '<branch>', '<url>', '<mensaje>', '<autor>');

-- lectura
select * from github_repo_problemas.v_problemas order by detectado_en desc;
```

**Avisar en el chat el titulo del problema** al registrarlo y al cerrarlo, no el numero de id
(mismo criterio que Planify).

**Si el problema se detecta pero NO se arregla, queda en `estado='abierto'`.** Ese es el punto:
que quede anotado. Estados: `abierto` | `en_curso` | `corregido` | `no_corregible` | `descartado`.
Para pasar a `corregido` la base exige `correccion` y `corregido_en` cargados (constraint).

**La auditoria no se borra.** El rol `anon` tiene SELECT/INSERT/UPDATE pero NO DELETE ni
TRUNCATE en las tres tablas. Si una fila esta mal, se corrige o se pasa a `descartado`.

## REGLA: claves de Supabase - migrar a las nuevas, NO apagar las legacy todavia

Estado al 2026-09-11. Supabase cambio el sistema de claves. Conviven dos juegos y **los dos
funcionan a la vez**, asi que se migra cliente por cliente sin downtime.

| Sistema | Claves | Se rota de a una |
|---|---|---|
| Nuevo | `sb_publishable_...` (frontend) + `sb_secret_...` (backend) | si |
| Legacy (JWT) | `anon` + `service_role` | NO: las dos derivan del JWT secret del proyecto |

Doc: `supabase.com/docs/guides/getting-started/migrating-to-new-api-keys`. Textual: *"The
legacy anon and service_role keys are based on your project's JWT secret, which makes them
hard to rotate without downtime."* **No existe boton "Roll" para las legacy.**

### 1. Lo filtrado vive en el HISTORIAL de git, y el historial no se arregla

Una `service_role` legacy quedo expuesta en el historial de un repo publico (ver `LOCKS.txt`
de `GestionProductivaEntero`, entrada 2026-09-04). El arbol de trabajo ya esta limpio, pero
eso no alcanza: lo que estuvo en un repo publico pudo clonarlo cualquiera y reescribir el
historial NO lo des-filtra. **El unico arreglo real es invalidar la clave.**

Precision importante: lo que se filtro es la **`service_role` key** (un JWT firmado con el
secret), NO el JWT secret. De un HS256 no se deriva la clave, asi que **apagar las legacy
alcanza** para matar lo filtrado. Rotar el JWT secret es un paso extra, no el obligatorio.

### 2. Como se invalida (y por que todavia no)

Dashboard -> Settings -> API Keys -> pestana **"Legacy anon, service_role API keys"** ->
boton **`Disable JWT-based API keys`**. Apaga `anon` y `service_role` de una sola vez. Es
reversible. Es lo que la doc pide para este caso: *"Make sure you also switch to publishable
and secret API keys and disable the anon and service_role keys."*

**NO apretarlo todavia:** apaga TAMBIEN la `anon`, que es la que usa el frontend. Hoy eso
tira abajo la app entera.

### 3. ⚠ EL STORAGE SI ACEPTA LAS CLAVES NUEVAS — lo que falta es el header `apikey`

**Este bloque cambio DOS veces el mismo dia, y la segunda es la buena.** Vale la pena leer las
dos, porque la equivocacion del medio es facil de repetir:

- **11/09** decia *"el Storage rechaza las claves nuevas al ESCRIBIR"* y que por eso no se podian
  apagar las legacy.
- **13/09 (v16.56)** dije que esa excepcion ya no existia, porque mande un upload con la
  `sb_publishable_` y dio 200. **Estaba mal la conclusion, no la medicion**: en esa prueba mande
  la clave en `apikey` **y** en `Authorization`, y no me di cuenta de que el que hacia el trabajo
  era el primero.
- **13/09 (v16.62), la buena:** el formato de la clave nunca fue el problema. **Lo que faltaba es
  el header `apikey`.**

Medicion contra el Storage real (bucket `inbox` de LK, objeto de prueba creado y borrado):

| Request | Resultado |
|---|---|
| `Bearer sb_secret_…` y nada mas | **403 `Invalid Compact JWS`** |
| `Bearer sb_secret_…` **+ `apikey: sb_secret_…`** | **200**, el objeto se sube |
| `Bearer sb_publishable_…` y nada mas | 403 `Invalid Compact JWS` |
| `Bearer sb_publishable_…` **+ `apikey: …`** | 403 **`new row violates row-level security policy`** ← paso auth; lo frena la RLS, que es lo correcto para una clave publica |

**Por que la legacy andaba sin `apikey`:** la legacy **es** un JWT, asi que el Storage la podia
parsear del Bearer. Con la clave nueva intenta lo mismo, no puede, y contesta `Invalid Compact
JWS`. Ese error significa *"no pude parsear el token"*, no *"no soporto el formato"*.

**Y por eso la app nunca estuvo rota:** `supabase-js` manda `apikey` siempre. Los que fallaban
eran los `curl` / `Invoke-RestMethod` escritos a mano, que mandan solo el Bearer — exactamente el
caso del workflow de Planify (runs 112 a 115 del 11/09). **Ya corregido**: `build-deploy.yml` y
`deploy-only.yml` de `loekemeyer/Planify` mandan las dos cabeceras desde el commit `75179d7`.

Repro, para volver a medirlo (ojo: **si da 200 crea el objeto**, hay que borrarlo con un `DELETE`
a la misma URL — `storage.objects` no se puede borrar por SQL, `storage.protect_delete()` lo
impide):

```sql
select net.http_post(
  url := 'https://<ref>.supabase.co/storage/v1/object/<bucket>/__prueba__.json',
  headers := jsonb_build_object('Authorization','Bearer <clave>','apikey','<clave>',
                                'Content-Type','application/json'),
  body := '{"p":1}'::jsonb);
```

**Inventario de lo que escribe en Storage, al 13/09** (todos con `supabase-js` salvo Planify, o
sea que ya mandan `apikey`): `recepcion.js` de Gestion (bucket `remitos`), `krikos-ingest` de LK
(`krikos-oc`), `script.js` de LK (`.remove()` de videos) y los workflows de Planify (corregidos).

⚠ **Y hay un pedazo de `recepcion.js` que quedo muerto**: `pendUploadFoto` tiene un tercer intento
que hace `signOut()` y sube con la clave pelada como Bearer. Estaba pensado para la anon legacy.
Hoy el primer intento anda, asi que no molesta, pero el comentario que dice que ese fallback
"sube igual" hay que leerlo con esta nota al lado.

### Orden obligatorio

1. Contar donde esta escrita la clave legacy en este repo:
   ```
   grep -rl 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' . --exclude-dir=.git | wc -l
   ```
   (Referencia: `GestionProductivaEntero` tenia 66 archivos y 0 con la clave nueva.)
2. Reemplazar esa cadena por la `sb_publishable_...` del proyecto Supabase de ESTE repo
   (cada proyecto tiene la suya; no mezclar).
3. Migrar todo backend que use `service_role` (Edge Functions, n8n, scripts) a `sb_secret_...`.
4. Inventariar lo que escribe en Storage (ver el punto 3) y confirmar que **cada uno manda el
   header `apikey`**, no solo el Bearer. Ya NO hay que dejar nada en legacy por eso: con
   `apikey` el Storage acepta tanto `sb_secret_` como `sb_publishable_` (medido el 13/09).
   Lo que usa `supabase-js` ya lo manda solo; lo escrito a mano (`curl`, `Invoke-RestMethod`)
   hay que mirarlo uno por uno.
5. Recien con 1-4 hechos en TODOS los repos que peguen contra ese proyecto:
   `Disable JWT-based API keys`. **Ya no esta bloqueado por el Storage** (punto 3). Lo que
   falta: que el dueno cambie el secret `SUPABASE_SERVICE_KEY` de Planify por una
   `sb_secret_` y mire ese primer build, y que ningun cliente siga mandando la anon legacy.
   El boton lo aprieta el dueno, no Claude: apaga la `anon` que usa el frontend.

### Paso opcional: rotar el JWT secret

Sirve si ademas se sospecha del secret en si. Va en **Settings -> JWT Keys**
(`/dashboard/project/_/settings/jwt`), NO en la pagina de API Keys:

1. `Migrate JWT secret` - importa el secret viejo y crea una clave asimetrica standby. Sin downtime.
2. `Rotate keys` - la standby firma los JWT nuevos. NO desloguea a nadie: los tokens no
   vencidos se siguen aceptando.
3. Revocar el secret legacy, que queda en *Previously used*.

Dos avisos de la doc antes del paso 2:
- *"Make sure your app does not directly rely on the legacy JWT secret. If it's verifying every
  JWT against the legacy JWT secret (using a library like jose, jsonwebtoken or similar),
  continuing with the rotation might break those components."*
- *"If you're using Edge Functions that have the Verify JWT setting, continuing with the
  rotation might break your app. You will need to turn off this setting."*

Cuando revocar: esperar el tiempo de expiracion del access token + 15 min (1 h 15 min si es de
1 h) para no desloguear a nadie; en un incidente activo, revocar de inmediato.

**Al tocar cualquier archivo con una clave de Supabase, dejarlo en el sistema nuevo. Nunca
escribir codigo nuevo con la clave legacy.**

## REGLA: toda copia de respaldo nace sin RLS

**Vale para TODOS los repos** (igual que las reglas de Planify y de auditoria: copiar este bloque
al `CLAUDE.md` de cualquier repo nuevo).

**⚠️ `CREATE TABLE AS` y `SELECT INTO` NO heredan Row Level Security de la tabla de origen.** La
copia queda con `relrowsecurity = false` aunque la madre este protegida, y los `GRANT` del schema
le siguen aplicando, asi que `anon` hereda SELECT/INSERT/UPDATE/DELETE. Postgres no emite ninguna
advertencia. **Prender RLS en el MISMO paso en que se crea la copia**, no despues:

```sql
create table <schema>.<copia> as select * from <schema>.<madre>;
alter table <schema>.<copia> enable row level security;  -- sin politicas = deny-all para anon
```

Sin politicas, RLS habilitada deja la tabla accesible solo para `service_role`, que es exactamente
lo que se quiere en un respaldo.

**Caso real (2026-09-14):** `planify.bkp_items_mayo_20260914`, respaldo de la liquidacion de sueldos
de mayo hecho —bien— antes de tocarla, quedo con 56 sueldos completos (legajo, nombre,
`sueldo_bolsillo`, banco, aportes) legibles y borrables por cualquiera con la clave publishable,
durante 24 horas. El respaldo estuvo bien; lo que falto fue el `alter`.

Para barrer copias abiertas en un proyecto:

```sql
select n.nspname, c.relname
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where c.relkind = 'r' and c.relrowsecurity = false
   and has_table_privilege('anon', c.oid, 'SELECT')
   and n.nspname not in ('pg_catalog','information_schema','pg_toast');
```
