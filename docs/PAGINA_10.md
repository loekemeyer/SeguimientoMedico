# Página 10/10 — roadmap del front (admin / familiar)

Objetivo: que el administrador cargue y vea **todo** lo necesario para que funcione
perfecto (sobre todo los **avisos**), y que la página sea **moderna y legible para 40+**.

## 🎨 Visual / accesibilidad (40+)
- ✅ Pase de accesibilidad: escala 17px, tipografía y controles más grandes, badges
  de alerta más visibles, foco/contraste — `styles.css`.
- [ ] Estados vacíos más guiados (qué cargar primero) y microayudas.
- [ ] Indicadores de alerta más prominentes en la tarjeta de cada persona (semáforo
  del último seguimiento).
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
- [ ] **Métricas clínicas en el historial**: presión, glucemia, temperatura, dolor,
  peso, caída, riesgo emocional (hoy solo se ve el relato).
- [ ] **Borrar/editar** ítems de rutina y contactos (faltan endpoints DELETE testeados).
- [ ] **Estado del consentimiento** y apoderado, más claro.
- [ ] (Opc.) Exportar FHIR / ver auditoría para la prepaga.

## Notas
- El front no se puede testear con navegador en este entorno: se valida sintaxis
  (`node --check app.js`, llaves CSS balanceadas) y se mantiene el comportamiento;
  lo visual queda para el vistazo del usuario.
