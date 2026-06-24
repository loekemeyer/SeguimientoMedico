/* SeguimientoMedico — frontend (vanilla JS, sin build) */
const API = "";                 // misma raíz que sirve la app
const TOKEN_KEY = "sm_token";

/* ---------- helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const token = () => localStorage.getItem(TOKEN_KEY);

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast is-show" + (isError ? " toast--error" : "");
  setTimeout(() => (t.className = "toast"), 3200);
}

async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && token()) headers.Authorization = `Bearer ${token()}`;
  const res = await fetch(API + path, {
    method, headers, body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Ocurrió un error");
  return data;
}

/* ---------- navegación entre vistas ---------- */
function show(view) {
  $("#auth-view").classList.toggle("is-hidden", view !== "auth");
  $("#app-view").classList.toggle("is-hidden", view !== "app");
}
function showPage(page) {
  $("#page-list").classList.toggle("is-hidden", page !== "list");
  $("#page-detail").classList.toggle("is-hidden", page !== "detail");
}

/* ====================================================================
   AUTENTICACIÓN
==================================================================== */
$$(".tabs__btn").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".tabs__btn").forEach((x) => x.classList.remove("is-active"));
    b.classList.add("is-active");
    const tab = b.dataset.tab;
    $("#form-login").classList.toggle("is-hidden", tab !== "login");
    $("#form-register").classList.toggle("is-hidden", tab !== "register");
  })
);

$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("[data-error]", e.target);
  err.textContent = "";
  const f = new FormData(e.target);
  try {
    const r = await api("/auth/login", {
      method: "POST", auth: false,
      body: { email: f.get("email"), password: f.get("password") },
    });
    localStorage.setItem(TOKEN_KEY, r.access_token);
    await enterApp();
  } catch (ex) { err.textContent = ex.message; }
});

// Onboarding: mostrar los campos de obra social solo si se elige esa opción.
$$('#reg-tipo input[name="tipo_cuenta"]').forEach((radio) =>
  radio.addEventListener("change", () => {
    const esObraSocial = $('#reg-tipo input[name="tipo_cuenta"]:checked').value === "obra_social";
    $("#reg-obrasocial").classList.toggle("is-hidden", !esObraSocial);
  })
);

$("#form-register").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("[data-error]", e.target);
  err.textContent = "";
  const f = new FormData(e.target);
  try {
    const r = await api("/auth/register", {
      method: "POST", auth: false,
      body: {
        nombre: f.get("nombre"), email: f.get("email"), password: f.get("password"),
        tipo_cuenta: f.get("tipo_cuenta") || "privado",
        obra_social: f.get("obra_social") || "",
        nro_afiliado: f.get("nro_afiliado") || "",
      },
    });
    localStorage.setItem(TOKEN_KEY, r.access_token);
    await enterApp();
  } catch (ex) { err.textContent = ex.message; }
});

$("#btn-logout").addEventListener("click", () => {
  localStorage.removeItem(TOKEN_KEY);
  show("auth");
});

/* ====================================================================
   APP
==================================================================== */
async function enterApp() {
  try {
    const me = await api("/auth/me");
    const inicial = (me.nombre || me.email || "U").trim()[0].toUpperCase();
    $("#avatar").textContent = inicial;
    $("#plan-chip").textContent = "Plan " + (me.plan || "trial");
    show("app");
    showPage("list");
    await loadPatients();
  } catch {
    localStorage.removeItem(TOKEN_KEY);
    show("auth");
  }
}

async function loadPatients() {
  const grid = $("#patient-grid");
  grid.innerHTML = "";
  let pacientes = [];
  try { pacientes = await api("/pacientes"); } catch (e) { toast(e.message, true); }

  $("#list-subtitle").textContent = pacientes.length
    ? `${pacientes.length} persona${pacientes.length > 1 ? "s" : ""} en seguimiento.`
    : "Cargá a tu familiar para empezar el seguimiento.";

  if (!pacientes.length) {
    const empty = document.createElement("div");
    empty.className = "emptystate";
    empty.innerHTML = `
      <div class="emptystate__icon">👵</div>
      <h2 class="emptystate__title">Empecemos por la persona a cuidar</h2>
      <p class="emptystate__text">Cargá a tu familiar (papá, mamá, la abuela…) y en un par de
        minutos queda andando el acompañamiento diario por teléfono, con avisos a la familia.</p>
      <button class="btn btn--primary" id="empty-add">＋ Agregar persona</button>`;
    grid.appendChild(empty);
    $("#empty-add", empty).addEventListener("click", openModal);
    return;
  }

  pacientes.forEach((p) => grid.appendChild(patientCard(p)));

  const add = document.createElement("button");
  add.className = "pcard pcard--add";
  add.innerHTML = `<span class="plus">＋</span><span>Agregar persona</span>`;
  add.addEventListener("click", openModal);
  grid.appendChild(add);
}

