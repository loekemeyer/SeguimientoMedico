# Parametrización para una app 10/10 (lo que configura el familiar)

> Propuesta de diseño: qué debería poder configurar el **familiar/cuidador a cargo**
> para que el acompañamiento sea de primera, sin volverse un panel técnico imposible.
> Mapeado al modelo actual: ✅ ya existe · 🔶 existe parcial · 🆕 falta construir.

## Filosofía (clave para que sea 10/10 con un cuidador NO técnico)

1. **Funciona sin configurar nada.** Defaults inteligentes: con cargar nombre,
   teléfono, consentimiento y un horario, ya acompaña bien. Todo lo demás es opcional.
2. **Configuración en pasos (wizard), no un formulario gigante.** Onboarding guiado;
   el resto vive en "Ajustes" con **modo simple / modo avanzado**.
3. **Plantillas por situación.** Elegís "Hipertensión", "Diabetes", "Post-ACV",
   "Deterioro cognitivo", "Bajón anímico / soledad" y se precargan rutina, umbrales y
   preguntas. El cuidador ajusta, no arma de cero.
4. **Lenguaje humano, no clínico.** "¿Cuándo querés que lo llamemos?" en vez de
   "cron de disparo". Cada opción explica *para qué sirve* en una línea.
5. **Previsualización.** "Escuchá cómo va a sonar" (voz + saludo) y "Mirá un reporte
   de ejemplo" antes de activar.

---

## Los grupos de configuración

### A. La persona (perfil) — ✅/🔶
- Cómo la llaman (mostrar como "Papá", "Abuela Rosa") ✅ `nombre_enc`
- Teléfono / WhatsApp ✅ · Zona horaria ✅ · Idioma/tonada (es-AR) 🔶 (hoy fijo)
- Consentimiento del apoderado (Ley 25.326) ✅ — bloqueante para operar
- Patologías ✅ `FichaClinica.patologias`

### B. Cuándo y cómo lo acompaña — ✅/🆕
- **Canal**: llamada de voz ✅ · WhatsApp por voz ✅ · app de voz 🆕 (futuro)
- Horario y días ✅ `llamada_hora`, `llamada_dias` · activar/pausar ✅
- **Duración objetivo de la charla** (ej. 5–10 min) 🆕 — hoy está en el guion, no es configurable
- **Reintento si no atiende** (cuántas veces, cada cuánto) 🆕
- **Nivel de insistencia** (1 pasivo · 2 recordar · 3 insistir amable) ✅ `nivel_insistencia`

### C. Qué controla (rutina + seguimiento) — ✅/🔶
- Ítems de rutina: medicamento, presión, glucemia, ejercicio, sueño, baño nocturno,
  pregunta libre ✅ `RutinaItem` (con horario/días)
- Por ítem, **cómo avisar**: mensaje / llamada / ninguno ✅ `aviso`
- **Qué signos medir y con qué umbrales** (presión, glucemia, temperatura, FC, SpO2…)
  🔶 `FichaClinica.limites` existe pero **no se expone en la UI** → exponerlo, idealmente
  vía plantilla por patología
- **Preguntas de seguimiento personalizadas** ✅ (tipo "pregunta")

### D. Personalidad y voz del acompañante (lo que lo hace sentir humano) — ✅ backend / 🔶 UI
*Lo que más mueve la aguja en "no parece un bot". Ya es configurable por paciente en el
modelo y la API (`PersonalidadAcompanante`); falta exponerlo en la pantalla.*
- **Voz** (8 voces) y **velocidad** ✅ API (antes `coral` / `speed 0.9` fijos en el código)
- **Trato**: de "vos" o de "usted" ✅ API → el guion lo respeta
- **Cómo se presenta** (nombre del acompañante, p. ej. "Sofía") ✅ API → saludo y guion
- **Temas que le gustan** (fútbol, los nietos, el jardín) y **temas a evitar** ✅ API → guion
- ✅ El modo **WhatsApp por voz** también respeta trato / temas / nombre del acompañante
- Falta: 🔶 mostrarlo en la UI (modo avanzado)
- **¿Se presenta como asistente o no?** — ver *PENDIENTES DE DECISIÓN* en `CAMINO_A_100.md` (aristas éticas/legales)

### E. Seguridad y alertas (a quién y cuándo avisar) — ✅/🔶/🆕
- **Contactos** con orden de escalamiento y quién recibe alertas ✅ `ContactoEmergencia`
- **Por nivel**: hoy ROJA → todos + webhook emergencias; AMARILLA → todos. Para 10/10:
  elegir **a quién y por qué canal** según nivel 🔶
- **Webhook a la prepaga / central de emergencias** 🔶 `emergency_webhook` (global, no por paciente)
- **Riesgo emocional**: a quién avisar y **qué línea de crisis** usar 🆕 (hoy 135 fijo, AR)
- **Avisarle al paciente que se va a contactar a la familia**: sí/no 🆕 (hoy siempre, recién agregado al guion)

### F. Privacidad y reporte (qué ve la familia) — 🔶/🆕
- Qué incluye el reporte: rutina ✅ + relato emocional ✅ + **transcripción sí/no** 🆕
- **Retención** de la transcripción (borrar a los N días) 🆕
- **Varios familiares con acceso** y permisos (ver/editar) 🆕 (hoy un único dueño)

### G. Cuenta y suscripción — ✅/🔶
- Plan y estado de suscripción ✅ · varios pacientes por cuenta ✅ · facturación 🔶

---

## El onboarding ideal (wizard de 5 pasos)

1. **¿A quién cuidamos?** nombre, teléfono, consentimiento.
2. **¿Qué le pasa?** → elegí una **plantilla** (HTA / diabetes / post-ACV / cognitivo /
   ánimo) → precarga rutina + umbrales + preguntas. (Salteable.)
3. **¿Cuándo lo llamamos?** horario, días, insistencia, duración.
4. **¿A quién avisamos si algo pasa?** contactos + orden.
5. **Escuchá una demo** (voz + saludo) y **activá**. Listo.

Todo lo demás (personalidad fina, canales por nivel, privacidad) queda en *Ajustes →
modo avanzado*, con los defaults ya puestos.

---

## Por qué esto da un 10/10
- **Cuidador tranquilo**: lo arma en 3 minutos y confía en los defaults.
- **Paciente cómodo**: voz, trato y temas a su medida → se siente acompañado, no "atendido".
- **Familia seguro**: controla a quién y cómo se avisa, y qué se guarda.
- **Prepaga conforme**: plantillas clínicas, umbrales auditables, reporte claro.

*Las decisiones que requieren tu criterio están en `CAMINO_A_100.md → PENDIENTES DE DECISIÓN`.*
