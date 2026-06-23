# Camino a 100% — Psicólogo + Terapeuta + Clínico básico

> **Objetivo (norte):** que la IA funcione como un **psicólogo + terapeuta + clínico
> básico** confiable, que cumpla los requerimientos de **seguimiento médico y
> emocional** de cada paciente.

Este documento es el análisis "como CEO": mide honestamente dónde estamos contra
ese objetivo, qué falta, y en qué orden conviene construirlo. Está aterrizado en
el código real (con referencias `archivo:línea`), no en intenciones.

---

## 1. El objetivo, desglosado en requisitos

Para llegar a 100% hay que cumplir, de verdad, tres roles:

### A. Clínico básico
- [ ] Capturar y graduar los signos y síntomas que importan (no solo medirlos).
- [ ] Triar con criterio (umbrales personalizados por patología, no genéricos).
- [ ] Detectar **cambios agudos** (tendencia), no solo valores aislados.
- [ ] Conocer el **contexto** (qué medicación toma, qué patologías tiene).
- [ ] **Validar** el dato crítico antes de alarmar (evitar falsos positivos).

### B. Terapeuta / psicólogo
- [ ] Escucha activa y contención reales (no solo "tono cálido").
- [ ] **Medir** el ánimo con una escala validada y seguir su evolución en el tiempo.
- [ ] Detectar **crisis emocional y riesgo suicida** — y tener un protocolo claro.
- [ ] Continuidad emocional entre llamadas (memoria con sentido, no genérica).
- [ ] Derivación a un profesional cuando corresponde, con criterios.

### C. Confiable y operable (para que A y B existan de verdad)
- [ ] Las llamadas se disparan **solas** (seguimiento automático real).
- [ ] El reporte se guarda **siempre** (médico + emocional) para la familia.
- [ ] Trazabilidad/auditoría, reintentos e idempotencia.
- [ ] Privacidad y consentimiento sólidos (ya bastante avanzado).

---

## 2. Dónde estamos hoy (honesto)

| Pilar | Completitud | Lectura |
|---|---|---|
| **Clínico básico** | ~55% | Buen monitor de signos vitales con triaje de 3 niveles, pero le faltan datos clave y contexto. Es "monitor", todavía no "clínico". |
| **Terapeuta / psicólogo** | ~40% | Tono empático y captura del relato emocional reales, pero **ciego a las crisis**. Sirve para acompañar; colapsa ante una urgencia emocional. |
| **Confiable / operable** | ~50% | Arquitectura limpia, cifrado y consentimiento OK. Pero el seguimiento automático **no se dispara solo** y faltan reintentos/auditoría. |

### Lo que YA funciona bien (no tocar)
- **Arquitectura de 3 agentes** (Contenedor / Clínico / Supervisor) con la decisión
  médica siempre en manos humanas (la IA solo recolecta y alerta) — `orchestrator.py`.
- **Triaje determinístico** de 3 niveles con umbrales personalizables por paciente
  — `triage/rules.py`.
- **Cifrado AES-256-GCM** de PII y consentimiento (Ley 25.326) — `shared/security.py`, `services.py:33`.
- **Captura del relato emocional** para la familia — `clinical.py:relato_empatico`, `prompts.py:RELATO_PROMPT`.
- **FHIR R4** de los signos vitales (interoperable con prepagas) — `fhir.py`.
- **[NUEVO] El reporte se guarda aunque el paciente cuelgue primero** — corregido un
  bug que dejaba la llamada colgada y nunca persistía la evolución (`media_stream.py`).

---

## 3. Los gaps que más duelen (priorizados por riesgo × impacto)

### 🔴 Seguridad (lo que NO puede fallar)
1. **No detecta riesgo suicida ni crisis emocional.** El 15-20% de los adultos
   mayores con depresión tiene ideación suicida; hoy eso pasa invisible o llega
   como "amarillo" igual que una presión apenas alta. *(pilar B — crítico)*