function patientCard(p) {
  const el = document.createElement("div");
  el.className = "pcard";
  const inicial = (p.nombre || "?").trim()[0].toUpperCase();
  const pat = (p.patologias || []).join(", ") || "Seguimiento general";
  const hora = p.programacion?.llamada_hora || "—";
  const estado = p.consentimiento_firmado
    ? `<span class="badge badge--verde">Activo</span>`
    : `<span class="badge badge--neutral">Falta consentimiento</span>`;
  el.innerHTML = `
    <div class="pcard__top">
      <div class="avatar">${inicial}</div>
      <div>
        <div class="pcard__name">${escapeHtml(p.nombre || "Sin nombre")}</div>
        <div class="pcard__tag">${escapeHtml(pat)}</div>
      </div>
    </div>
    <div class="pcard__row">🕒 Llamada diaria a las ${hora}</div>
    ${p.ultimo_nivel ? `<div class="pcard__row">Último seguimiento: <span class="badge badge--${p.ultimo_nivel.toLowerCase()}">${escapeHtml(p.ultimo_nivel)}</span></div>` : ""}
    <div class="pcard__foot">${estado}<span class="pcard__tag">Ver detalle →</span></div>`;
  el.addEventListener("click", () => openDetail(p.id));
  return el;
}

/* ---------- detalle ---------- */
let currentPatient = null;   // paciente abierto en el detalle

async function openDetail(id) {
  showPage("detail");
  try {
    const [p, contactos, rutina, evos, sugerencias, notifs] = await Promise.all([
      api(`/pacientes/${id}`),
      api(`/pacientes/${id}/contactos`).catch(() => []),
      api(`/pacientes/${id}/rutina`).catch(() => []),
      api(`/pacientes/${id}/evoluciones`).catch(() => []),
      api(`/pacientes/${id}/sugerencias`).catch(() => []),
      api(`/pacientes/${id}/notificaciones`).catch(() => []),
    ]);
    currentPatient = p;
    renderDetail(p, contactos, rutina, evos);
    renderSugerencias(sugerencias);
    renderNotificaciones(notifs);
  } catch (e) { toast(e.message, true); }
}

/* ---------- llamar ahora ---------- */
$("#btn-call-now").addEventListener("click", async () => {
  if (!currentPatient) return;
  try {
    const r = await api(`/pacientes/${currentPatient.id}/llamar`, { method: "POST" });
    toast(r.detail || "Llamada en curso", r.status === "error" || r.status === "no_disponible");
  } catch (e) { toast(e.message, true); }
});

/* ---------- seguimiento por WhatsApp de voz (canal económico) ---------- */
$("#btn-whatsapp").addEventListener("click", async () => {
  if (!currentPatient) return;
  if (!confirm("¿Iniciar un seguimiento por mensajes de voz de WhatsApp?")) return;
  try {
    const r = await api(`/whatsapp/iniciar/${currentPatient.id}`, { method: "POST" });
    toast(r.status === "iniciado" ? "Seguimiento por WhatsApp iniciado 📲" : (r.detail || "Listo"));
  } catch (e) { toast(e.message, true); }
});

/* ---------- agregar a la rutina ---------- */
const TIPO_ICON = {
  medicamento: "💊", presion: "🩺", glucemia: "🩸", oximetria: "🫁",
  temperatura: "🌡️", peso: "⚖️", ejercicio: "🏃", sueno: "😴",
  pregunta: "❓", despertar: "☀️", acostar: "🌙", otro: "📌",
};
const DIA_NOMBRE = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

