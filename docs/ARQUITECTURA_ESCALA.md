# Arquitectura para escalar a 1.000–10.000 clientes

> Documento estratégico. Define **cómo guardar la información** y **qué
> instrumentar hoy** para no tener que migrar datos a las apuradas mañana,
> y diseña el **módulo de inteligencia de negocio (BI) del dueño**.

Cada "cliente" es un familiar/cuidador (un `Usuario`) que paga una suscripción
y administra una o más personas a cuidar (`Paciente`). A 10.000 clientes con ~1,3
pacientes promedio hablamos de ~13.000 pacientes, una llamada/charla diaria por
paciente y un historial que crece para siempre. El cuello de botella no es la
cantidad de filas vivas, sino **el historial que se acumula** y **el costo por
cliente** que hay que poder medir.

---

## 1. Estado actual (junio 2026)

- **Base**: SQLite por defecto; Postgres en producción vía `render.yaml`.
- **Sin migraciones**: el esquema se crea con `Base.metadata.create_all` al
  arrancar. Funciona para empezar, pero **no permite evolucionar el esquema**
  sin perder datos o hacerlo a mano.
- **PII cifrada** con AES-256-GCM (`FieldCipher`) y una sola `ENCRYPTION_KEY`
  global. Índice de teléfono por HMAC.
- **Historial** (`Evolucion`, transcripciones) en la misma base que los datos
  vivos. Crece sin techo.
- **Scheduler** en proceso, recorre pacientes para disparar llamadas.

Nada de esto está "mal" para arrancar y probar. Lo que sigue es el camino para
que aguante 1k–10k sin reescribir.

---

## 2. Principios

1. **Separar lo VIVO de lo HISTÓRICO.** Los datos que se leen todo el tiempo
   (usuarios, pacientes, rutina, configuración) son pocos y chicos. El historial
   (evoluciones, transcripciones, eventos) es grande y casi nunca se relee.
2. **Instrumentar antes de necesitarlo.** Registrar uso y costo desde hoy, aunque
   el panel BI venga después: los datos no se pueden recuperar a posteriori.
3. **Migraciones versionadas desde ya.** Es 10× más barato adoptar Alembic con
   13 tablas que con 130.
4. **Multitenancy por fila, no por base.** Un `usuario_id` en todo lo que sea de
   un cliente, e índices que siempre filtren por él. Nada de una base por cliente.
5. **El costo por cliente es un dato de primera clase**, no un cálculo de Excel a
   fin de mes.

---

## 3. Base de datos

### 3.1 Migraciones — adoptar Alembic YA
- Inicializar Alembic tomando el esquema actual como revisión base.
- Reemplazar el `create_all` de arranque por `alembic upgrade head` en el deploy.
- Regla: **ningún cambio de modelo sin su migración**.

### 3.2 Postgres real (no el free tier para 1k+)
- El free de Render duerme y tiene límites de conexión. Para producción seria:
  un plan con conexiones estables + **PgBouncer** (pool) adelante. FastAPI con
  pool de SQLAlchemy `pool_size`/`max_overflow` afinado al límite del plan.
- `pool_pre_ping=True` para no morir con conexiones zombi.

### 3.3 Índices que faltan (consultas calientes)
- `Paciente(usuario_id)` — listar pacientes de un cliente.
- `Paciente(codigo_acceso)` — login del paciente (ya es unique).
- `Evolucion(paciente_id, fecha DESC)` — historial y "estado de hoy".
- `EventoUso(usuario_id, ts)` y `EventoUso(paciente_id, ts)` — BI.
- Índice del scheduler: pacientes con llamada activa por hora/zona (ver 3.5).

### 3.4 Archivado del historial (lo importante para escala)
El historial crece linealmente con clientes × días. Estrategia **hot/cold**:

- **Hot (Postgres)**: últimos ~90 días de evoluciones + métricas. Es lo que la
  app lee (estado de hoy, tendencias, últimos seguimientos).
- **Cold (object storage, ej. S3/R2)**: evoluciones y **transcripciones de
  llamadas/charlas** más viejas que 90 días, en archivos comprimidos
  (JSONL/Parquet) particionados por `año/mes/usuario_id`. Un job nocturno mueve
  lo viejo de hot→cold y lo borra de Postgres.
- **Particionado por fecha** de la tabla `Evolucion` en Postgres (partición
  mensual) para que el archivado sea "drop partition", instantáneo y barato.
- Las **transcripciones** (texto largo de cada charla) **no van en la fila** de
  Postgres: van directo a object storage desde el inicio, con sólo un puntero
  (`transcript_uri`) y un resumen corto en la base. Esto solo ya baja el tamaño
  de la base un orden de magnitud.

### 3.5 Scheduler a escala
- Recorrer todos los pacientes en memoria no escala. Query indexada: "pacientes
  con `llamada_activa` cuya `llamada_hora` (en su zona) cae en esta ventana".
- A miles de llamadas, mover el disparo a una **cola de trabajos** (ej. tabla
  `tarea_llamada` o Redis/RQ/Celery) con workers, para no bloquear el web ni
  perder llamadas si un proceso se reinicia. Idempotencia con
  `ultima_llamada_programada` (ya existe).

---

## 4. Cifrado a escala (envelope encryption)

Hoy hay **una** `ENCRYPTION_KEY` global. Problema a escala: rotarla obliga a
recifrar todo, y un leak compromete a todos.

**Envelope encryption con KMS:**
- Una **DEK** (data encryption key) por cliente (o por paciente), guardada
  cifrada con una **KEK** maestra en un KMS (AWS KMS / GCP KMS / Vault).
