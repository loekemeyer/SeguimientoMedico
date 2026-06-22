# SeguimientoMedico — Agentic Healthcare Monitor

Backend en **Python** basado en arquitectura agéntica (Agentic AI), pensado para
correr en la nube. Software de salud proactivo para tercera edad y pacientes
crónicos: llama por voz al WhatsApp del paciente, mantiene un diálogo empático,
extrae métricas de salud, actualiza la HCE y dispara alertas jerárquicas.

| Componente | Carpeta | Descripción |
|------------|---------|-------------|
| **Acompañamiento y Monitoreo Crónico** | [`health_monitor/`](health_monitor) | Llamadas de voz proactivas vía WhatsApp para pacientes crónicos / tercera edad. Tres agentes (Contenedor, Clínico, Supervisor) + triaje jerárquico de alertas. |
| **Shared** | [`shared/`](shared) | Configuración, cifrado AES-256, notificaciones (WhatsApp / webhooks). |

## Decisiones de arquitectura

Este repo entrega una **base estructurada y ejecutable**, no un sistema con credenciales en
producción. La lógica de negocio determinística (triaje, cifrado, extracción de métricas,
mapeo FHIR, herramientas de la fábrica) está **implementada y cubierta por tests**. Las capas
de integración con servicios externos (Twilio Media Streams, Realtime API de OpenAI/Gemini,
LangChain/LangGraph) están implementadas como módulos con interfaces claras e **imports
perezosos**: el núcleo funciona y se testea aunque esas librerías o API keys no estén presentes.

```
┌─────────────┐   audio (mulaw/8000)   ┌──────────────┐   audio    ┌────────────────┐
│  WhatsApp   │ ───────────────────────│   FastAPI    │───────────▶│ Realtime API   │
│  (Twilio)   │◀────── WebSocket ──────│  Media Stream│◀───────────│ (OpenAI/Gemini)│
└─────────────┘                        └──────┬───────┘            └────────────────┘
                                              │ transcript
                       ┌──────────────────────┼───────────────────────┐
                       ▼                       ▼                       ▼
                ┌────────────┐         ┌──────────────┐        ┌──────────────┐
                │ Agente 1   │         │ Agente 2     │        │ Agente 3     │
                │ Contenedor │         │ Clínico      │        │ Supervisor   │
                │ (voz)      │         │ (JSON métr.) │        │ (triaje)     │
                └────────────┘         └──────┬───────┘        └──────┬───────┘
                                              ▼                       ▼
                                       PostgreSQL (HCE)        Alertas R/A/V
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # completar credenciales
docker compose up -d db       # PostgreSQL local (opcional)
pytest                        # corre la suite de lógica de negocio
```

### Demo sin servicios pagos

Para ver el flujo completo de una llamada (extracción → triaje → alertas →
guardado en la HCE) **sin Twilio, sin OpenAI y sin red**, corré:

```bash
python scripts/demo_local.py
```

Usa SQLite local y una clave de cifrado generada al vuelo. Simula tres llamadas
(Verde / Amarilla / Roja) y muestra el triaje, las alertas (en modo degradado se
loguean en vez de enviarse) y el bundle FHIR resultante.

### Correr el servicio

```bash
uvicorn health_monitor.main:app --reload --port 8001
```

### Pipeline de voz (latencia < 1s)

```
WhatsApp ──audio mulaw/8000──▶ Twilio ──WS (wss://)──▶ FastAPI (MediaStreamBridge)
                                                            │  audio-to-audio nativo
                                                            ▼
                                              Realtime API (OpenAI / Gemini Live)
```

No se transcribe a texto para "pensar": el modelo de voz procesa audio y devuelve
audio por el mismo canal. La transcripción se acumula en paralelo solo para
alimentar al Agente Clínico y al chequeo crítico en vivo del Supervisor.

## Cumplimiento legal

- **Ley 25.326 (Datos Sensibles, Argentina):** cifrado **AES-256-GCM** en reposo para campos
  PII/clínicos (`shared/security.py`) y consentimiento informado obligatorio antes de operar.
- **Interoperabilidad HL7 / FHIR:** las métricas se exportan como recursos FHIR `Observation`
  (`health_monitor/schemas/fhir.py`) para integrarse como "enchufe" nativo con prepagas/obras
  sociales.
- **Human-in-the-loop:** la IA nunca decide la acción médica; provee la alerta al humano.