$("#form-rutina").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentPatient) return;
  const f = new FormData(e.target);
  const dias = $$("#rutina-days input:checked").map((c) => Number(c.value));
  try {
    await api(`/pacientes/${currentPatient.id}/rutina`, {
      method: "POST",
      body: {
        tipo: f.get("tipo"), nombre: f.get("nombre"),
        frecuencia: f.get("frecuencia") || "", horario: f.get("horario") || "",
        dias: dias.length === 7 ? [] : dias, activa: true,
        aviso: f.get("aviso") || "mensaje",
      },
    });
    e.target.reset();
    $$("#rutina-days input").forEach((c) => (c.checked = true));
    const rutina = await api(`/pacientes/${currentPatient.id}/rutina`).catch(() => []);
    renderRutina(rutina);
    toast("Agregado a la rutina ✅");
  } catch (ex) { toast(ex.message, true); }
});

/* ---------- contactos de emergencia ---------- */
function renderContactos(contactos) {
  $("#detail-contacts").innerHTML = contactos.length
    ? contactos.map((c) => {
        const alertas = c.recibe_alertas ? "🔔 recibe avisos" : "🔕 no recibe";
        const det = [c.relacion, c.telefono, `${c.prioridad || 1}º en avisar`, alertas]
          .filter(Boolean).join(" · ");
        return `<div class="stack-item">👤
          <div class="stack-item__main"><div>${escapeHtml(c.nombre || "")}</div><small>${escapeHtml(det)}</small></div>
          <button class="icon-btn" data-del-contacto="${c.id}" title="Quitar contacto">✕</button>
        </div>`;
      }).join("")
    : `<p class="empty">Sin contactos. Agregá al menos uno para que lleguen los avisos.</p>`;
}

async function reloadContactos() {
  if (!currentPatient) return;
  const contactos = await api(`/pacientes/${currentPatient.id}/contactos`).catch(() => []);
  renderContactos(contactos);
}

$("#form-contacto").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentPatient) return;
  const f = new FormData(e.target);
  try {
    await api(`/pacientes/${currentPatient.id}/contactos`, {
      method: "POST",
      body: {
        nombre: f.get("nombre"), telefono: f.get("telefono"),
        relacion: f.get("relacion") || "", prioridad: Number(f.get("prioridad")) || 1,
        recibe_alertas: f.get("recibe_alertas") === "on",
      },
    });
    e.target.reset();
    await reloadContactos();
    toast("Contacto agregado ✅");
  } catch (ex) { toast(ex.message, true); }
});

$("#detail-contacts").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-del-contacto]");
  if (!btn || !currentPatient) return;
  if (!confirm("¿Quitar este contacto de emergencia?")) return;
  try {
    await api(`/pacientes/${currentPatient.id}/contactos/${btn.dataset.delContacto}`, { method: "DELETE" });
    await reloadContactos();
    toast("Contacto quitado");
  } catch (ex) { toast(ex.message, true); }
});

function renderRutina(items) {
  $("#detail-rutina").innerHTML = items.length
    ? items.map((r) => {
        const icon = TIPO_ICON[r.tipo] || "📌";
        const dias = (!r.dias || r.dias.length === 0 || r.dias.length === 7)
          ? "Todos los días" : r.dias.map((d) => DIA_NOMBRE[d]).join(", ");
        const avisoTxt = { llamada: "📞 llamada", mensaje: "💬 mensaje", ninguno: "🔕 sin aviso" }[r.aviso] || "";
        const det = [r.frecuencia, r.horario, dias, avisoTxt].filter(Boolean).join(" · ");
        return `<div class="stack-item">${icon}
          <div class="stack-item__main"><div>${escapeHtml(r.nombre || "")}</div><small>${escapeHtml(det)}</small></div>
          <button class="icon-btn" data-del-rutina="${r.id}" title="Quitar de la rutina">✕</button>
        </div>`;
      }).join("")
    : `<p class="empty">Todavía no cargaste la rutina. Empezá agregando un ítem abajo.</p>`;
}

async function reloadRutina() {
  if (!currentPatient) return;
  const rutina = await api(`/pacientes/${currentPatient.id}/rutina`).catch(() => []);
  renderRutina(rutina);
}

$("#detail-rutina").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-del-rutina]");
  if (!btn || !currentPatient) return;
  if (!confirm("¿Quitar este ítem de la rutina?")) return;
  try {
    await api(`/pacientes/${currentPatient.id}/rutina/${btn.dataset.delRutina}`, { method: "DELETE" });
    await reloadRutina();
    toast("Ítem quitado");
  } catch (ex) { toast(ex.message, true); }
});