2. **No valida el dato crítico.** Si el modelo entiende "presión 240/150", alarma
   sin reconfirmar. Falsos positivos = la familia deja de confiar. *(pilar A)*

### 🟠 Lo que convierte "acompañante" en "profesional"
3. **Sin escala validada de ánimo (PHQ-9 / GDS).** No hay línea de base ni forma de
   ver si el paciente mejora o empeora. *(pilar B)*
4. **Triaje emocional acoplado al médico.** Un paciente triste hace meses sigue en
   "verde" si la presión está bien. Lo emocional no escala por sí mismo. *(pilar B)*
5. **Clínico sin contexto:** no sabe qué medicación toma el paciente, no extrae
   **temperatura** (¡el campo existe pero el extractor nunca lo llena!), no mide
   **dolor**, **peso/tendencia** ni **caídas** — todo crítico en adultos mayores. *(pilar A)*

### 🟡 Lo que lo hace un producto real (y vendible)
6. **El seguimiento automático no existe:** el scheduler lista a quién llamar pero
   **no dispara la llamada** — hoy hay que apretar "Llamar" a mano. *(pilar C)*
7. **Sin reintentos ni idempotencia:** si falla OpenAI/Twilio/DB, la llamada se
   pierde; si se reintenta, se duplican alertas. *(pilar C)*
8. **Sin auditoría/trazabilidad** (trace IDs, log de acciones) — requisito de
   cualquier prepaga. *(pilar C)*

---

## 4. El plan a 100% (por fases)

El orden está pensado por **riesgo primero, después profundidad, después escala**.

### Fase 0 — Higiene (✅ hecho)
- Fix: el reporte se persiste siempre al terminar la llamada.

### Fase 1 — Seguridad médica y emocional (✅ hecho)
- **Detección de riesgo suicida / crisis emocional**: nueva dimensión
  `riesgo_emocional` (ninguno / angustia_aguda / riesgo_suicida) en el readout,
  detectada por el LLM y por heurística conservadora — `schemas/clinical.py`, `clinical.py`.
- **Triaje**: riesgo suicida → ROJA; angustia aguda → AMARILLA — `triage/rules.py`.
- **Escalada y contención**: aviso a la familia con tono de contención y línea de
  ayuda (no médico) y, en vivo, el agente se queda conteniendo y NUNCA corta —
  `supervisor.py`, `orchestrator.py`, `media_stream.py`.
- **Límites éticos** cristalinos y **re-validación del dato crítico** antes de
  alarmar, en el prompt del acompañante — `prompts.py`.
- **Guion**: charla que apunta a 5-10 min para que se sienta acompañado, sin
  obligar a hablar — `prompts.py`.

### Fase 2 — Técnica terapéutica real (🚧 en curso)
- ✅ **Memoria emocional con tendencia**: el acompañante recibe la trayectoria del
  ánimo de las últimas llamadas (mejora / baja / se mantiene) para retomar con
  sensibilidad — `agents/mood.py`, `services.py:_load_historial_resumen`.
- [ ] **PHQ-9 / GDS-15** conversacional, con score histórico y triaje emocional propio.
- [ ] Derivación automática a profesional con criterios (no solo "considerá consulta").

---

## PENDIENTES DE DECISIÓN (del usuario)

Cosas que el loop autónomo dejó anotadas porque necesitan tu criterio (no las
decide solo). Mientras tanto sigue con lo que no depende de esto.

1. **Cadencia de la escala validada (PHQ-9 / GDS-15).** Administrar 9 preguntas
   tipo cuestionario en CADA llamada choca con tu pedido de charla natural de
   5-10 min "sin obligar a hablar". Opciones: (a) periódica (p. ej. cada 14 días),
   (b) solo cuando hay señales (ánimo en baja varias llamadas), (c) nunca rígida:
   inferir de la conversación. *Default propuesto si no decidís: (b) gatillada por
   señales, tejida con naturalidad.*
