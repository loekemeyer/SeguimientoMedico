# Página 10/10 — roadmap del front (admin / familiar)

Objetivo: que el administrador cargue y vea **todo** lo necesario para que funcione
perfecto (sobre todo los **avisos**), y que la página sea **moderna y legible para 40+**.

## 🎨 Visual / accesibilidad (40+)
- ✅ Pase de accesibilidad: escala 17px, tipografía y controles más grandes, badges
  de alerta más visibles, foco/contraste — `styles.css`.
- [ ] Estados vacíos más guiados (qué cargar primero) y microayudas.
- ✅ Semáforo del último seguimiento (VERDE/AMARILLA/ROJA) en la tarjeta de cada
  persona — se ve de un vistazo quién necesita atención (`PacienteOut.ultimo_nivel`).
- [ ] Repaso final de contraste y tamaños en mobile.

## 🔔 Funcional — lo que el admin tiene que poder cargar/ver
- ✅ **Contactos de emergencia completos**: agregar varios desde el detalle con orden
  de escalamiento (1º/2º/3º) y "recibe avisos" sí/no, y quitarlos (endpoint DELETE con
  autorización + auditoría) — `api/patients.py`, `static/*`. *(núcleo de los avisos)*
  (Editar = quitar y volver a agregar por ahora.)
- ✅ **Historial de avisos enviados** (`/notificaciones`): tarjeta "Avisos enviados a la
  familia" con canal, destino, nivel, fecha, si se envió y el texto.
- ✅ **Sugerencias del agente** (`/sugerencias`): tarjeta "Sugerencias para el cuidado"
  (se muestra solo si hay), con prioridad en color.
- ✅ **Programación completa**: en el form del paciente, días de llamada (Lun-Dom),
  pausar/reanudar (llamadas activas) y zona horaria; se guardan y se ven en el detalle.
- ✅ **Métricas clínicas en el historial**: cada seguimiento muestra chips con presión,
  glucemia, saturación, temperatura, FC, dolor, peso, adherencia, caída y riesgo
  emocional (los que aparezcan), además del relato — `static/app.js` (metricasChips).
- ✅ **Borrar** ítems de rutina y contactos desde el detalle (endpoints DELETE con
  autorización + auditoría, testeados). (Editar = quitar y volver a agregar por ahora.)
- [ ] **Estado del consentimiento** y apoderado, más claro.
- [ ] (Opc.) Exportar FHIR / ver auditoría para la prepaga.

## Principio de datos clínicos
Las métricas son **solo lo que la persona se automide en casa y nos informa en la
llamada**: presión (tensiómetro), glucemia (glucómetro), saturación/pulso (oxímetro),
temperatura, peso (balanza), más lo auto-reportado (dolor, caídas, ánimo). **No** hay
datos cargados por profesionales ni integraciones con devices externos. Por eso la app
permite agendar esas automediciones en la rutina y aclara que los valores son informados
por la persona (no son mediciones clínicas verificadas).

## Notas
- El front no se puede testear con navegador en este entorno: se valida sintaxis
  (`node --check app.js`, llaves CSS balanceadas) y se mantiene el comportamiento;
  lo visual queda para el vistazo del usuario.