function renderDetail(p, contactos, rutina, evos) {
  $("#detail-avatar").textContent = (p.nombre || "?").trim()[0].toUpperCase();
  $("#detail-name").textContent = p.nombre || "—";
  $("#detail-meta").textContent = (p.patologias || []).join(" · ") || "Seguimiento general";
  const st = $("#detail-status");
  if (p.consentimiento_firmado) { st.className = "badge badge--verde"; st.textContent = "Seguimiento activo"; }
  else { st.className = "badge badge--neutral"; st.textContent = "Falta consentimiento"; }

  const prog = p.programacion || {};
  const dias = (prog.llamada_dias && prog.llamada_dias.length)
    ? prog.llamada_dias.map((d) => ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"][d]).join(", ")
    : "Todos los días";
  $("#detail-schedule").innerHTML = `
    <div class="kv__row"><span>Estado</span><span>${prog.llamada_activa === false ? "Pausada" : "Activa"}</span></div>
    <div class="kv__row"><span>Hora</span><span>${prog.llamada_hora || "—"}</span></div>
    <div class="kv__row"><span>Días</span><span>${dias}</span></div>
    <div class="kv__row"><span>Zona</span><span>${(prog.llamada_zona || "").split("/").pop() || "—"}</span></div>`;

  renderContactos(contactos);
  renderRutina(rutina);

  $("#detail-history").innerHTML = evos.length
    ? evos.map(historyRow).join("")
    : `<p class="empty">Todavía no hay seguimientos registrados.</p>`;
}

/* ---------- sugerencias del agente + avisos enviados ---------- */
const PRIO_BADGE = { alta: "roja", media: "amarilla", baja: "neutral" };

function renderSugerencias(sugs) {
  const card = $("#detail-sugerencias-card");
  if (!sugs || !sugs.length) { card.classList.add("is-hidden"); return; }
  card.classList.remove("is-hidden");
  $("#detail-sugerencias").innerHTML = sugs.map((s) => {
    const badge = PRIO_BADGE[s.prioridad] || "neutral";
    return `<div class="stack-item">
      <span class="badge badge--${badge}">${escapeHtml(s.prioridad || "")}</span>
      <div class="stack-item__main">${escapeHtml(s.texto || "")}</div></div>`;
  }).join("");
}

const CANAL_ICON = { whatsapp: "💬", webhook: "🛰️", sms: "✉️" };

function renderNotificaciones(notifs) {
  $("#detail-notificaciones").innerHTML = (notifs && notifs.length)
    ? notifs.map((n) => {
        const fecha = new Date(n.fecha).toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
        const icon = CANAL_ICON[n.canal] || "🔔";
        const nivel = (n.nivel_alerta || "VERDE").toLowerCase();
        const estado = n.enviado ? "✓ enviado" : "✗ no enviado";
        return `<div class="stack-item">${icon}
          <div class="stack-item__main">
            <div>${escapeHtml(n.destino || "Familia")} <span class="badge badge--${nivel}">${escapeHtml(n.nivel_alerta || "")}</span></div>
            <small>${fecha} · ${estado} · ${escapeHtml(n.contenido || "")}</small>
          </div></div>`;
      }).join("")
    : `<p class="empty">Todavía no se enviaron avisos. Aparecen acá cuando el sistema alerta a la familia.</p>`;
}

function metricasChips(r) {
  if (!r) return "";
  const chips = [];
  if (r.presion_sistolica && r.presion_diastolica) chips.push(`🩺 ${r.presion_sistolica}/${r.presion_diastolica}`);
  if (r.glucemia != null) chips.push(`🩸 ${r.glucemia} mg/dL`);
  if (r.saturacion_oxigeno != null) chips.push(`🫁 ${r.saturacion_oxigeno}%`);
  if (r.temperatura != null) chips.push(`🌡️ ${r.temperatura}°`);
  if (r.frecuencia_cardiaca != null) chips.push(`❤️ ${r.frecuencia_cardiaca} lpm`);
  if (r.dolor != null) chips.push(`💢 dolor ${r.dolor}/10`);
  if (r.peso != null) chips.push(`⚖️ ${r.peso} kg`);
  if (r.adherencia_medicacion === "no_tomo") chips.push("💊 no tomó");
  else if (r.adherencia_medicacion === "tomo_parcial") chips.push("💊 tomó parcial");
  if (r.caida_reportada) chips.push("🤕 caída");
  if (r.riesgo_emocional === "riesgo_suicida") chips.push("🆘 riesgo emocional");
  else if (r.riesgo_emocional === "angustia_aguda") chips.push("😟 angustia");
  if (!chips.length) return "";
  return `<div class="tl-chips">${chips.map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("")}</div>`;
}

function historyRow(e) {
  const fecha = new Date(e.fecha).toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
  const nivel = (e.nivel_alerta || "VERDE").toLowerCase();
  const relato = e.relato || (e.motivos || []).join("; ") || "Sin novedades";
  return `<div class="tl-item">
    <div class="tl-date">${fecha}</div>
    <div><div class="tl-summary">${escapeHtml(relato)}</div>
      ${(e.motivos || []).length ? `<div class="tl-reasons">${escapeHtml(e.motivos.join(" · "))}</div>` : ""}
      ${metricasChips(e.readout)}</div>
    <span class="badge badge--${nivel}">${e.nivel_alerta}</span>
  </div>`;
}

$("#btn-back").addEventListener("click", () => { showPage("list"); loadPatients(); });
$("#btn-add").addEventListener("click", openModal);

/* ---------- modal alta / edición de paciente ---------- */
let editingId = null;
const form = $("#form-patient");

function openModal() {            // alta
  editingId = null;
  $("#modal-title").textContent = "Agregar persona a cuidar";
  $("#contacto-section").classList.remove("is-hidden");
  form.reset();
  $("[name=llamada_hora]", form).value = "10:00";
  $$("#patient-days input").forEach((c) => (c.checked = true));
  $("#modal").classList.remove("is-hidden");
}

function openEditModal() {        // edición del paciente abierto
  if (!currentPatient) return;
  editingId = currentPatient.id;
  $("#modal-title").textContent = "Editar persona";
  $("#contacto-section").classList.add("is-hidden");
  form.reset();
  $("[name=nombre]", form).value = currentPatient.nombre || "";
  $("[name=telefono_whatsapp]", form).value = currentPatient.telefono_whatsapp || "";
  $("[name=patologias]", form).value = (currentPatient.patologias || []).join(", ");
  $("[name=llamada_hora]", form).value = currentPatient.programacion?.llamada_hora || "10:00";
  $("[name=consentimiento_firmado]", form).checked = !!currentPatient.consentimiento_firmado;
  $("[name=nivel_insistencia]", form).value = String(currentPatient.programacion?.nivel_insistencia || 2);
  const pers = currentPatient.personalidad || {};
  $("[name=trato]", form).value = pers.trato || "vos";
  $("[name=acompanante_nombre]", form).value = pers.acompanante_nombre || "";
  $("[name=voz]", form).value = pers.voz || "coral";
  $("[name=velocidad]", form).value = String(pers.velocidad ?? 0.9);
  $("[name=temas_preferidos]", form).value = pers.temas_preferidos || "";
  $("[name=temas_evitar]", form).value = pers.temas_evitar || "";
  const prog = currentPatient.programacion || {};
  $("[name=llamada_activa]", form).checked = prog.llamada_activa !== false;
  $("[name=llamada_zona]", form).value = prog.llamada_zona || "America/Argentina/Buenos_Aires";
  const dias = prog.llamada_dias || [];
  $$("#patient-days input").forEach((c) => {
    c.checked = dias.length === 0 || dias.includes(Number(c.value));
  });
  $("#modal").classList.remove("is-hidden");
}

function closeModal() {
  $("#modal").classList.add("is-hidden");
  form.reset();
  $("[data-error]", form).textContent = "";
}
$$("[data-close]").forEach((el) => el.addEventListener("click", closeModal));
$("#btn-edit").addEventListener("click", openEditModal);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("[data-error]", e.target);
  err.textContent = "";
  const f = new FormData(e.target);
  const patologias = (f.get("patologias") || "").split(",").map((s) => s.trim()).filter(Boolean);
  const nivel = Number(f.get("nivel_insistencia")) || 2;
  const personalidad = {
    voz: f.get("voz") || "coral",
    velocidad: Number(f.get("velocidad")) || 0.9,
    trato: f.get("trato") || "vos",
    acompanante_nombre: f.get("acompanante_nombre") || "",
    temas_preferidos: f.get("temas_preferidos") || "",
    temas_evitar: f.get("temas_evitar") || "",
  };
  const dias = $$("#patient-days input:checked").map((c) => Number(c.value));
  const programacion = {
    llamada_hora: f.get("llamada_hora") || "10:00",
    nivel_insistencia: nivel,
    llamada_activa: f.get("llamada_activa") === "on",
    llamada_zona: f.get("llamada_zona") || "America/Argentina/Buenos_Aires",
    llamada_dias: dias.length === 7 ? [] : dias,
  };
  const body = {
    nombre: f.get("nombre"),
    telefono_whatsapp: f.get("telefono_whatsapp"),
    consentimiento_firmado: f.get("consentimiento_firmado") === "on",
    patologias,
    personalidad,
    programacion,
  };
  try {
    if (editingId) {
      const p = await api(`/pacientes/${editingId}`, { method: "PUT", body });
      closeModal();
      toast("Cambios guardados ✅");
      await openDetail(p.id);
    } else {
      const p = await api("/pacientes", { method: "POST", body });
      if (f.get("contacto_nombre") && f.get("contacto_telefono")) {
        await api(`/pacientes/${p.id}/contactos`, {
          method: "POST",
          body: { nombre: f.get("contacto_nombre"), telefono: f.get("contacto_telefono"), relacion: "familiar", prioridad: 1 },
        }).catch(() => {});
      }
      closeModal();
      toast("Persona agregada ✅");
      await loadPatients();
    }
  } catch (ex) { err.textContent = ex.message; }
});