- Cada PII se cifra con la DEK de su dueño. Rotar la KEK no toca los datos;
  rotar una DEK afecta sólo a un cliente.
- Migración incremental: `FieldCipher` ya abstrae el cifrado; se le agrega un
  `key_id` por fila y un resolvedor de claves. Compatible hacia atrás
  (las filas viejas usan la clave global como `key_id = "legacy"`).

---

## 5. Instrumentación que conviene meter HOY

Esto es lo que **no se puede recuperar después**. Una tabla append-only de
eventos de uso, barata de escribir y la base del módulo BI:

### Tabla `EventoUso` (append-only)
| campo | qué |
|---|---|
| `id` | PK |
| `usuario_id` | de qué cliente (índice) |
| `paciente_id` | opcional, de qué persona |
| `ts` | cuándo (índice) |
| `tipo` | `llamada`, `whatsapp`, `chat_msg`, `login_paciente`, `alerta_familia`, `info_cargada`, … |
| `modulo` | `acompanado`, `telefono`, `admin`, `billing` |
| `unidades` | cantidad (minutos de llamada, tokens, mensajes) |
| `costo_estimado` | $ estimado del evento (ver §6) |
| `meta` | JSON libre (sid de Twilio, modelo OpenAI, etc.) |

Reglas:
- **Append-only**, nunca se updatea. Se archiva igual que el historial (§3.4).
- Se escribe en cada acción facturable: al crear una llamada Twilio, al
  responder un chat con OpenAI, al mandar un WhatsApp, etc.
- Barata: un insert por evento, sin joins en el camino caliente.

Con esta única tabla quedan habilitados: costo por cliente, ingreso vs costo,
qué módulos usa cada cliente, retención y el asesor agéntico. **Si se mete una
sola cosa hoy, que sea esta tabla.**

---

## 6. Módulo BI del dueño (rentabilidad)

Panel privado (solo para el dueño) que responde: *¿cuánto me cuesta y cuánto me
deja cada cliente, y cómo mejoro la rentabilidad?*

### 6.1 Costo por cliente
Sumar `EventoUso.costo_estimado` por `usuario_id` en el período. Fuentes de costo:
- **Llamadas de voz (Twilio)**: minutos × tarifa + costo de la Realtime API.
- **WhatsApp**: por conversación/plantilla.
- **Chat (OpenAI)**: tokens × precio del modelo (`gpt-4o-mini` es barato; medirlo
  igual). Registrar `usage` que devuelve la API en `EventoUso.meta`.
- **Infra prorrateada**: costo fijo mensual / clientes activos.

### 6.2 Ingreso por cliente
- Del plan suscripto: App $10.000 / Teléfono $20.000. Estado real de pago
  (ver §7). Ingreso reconocido sólo desde que el pago está confirmado.

### 6.3 Rentabilidad
- `margen = ingreso − costo` por cliente y agregado.
- Tablero: clientes ordenados por margen, alertas de **clientes que dan
  pérdida** (ej. plan App que usa muchísimo chat, o plan Teléfono con muchas
  llamadas largas).
- **Qué módulos usa cada cliente**: de `EventoUso.modulo` → mix de uso por
  cliente (cuánto Acompañado vs Teléfono vs nada).

### 6.4 Asesor agéntico de rentabilidad
Un endpoint admin que arma un prompt con los agregados (margen por cliente, mix
de uso, clientes en pérdida, tendencia) y le pide a un LLM recomendaciones
concretas: *"estos 12 clientes del plan App consumen como plan Teléfono →
sugerir upgrade"*, *"el costo de chat subió 30% → revisar `max_tokens`"*,
*"clientes inactivos 14 días → riesgo de baja, contactar"*. El LLM **no toca la
base**: sólo lee agregados y devuelve texto accionable. Reutiliza el patrón del
`improver` que ya existe en `health_monitor/agents/`.

### 6.5 Privacidad
El panel del dueño trabaja con **agregados y métricas de uso**, nunca con el
contenido de las charlas ni PII de los pacientes. El asesor recibe números, no
transcripciones.

---

## 7. Pagos: de "link de MercadoPago" a suscripción real

Hoy el pago es un link de MercadoPago y el alta efectiva es manual/optimista.
Para facturar a escala y reconocer ingresos de verdad:
- **Webhook de MercadoPago** que reciba el evento de pago aprobado y marque
  `Usuario.plan = activo` + `suscripcion_vence`. Idempotente (un pago = un cambio).
- Estado de suscripción como fuente de verdad para el gating (ya existe el gating;
  falta cerrar el lazo del cobro automático).
- **Devolución de 5 días**: registrar `fecha_inicio_pago`; si pide baja dentro de
  los 5 días, reembolso. Guardar el evento para no rediscutirlo.
- Reintentos/dunning para tarjetas que fallan.

---

## 8. Hoja de ruta sugerida (orden de menor a mayor esfuerzo / mayor urgencia)

1. **`EventoUso` + registro en cada acción facturable.** (instrumentación: ya)
2. **Alembic** con revisión base del esquema actual.
3. **Webhook de MercadoPago** + estado de pago real.
4. **Transcripciones a object storage** (puntero en la base).
5. **Índices** del §3.3.
6. **Panel BI** (costo/ingreso/margen/mix) leyendo `EventoUso`.
7. **Asesor agéntico** de rentabilidad.
8. **Archivado hot/cold + particionado** del historial.
9. **Postgres con pool/PgBouncer**; scheduler a cola de trabajos.
10. **Envelope encryption con KMS** (cuando el volumen de PII lo justifique).

> Los primeros 3 ítems son los que, si no se hacen ahora, **cuestan datos
> perdidos o deuda cara** después. El resto se puede ir haciendo a medida que
> crece la base de clientes.
