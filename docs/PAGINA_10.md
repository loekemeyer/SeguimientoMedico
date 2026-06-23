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
- [ ] **Contactos de emergencia completos**: varios, con orden de escalamiento y
  "recibe alertas" sí/no; agregar / editar / borrar desde el detalle. *(núcleo de los avisos)*
- [ ] **Historial de avisos enviados** (`GET /pacientes/{id}/notificaciones`): a quién,
  por qué canal, cuándo, si se envió.
- [ ] **Sugerencias del agente** (`GET /pacientes/{id}/sugerencias`): panel de
  recomendaciones proactivas (caídas, ánimo, adherencia, derivación).
- [ ] **Programación completa**: días de llamada, pausar/reanudar, zona horaria.
- [ ] **Métricas clínicas en el historial**: presión, glucemia, temperatura, dolor,
  peso, caída, riesgo emocional (hoy solo se ve el relato).
- [ ] **Borrar/editar** ítems de rutina y contactos (faltan endpoints DELETE testeados).
- [ ] **Estado del consentimiento** y apoderado, más claro.
- [ ] (Opc.) Exportar FHIR / ver auditoría para la prepaga.

## Notas
- El front no se puede testear con navegador en este entorno: se valida sintaxis
  (`node --check app.js`, llaves CSS balanceadas) y se mantiene el comportamiento;
  lo visual queda para el vistazo del usuario.