2. **Derivación a profesional:** ¿a quién deriva y cómo? (¿la prepaga tiene red de
   salud mental? ¿el familiar coordina?) Sin esto, la "derivación automática"
   queda como un aviso al familiar.
3. **Línea de ayuda en crisis (135):** confirmar que es la que querés usar
   (hoy: Centro de Asistencia al Suicida, AR).
4. **¿Cuánto se le oculta al paciente que es un asistente automático?** Ya hice que
   el acompañante hable con total naturalidad y NO se presente como bot/IA, y que si
   le preguntan responda con calidez "soy parte del equipo que te acompaña". Falta tu
   decisión sobre el límite: si pregunta de forma directa e insistente "¿sos una
   máquina?", ¿igual lo evade? Mi recomendación profesional: que el **consentimiento
   del apoderado** deje claro que es un asistente automático (lo cubre legalmente), y
   que con el paciente se mantenga la experiencia natural sin mentir activamente si
   confronta. Es la postura más segura ética y legalmente con personas vulnerables.
5. **Parametrización (ver `PARAMETRIZACION.md`):** priorizar qué configurables nuevos
   construir primero (sugiero: personalidad/voz por paciente, duración de la charla,
   y umbrales clínicos por plantilla de patología).

### Fase 3 — Clínico básico completo (🚧 en curso)
- ✅ **Temperatura**: se extrae (heurística + LLM) y se tría (febrícula → AMARILLA,
  fiebre alta/hipotermia → ROJA), con umbrales personalizables — `clinical.py`,
  `triage/rules.py`, `supervisor.py`.
- [ ] **Dolor (0-10)**, **peso + tendencia**, **caídas**.
- [ ] **Contexto de medicación** y **reglas por patología** (un diabético no se tría
  como un prediabético).
- [ ] Detección de **cambios agudos** comparando con el histórico.

### Fase 4 — Operación confiable y vendible
- **Scheduler que dispara las llamadas solo** + manejo de no-respuesta (reintento).
- **Reintentos + idempotencia** en alertas y persistencia.
- **Auditoría** (trace IDs + tabla de audit log) y **endpoint FHIR** (hoy es código muerto).

---

## 5. La capa agéntica que mide el avance (el "Director" / CEO)

La pregunta original era "un agente que analice todo como CEO". La respuesta es una
capa de análisis en **dos niveles**, que usa estos mismos requisitos como vara:

- **Director de cuidado (por población):** mira a TODOS los pacientes y responde
  "¿quién necesita atención esta semana?" — quiénes empeoran (médico o emocional),
  adherencia, alertas, días sin contacto. Extiende el agente `improver` que ya existe
  (hoy mira un paciente; esto sube a toda la población).
- **Lectura de negocio (CEO):** sobre los mismos datos, "¿cómo va la operación y qué
  decisión tomar?" — costo por canal (llamada vs WhatsApp), concentración de riesgo,
  cobertura del seguimiento, dónde poner el foco.

Esta capa **no reemplaza** el trabajo de las Fases 1-3: lo **mide** y prioriza. Es lo
que te da, en una pantalla, "estamos al X% del objetivo y esto es lo próximo".

---

## 6. Riesgos a tener en el radar

- **Clínico/legal:** un sistema que dice ser "terapeuta/clínico" y falla en detectar
  una crisis es un riesgo serio. Por eso la Fase 1 va primero, con límites éticos
  explícitos y siempre con humano en el loop (la IA nunca decide, alerta).
- **Calidad de la IA de voz:** depende de OpenAI; hay que medir latencia y tener un
  guion robusto. La validación con llamadas reales es insustituible.
- **Costo:** la llamada telefónica en vivo es lo más caro. El modo WhatsApp por voz
  (ya construido) y una futura app de voz bajan el costo del seguimiento masivo.

---

*Este documento es vivo: se actualiza a medida que cerramos fases.*