/* ---------- util ---------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ====================================================================
   MI SUSCRIPCIÓN
==================================================================== */
const subModal = $("#modal-sub");
$("#plan-chip").addEventListener("click", openSubModal);
$$("[data-close-sub]").forEach((el) =>
  el.addEventListener("click", () => subModal.classList.add("is-hidden"))
);

async function openSubModal() {
  subModal.classList.remove("is-hidden");
  $("#sub-body").innerHTML = `<p class="empty">Cargando…</p>`;
  try {
    renderSub(await api("/billing/estado"));
  } catch (e) {
    $("#sub-body").innerHTML = `<p class="form__error">${escapeHtml(e.message)}</p>`;
  }
}

function renderSub(s) {
  const vence = s.suscripcion_vence
    ? new Date(s.suscripcion_vence).toLocaleDateString("es-AR")
    : "—";
  const plan = s.plan_disponible || {};
  let html = `<div class="kv">
    <div class="kv__row"><span>Estado</span><span>${escapeHtml(s.plan || "trial")}</span></div>
    <div class="kv__row"><span>Vigente hasta</span><span>${vence}</span></div>`;
  if (s.tipo_cuenta === "obra_social") {
    html += `<div class="kv__row"><span>Cobertura</span><span>${escapeHtml(s.obra_social || "Obra social")}</span></div></div>
      <p class="hint">Tu seguimiento está cubierto por tu obra social. No tenés que pagar nada. 💚</p>`;
  } else {
    html += `</div>
      <p class="hint">${escapeHtml(plan.nombre || "Plan")}: <strong>$${plan.precio || 0} ${escapeHtml(plan.moneda || "ARS")}</strong> por mes.</p>
      <button class="btn btn--primary btn--block" id="btn-suscribir">Suscribirme</button>`;
  }
  $("#sub-body").innerHTML = html;
  const btn = $("#btn-suscribir");
  if (btn) btn.addEventListener("click", suscribir);
}

async function suscribir() {
  try {
    const r = await api("/billing/suscribir", { method: "POST" });
    if (r.checkout_url) {
      window.open(r.checkout_url, "_blank", "noopener");
      toast("Te abrimos el pago de Mercado Pago 💳");
      return;
    }
    toast(r.detail || "Listo", r.status === "no_disponible");
  } catch (e) { toast(e.message, true); }
}

/* ---------- PWA: registrar el service worker (app instalable) ---------- */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("/sw.js").catch(() => {})
  );
}

/* ---------- arranque ---------- */
if (token()) enterApp(); else show("auth");
