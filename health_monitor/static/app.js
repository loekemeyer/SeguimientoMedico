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

async function api(path, { method = "GET", body, auth = true, bearer } = {}) {
  const headers = { "Content-Type": "application/json" };
  const tok = bearer || (auth ? token() : null);
  if (tok) headers.Authorization = `Bearer ${tok}`;
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
  $("#paciente-login-view")?.classList.toggle("is-hidden", view !== "paciente-login");
  $("#acompanado-view")?.classList.toggle("is-hidden", view !== "acompanado");
}
function showPage(page) {
  $("#page-list").classList.toggle("is-hidden", page !== "list");
  $("#page-detail").classList.toggle("is-hidden", page !== "detail");
  $("#page-cuenta").classList.toggle("is-hidden", page !== "cuenta");
  // El detalle es parte del flujo "Personas", así que esa pestaña queda activa.
  const navActive = page === "cuenta" ? "cuenta" : "personas";
  $$(".bnav__btn").forEach((b) => b.classList.toggle("is-active", b.dataset.nav === navActive));
  if (page !== "detail") stopClaveRotativa();
  window.scrollTo(0, 0);
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

/* mostrar / ocultar contraseña */
$$(".pw-toggle").forEach((btn) =>
  btn.addEventListener("click", () => {
    const input = btn.parentElement.querySelector("input");
    if (!input) return;
    const ver = input.type === "password";
    input.type = ver ? "text" : "password";
    btn.textContent = ver ? "🙈" : "👁";
    btn.setAttribute("aria-label", ver ? "Ocultar contraseña" : "Mostrar contraseña");
  })
);

$("#form-login")?.addEventListener("submit", async (e) => {
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

// Reflejar la obra social elegida en el distintivo (monograma + nombre).
const osSelect = $('#reg-obrasocial select[name="obra_social"]');
if (osSelect) {
  const syncOsBrand = () => {
    const val = (osSelect.value || "Obra social").trim();
    $("#os-card-name").textContent = val;
    $("#os-logo").textContent = (val[0] || "O").toUpperCase();
  };
  osSelect.addEventListener("change", syncOsBrand);
  syncOsBrand();
}

$("#form-register")?.addEventListener("submit", async (e) => {
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

$("#btn-logout")?.addEventListener("click", () => {
  localStorage.removeItem(TOKEN_KEY);
  show("auth");
});

/* ====================================================================
   APP
==================================================================== */
let currentUser = null;

async function enterApp() {
  try {
    const me = await api("/auth/me");
    currentUser = me;
    const inicial = (me.nombre || me.email || "U").trim()[0].toUpperCase();
    $("#avatar").textContent = inicial;
    show("app");
    showPage("list");
    refreshSubButton();
    await loadPatients();
  } catch {
    localStorage.removeItem(TOKEN_KEY);
    show("auth");
  }
}

/* ---------- navegación inferior (app shell) + pantalla "Cuenta" ---------- */
$$(".bnav__btn").forEach((b) =>
  b.addEventListener("click", () => {
    const nav = b.dataset.nav;
    if (nav === "suscripcion") { openSubModal(); return; }
    if (nav === "cuenta") { showPage("cuenta"); loadCuenta(); }
    else { showPage("list"); loadPatients(); }
  })
);

async function refreshSubButton() {
  const lbl = $("#bnav-sub-lbl"), ico = $("#bnav-sub-ico"), btn = $("#bnav-sub");
  if (!lbl || !ico) return;
  try {
    const s = await api("/billing/estado");
    const suscripto = s.tipo_cuenta === "obra_social" ||
      (s.plan && s.plan !== "trial" && s.plan !== "cancelado");
    lbl.textContent = suscripto ? "Suscripto" : "Suscribirse";
    ico.textContent = suscripto ? "👑" : "💳";
    if (btn) btn.classList.toggle("is-suscripto", !!suscripto);
  } catch { /* sin red: dejamos el default */ }
}
$("#avatar")?.addEventListener("click", () => { showPage("cuenta"); loadCuenta(); });

async function loadCuenta() {
  const me = currentUser || {};
  const inicial = (me.nombre || me.email || "U").trim()[0].toUpperCase();
  $("#cuenta-avatar").textContent = inicial;
  $("#cuenta-name").textContent = me.nombre || "Mi cuenta";
  $("#cuenta-mail").textContent = me.email || "";
  try {
    const s = await api("/billing/estado");
    const tipo = s.tipo_cuenta === "obra_social"
      ? `Obra social — ${s.obra_social || ""}`
      : "Privada";
    const vence = s.suscripcion_vence
      ? new Date(s.suscripcion_vence).toLocaleDateString("es-AR") : "—";
    $("#cuenta-kv").innerHTML = `
      <div class="kv__row"><span>Plan</span><span>${escapeHtml(s.plan || "trial")}</span></div>
      <div class="kv__row"><span>Tipo de cuenta</span><span>${escapeHtml(tipo)}</span></div>
      <div class="kv__row"><span>Vigente hasta</span><span>${escapeHtml(vence)}</span></div>`;
  } catch {
    $("#cuenta-kv").innerHTML =
      `<div class="kv__row"><span>Plan</span><span>${escapeHtml((currentUser && currentUser.plan) || "trial")}</span></div>`;
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

  // El botón verde "＋ Agregar persona" de arriba ya cubre el alta; no repetimos
  // la tarjeta punteada cuando ya hay personas (evita saturar con la misma acción).
  pacientes.forEach((p) => grid.appendChild(patientCard(p)));
}

function patologiasBadges(arr) {
  const items = [...new Set((arr || []).map((x) => normalizaPatologia(x)).filter(Boolean))];
  if (!items.length) return "";
  return `<div class="pat-badges">${items.map((p) => `<span class="pat-badge">${escapeHtml(p)}</span>`).join("")}</div>`;
}

function patientCard(p) {
  const el = document.createElement("div");
  el.className = "pcard";
  const inicial = (p.nombre || "?").trim()[0].toUpperCase();
  const patHtml = patologiasBadges(p.patologias) || `<div class="pcard__tag">Seguimiento general</div>`;
  const hora = p.programacion?.llamada_hora || "—";
  const estado = p.consentimiento_firmado
    ? `<span class="badge badge--verde">Activo</span>`
    : `<span class="badge badge--neutral">Falta consentimiento</span>`;
  el.innerHTML = `
    <div class="pcard__top">
      <div class="avatar">${inicial}</div>
      <div class="pcard__head">
        <div class="pcard__name">${escapeHtml(p.nombre || "Sin nombre")}</div>
        ${patHtml}
      </div>
      ${estado}
    </div>
    <div class="pcard__row">🕒 Llamada diaria a las ${hora}</div>
    ${p.ultimo_nivel ? `<div class="pcard__row">Último seguimiento: <span class="badge badge--${p.ultimo_nivel.toLowerCase()}">${escapeHtml(p.ultimo_nivel)}</span></div>` : ""}
    <div class="pcard__foot"><span class="pcard__tag">Ver detalle →</span></div>`;
  el.addEventListener("click", () => openDetail(p.id));
  return el;
}

/* ---------- detalle ---------- */
let currentPatient = null;   // paciente abierto en el detalle

/* ---------- clave rotativa de 2 dígitos (panel del familiar) ---------- */
let claveTimer = null, claveSeg = 0, clavePacienteId = null;
function stopClaveRotativa() { if (claveTimer) clearInterval(claveTimer); claveTimer = null; }
async function _fetchClave(id) {
  try {
    const r = await api(`/pacientes/${id}/codigo-rotativo`);
    const val = $("#detail-clave-val");
    if (val) val.textContent = r.clave || "··";
    claveSeg = r.segundos || 0;
  } catch { claveSeg = 0; }
}
async function startClaveRotativa(id) {
  stopClaveRotativa();
  if (!$("#detail-clave-val")) return;
  clavePacienteId = id;
  await _fetchClave(id);
  claveTimer = setInterval(async () => {
    const seg = $("#detail-clave-seg");
    if (seg) seg.textContent = claveSeg > 0 ? `cambia en ${claveSeg}s` : "actualizando…";
    claveSeg--;
    if (claveSeg < 0) await _fetchClave(clavePacienteId);
  }, 1000);
}

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
    renderEstadoHoy(evos);
    renderTendencias(evos);
    renderSugerencias(sugerencias);
    renderNotificaciones(notifs);
    startClaveRotativa(id);
    resetAddForms();
  } catch (e) { toast(e.message, true); }
}

/* ---------- llamar ahora ---------- */
$("#btn-call-now")?.addEventListener("click", async () => {
  if (!currentPatient) return;
  try {
    const r = await api(`/pacientes/${currentPatient.id}/llamar`, { method: "POST" });
    toast(r.detail || "Llamada en curso", r.status === "error" || r.status === "no_disponible");
  } catch (e) { toast(e.message, true); }
});

/* ---------- seguimiento por WhatsApp de voz (canal económico) ---------- */
$("#btn-whatsapp")?.addEventListener("click", async () => {
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

$("#form-rutina")?.addEventListener("submit", async (e) => {
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

$("#form-contacto")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentPatient) return;
  const f = new FormData(e.target);
  try {
    await api(`/pacientes/${currentPatient.id}/contactos`, {
      method: "POST",
      body: {
        nombre: f.get("nombre"), telefono: getPhone(e.target, "telefono"),
        relacion: f.get("relacion") || "", prioridad: Number(f.get("prioridad")) || 1,
        recibe_alertas: f.get("recibe_alertas") === "on",
      },
    });
    e.target.reset();
    await reloadContactos();
    toast("Contacto agregado ✅");
  } catch (ex) { toast(ex.message, true); }
});

$("#detail-contacts")?.addEventListener("click", async (e) => {
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

$("#detail-rutina")?.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-del-rutina]");
  if (!btn || !currentPatient) return;
  if (!confirm("¿Quitar este ítem de la rutina?")) return;
  try {
    await api(`/pacientes/${currentPatient.id}/rutina/${btn.dataset.delRutina}`, { method: "DELETE" });
    await reloadRutina();
    toast("Ítem quitado");
  } catch (ex) { toast(ex.message, true); }
});

function renderEstadoHoy(evos) {
  const card = $("#detail-estado-hoy");
  if (!card) return;
  const e = (evos || [])[0];
  if (!e) {
    card.className = "card estado-hoy";
    card.innerHTML = `<div class="estado-hoy__row"><span class="estado-hoy__emoji">🕊️</span>
      <div class="estado-hoy__main"><div class="estado-hoy__title">Sin seguimientos todavía</div>
      <div class="estado-hoy__sub">Cuando haya una llamada o una charla, vas a ver acá cómo está hoy.</div></div></div>`;
    return;
  }
  const nivel = (e.nivel_alerta || "VERDE").toLowerCase();
  const emoji = { verde: "🟢", amarilla: "🟡", roja: "🔴" }[nivel] || "🟢";
  const fecha = new Date(e.fecha).toLocaleDateString("es-AR", { day: "2-digit", month: "long" });
  const relato = e.relato || (e.motivos || []).join("; ") || "Sin novedades.";
  card.className = "card estado-hoy estado-hoy--" + nivel;
  card.innerHTML = `<div class="estado-hoy__row">
    <span class="estado-hoy__emoji">${emoji}</span>
    <div class="estado-hoy__main">
      <div class="estado-hoy__title">¿Cómo está? <small>${fecha}</small></div>
      <div class="estado-hoy__sub">${escapeHtml(relato)}</div>
      ${metricasChips(e.readout)}
    </div></div>`;
}

/* ---------- tendencias (sparklines SVG, sin librerías) ---------- */
function sparklineSVG(values, color) {
  // values: array cronológico (puede tener null donde no hubo dato)
  const n = values.length;
  const pts = [];
  values.forEach((v, i) => { if (v != null && !isNaN(v)) pts.push({ i, v }); });
  if (pts.length < 2) return null;
  const vals = pts.map((p) => p.v);
  const min = Math.min(...vals), max = Math.max(...vals);
  const flat = max === min;
  const range = (max - min) || 1;
  const W = 100, H = 30, pad = 3;
  const x = (i) => n > 1 ? (i / (n - 1)) * W : W / 2;
  const y = (v) => flat ? H / 2 : H - pad - ((v - min) / range) * (H - pad * 2);
  const poly = pts.map((p) => `${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return `<svg class="spark__svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <polyline points="${poly}" fill="none" stroke="${color}" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(last.i).toFixed(1)}" cy="${y(last.v).toFixed(1)}" r="2.4" fill="${color}"/>
  </svg>`;
}

const NIVEL_ANIMO = { verde: 3, amarilla: 2, roja: 1 };
function renderTendencias(evos) {
  const card = $("#detail-tendencias-card");
  const cont = $("#detail-tendencias");
  if (!card || !cont) return;
  // evos viene del más nuevo al más viejo; lo damos vuelta y tomamos los últimos 14
  const serie = (evos || []).slice(0, 14).reverse();
  const get = (fn) => serie.map(fn);
  const defs = [
    { label: "Presión", unidad: "sist.", color: "#0d9488",
      vals: get((e) => e.readout?.presion_sistolica ?? null),
      fmt: (v) => `${v}` },
    { label: "Peso", unidad: "kg", color: "#7c3aed",
      vals: get((e) => e.readout?.peso ?? null),
      fmt: (v) => `${v}` },
    { label: "Ánimo", unidad: "", color: "#f59e0b",
      vals: get((e) => NIVEL_ANIMO[(e.nivel_alerta || "").toLowerCase()] ?? null),
      fmt: (v) => ({ 3: "Bien", 2: "Atención", 1: "Alerta" }[Math.round(v)] || "—") },
  ];
  const cards = [];
  for (const d of defs) {
    const svg = sparklineSVG(d.vals, d.color);
    if (!svg) continue;
    const reales = d.vals.filter((v) => v != null);
    const ultimo = reales[reales.length - 1];
    cards.push(`<div class="spark">
      <div class="spark__head"><span class="spark__label">${d.label}</span>
        <span class="spark__val">${d.fmt(ultimo)}${d.unidad ? " " + d.unidad : ""}</span></div>
      ${svg}</div>`);
  }
  if (!cards.length) { card.classList.add("is-hidden"); return; }
  card.classList.remove("is-hidden");
  cont.innerHTML = cards.join("");
}

function renderDetail(p, contactos, rutina, evos) {
  $("#detail-avatar").textContent = (p.nombre || "?").trim()[0].toUpperCase();
  $("#detail-name").textContent = p.nombre || "—";
  $("#detail-meta").innerHTML = patologiasBadges(p.patologias) || "Seguimiento general";
  $("#detail-codigo").textContent = p.codigo_acceso || "—";
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

$("#btn-back")?.addEventListener("click", () => { showPage("list"); loadPatients(); });
$("#btn-add")?.addEventListener("click", openModal);

/* mostrar los formularios de "agregar contacto/rutina" solo al tocar (no abrumar) */
function resetAddForms() {
  $$(".addform-toggle").forEach((b) => {
    b.classList.remove("is-hidden");
    const f = $("#" + b.dataset.form);
    if (f) f.classList.add("is-hidden");
  });
}
$$(".addform-toggle").forEach((b) => b.addEventListener("click", () => {
  const f = $("#" + b.dataset.form);
  if (!f) return;
  f.classList.remove("is-hidden");
  b.classList.add("is-hidden");
}));

/* rutina: autocompletar la descripción de lo obvio (automediciones) — no llenar de más */
const RUTINA_DEFECTO = {
  presion: "Tomar la presión", glucemia: "Medir la glucemia",
  oximetria: "Medir la saturación (oxímetro)", temperatura: "Tomar la temperatura",
  peso: "Pesarse", despertar: "Despertarse", acostar: "Acostarse", sueno: "Dormir / descansar",
};
$('#form-rutina select[name="tipo"]')?.addEventListener("change", (e) => {
  const nombre = $('#form-rutina input[name="nombre"]');
  if (!nombre) return;
  const def = RUTINA_DEFECTO[e.target.value];
  if (def) nombre.value = def;
  else if (Object.values(RUTINA_DEFECTO).includes(nombre.value)) nombre.value = "";
  nombre.placeholder = e.target.value === "medicamento" ? "Ej: Losartán 50mg"
    : e.target.value === "pregunta" ? "Ej: ¿Cómo durmió anoche?" : "Descripción";
});

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
  setPatologiasChips([]);
  $("#modal").classList.remove("is-hidden");
}

function openEditModal() {        // edición del paciente abierto
  if (!currentPatient) return;
  editingId = currentPatient.id;
  $("#modal-title").textContent = "Editar persona";
  $("#contacto-section").classList.add("is-hidden");
  form.reset();
  $("[name=nombre]", form).value = currentPatient.nombre || "";
  setPhone(form, "telefono_whatsapp", currentPatient.telefono_whatsapp || "");
  setPatologiasChips(currentPatient.patologias || []);
  $("[name=llamada_hora]", form).value = currentPatient.programacion?.llamada_hora || "10:00";
  $("[name=consentimiento_firmado]", form).checked = !!currentPatient.consentimiento_firmado;
  const _nivelIns = String(currentPatient.programacion?.nivel_insistencia || 2);
  const _insRadio = $(`[name=nivel_insistencia][value="${_nivelIns}"]`, form);
  if (_insRadio) _insRadio.checked = true;
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
$("#btn-edit")?.addEventListener("click", openEditModal);

/* ---------- patologías como chips (con normalización automática) ---------- */
const NORMALIZA_PATOLOGIA = {
  "le cuesta dormir": "Insomnio", "no duerme": "Insomnio", "duerme mal": "Insomnio",
  "no puede dormir": "Insomnio", "insomnio": "Insomnio",
  "presion alta": "Hipertensión", "presión alta": "Hipertensión", "hipertension": "Hipertensión",
  "la presion": "Hipertensión", "azucar": "Diabetes", "azúcar": "Diabetes", "diabetes": "Diabetes",
  "colesterol": "Colesterol alto (dislipidemia)", "del corazon": "Cardiopatía",
  "corazon": "Cardiopatía", "corazón": "Cardiopatía",
  "se olvida": "Deterioro cognitivo", "olvidos": "Deterioro cognitivo",
  "perdida de memoria": "Deterioro cognitivo", "pérdida de memoria": "Deterioro cognitivo",
  "memoria": "Deterioro cognitivo", "demencia": "Demencia", "alzheimer": "Alzheimer",
  "triste": "Depresión", "deprimido": "Depresión", "depresion": "Depresión", "depresión": "Depresión",
  "ansioso": "Ansiedad", "ansiedad": "Ansiedad", "nervioso": "Ansiedad",
  "se cae": "Riesgo de caídas", "caidas": "Riesgo de caídas", "caídas": "Riesgo de caídas",
  "se marea": "Mareos / vértigo", "mareos": "Mareos / vértigo", "vertigo": "Mareos / vértigo",
  "epoc": "EPOC", "asma": "Asma", "artrosis": "Artrosis", "artritis": "Artritis",
  "no escucha": "Hipoacusia", "sordo": "Hipoacusia", "no ve bien": "Baja visión",
  "parkinson": "Parkinson", "tiroides": "Trastorno de tiroides",
};
function normalizaPatologia(txt) {
  const limpio = (txt || "").trim();
  if (!limpio) return "";
  const key = limpio.toLowerCase();
  if (NORMALIZA_PATOLOGIA[key]) return NORMALIZA_PATOLOGIA[key];
  for (const [frase, termino] of Object.entries(NORMALIZA_PATOLOGIA)) {
    if (key.includes(frase)) return termino;
  }
  return limpio.charAt(0).toUpperCase() + limpio.slice(1);
}
let patologiasChips = [];
function renderPatologiasChips() {
  const tags = $("#patologias-tags");
  if (!tags) return;
  tags.innerHTML = patologiasChips.map((p, i) =>
    `<span class="chip chip--tag">${escapeHtml(p)}<button type="button" class="chip__x" data-pat="${i}" aria-label="Quitar">✕</button></span>`
  ).join("");
}
function setPatologiasChips(arr) {
  patologiasChips = [...(arr || [])];
  renderPatologiasChips();
  const e = $("#patologias-entry"); if (e) e.value = "";
}
function addPatologiaFromEntry() {
  const e = $("#patologias-entry"); if (!e) return;
  const norm = normalizaPatologia(e.value);
  if (norm && !patologiasChips.includes(norm)) patologiasChips.push(norm);
  e.value = "";
  renderPatologiasChips();
}
function getPatologias() {
  const e = $("#patologias-entry");
  const pend = normalizaPatologia(e ? e.value : "");
  const all = [...patologiasChips];
  if (pend && !all.includes(pend)) all.push(pend);
  return all;
}
(function wirePatologias() {
  const entry = $("#patologias-entry");
  const tags = $("#patologias-tags");
  if (!entry || !tags) return;
  entry.addEventListener("keydown", (ev) => {
    if (ev.key === "," || ev.key === "Enter") { ev.preventDefault(); addPatologiaFromEntry(); }
    else if (ev.key === "Backspace" && !entry.value && patologiasChips.length) {
      patologiasChips.pop(); renderPatologiasChips();
    }
  });
  entry.addEventListener("blur", addPatologiaFromEntry);
  tags.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-pat]");
    if (!b) return;
    patologiasChips.splice(Number(b.dataset.pat), 1);
    renderPatologiasChips();
  });
})();

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("[data-error]", e.target);
  err.textContent = "";
  const f = new FormData(e.target);
  const patologias = getPatologias();
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
    telefono_whatsapp: getPhone(e.target, "telefono_whatsapp"),
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
          body: { nombre: f.get("contacto_nombre"), telefono: getPhone(e.target, "contacto_telefono"), relacion: "familiar", prioridad: 1 },
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

/* ---------- teléfono con país (bandera + código, sin escribir el +54) ---------- */
function getPhone(scope, name) {
  const num = $(`[name="${name}"]`, scope);
  if (!num) return "";
  const cc = num.closest(".phone-input")?.querySelector(".phone-cc")?.value || "+549";
  let n = (num.value || "").replace(/\D/g, "").replace(/^0+/, "");
  const ccd = cc.replace(/\D/g, "");
  if (n.startsWith(ccd)) n = n.slice(ccd.length);
  return n ? cc + n : "";
}
function setPhone(scope, name, full) {
  const num = $(`[name="${name}"]`, scope);
  if (!num) return;
  const sel = num.closest(".phone-input")?.querySelector(".phone-cc");
  const digits = (full || "").replace(/\D/g, "");
  if (sel) {
    const opts = [...sel.options].map((o) => o.value)
      .sort((a, b) => b.replace(/\D/g, "").length - a.replace(/\D/g, "").length);
    for (const cc of opts) {
      const d = cc.replace(/\D/g, "");
      if (digits.startsWith(d)) { sel.value = cc; num.value = digits.slice(d.length); return; }
    }
  }
  num.value = digits;
}

/* ====================================================================
   MI SUSCRIPCIÓN
==================================================================== */
const subModal = $("#modal-sub");
$("#btn-mi-suscripcion")?.addEventListener("click", openSubModal);
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

const PLAN_META = {
  app: { icon: "📱", desc: "La persona charla desde la app con su código de 6 dígitos." },
  telefono: { icon: "📞", desc: "La llamamos por teléfono y charla por ahí." },
};

function renderSub(s) {
  const vence = s.suscripcion_vence
    ? new Date(s.suscripcion_vence).toLocaleDateString("es-AR")
    : "—";
  let html = `<div class="kv">
    <div class="kv__row"><span>Estado</span><span>${escapeHtml(s.plan || "trial")}</span></div>
    <div class="kv__row"><span>Vigente hasta</span><span>${vence}</span></div></div>`;
  if (s.tipo_cuenta === "obra_social") {
    html += `<p class="hint">Tu seguimiento está cubierto por tu obra social${s.obra_social ? " (" + escapeHtml(s.obra_social) + ")" : ""}. No tenés que pagar nada. 💚</p>`;
    $("#sub-body").innerHTML = html;
    return;
  }
  html += `<p class="sub-intro">Elegí tu plan:</p><div class="planes">`;
  (s.planes || []).forEach((p) => {
    const meta = PLAN_META[p.id] || { icon: "•", desc: "" };
    const precio = Number(p.precio || 0).toLocaleString("es-AR");
    html += `<div class="plan">
      <div class="plan__head">
        <span class="plan__icon">${meta.icon}</span>
        <div>
          <div class="plan__name">${escapeHtml(p.nombre)}</div>
          <div class="plan__price">$${precio} ${escapeHtml(p.moneda || "ARS")}/mes</div>
        </div>
      </div>
      <p class="plan__desc">${escapeHtml(meta.desc)}</p>
      <button class="btn btn--primary btn--block" data-suscribir="${escapeHtml(p.id)}">Suscribirme</button>
    </div>`;
  });
  html += `</div>`;
  html += `<p class="sub-garantia">🛡️ Garantía: si no te gusta, te devolvemos la plata dentro de los <strong>5 días</strong>.</p>`;
  $("#sub-body").innerHTML = html;
  $$("[data-suscribir]", $("#sub-body")).forEach((b) =>
    b.addEventListener("click", () => suscribir(b.dataset.suscribir))
  );
}

async function suscribir(planId) {
  try {
    const r = await api(`/billing/suscribir?plan=${encodeURIComponent(planId || "app")}`, { method: "POST" });
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

/* ---------- versión del build (fuente única: /health) ---------- */
async function loadVersion() {
  try {
    const h = await api("/health", { auth: false });
    const txt = "v" + (h.version || "?");
    $$(".appver").forEach((el) => (el.textContent = txt));
  } catch { /* sin conexión: no mostramos versión */ }
}
loadVersion();

/* ---------- carrusel de funcionalidades (pantalla de acceso) ---------- */
(function initCarousel() {
  const track = $("#carousel-track");
  const dotsWrap = $("#carousel-dots");
  if (!track || !dotsWrap) return;
  const slides = $$(".carousel__slide", track);
  if (!slides.length) return;
  let idx = 0, timer = null;

  function go(i) {
    idx = (i + slides.length) % slides.length;
    track.style.transform = `translateX(-${idx * 100}%)`;
    dots.forEach((d, j) => d.classList.toggle("is-active", j === idx));
  }
  function restart() { clearInterval(timer); timer = setInterval(() => go(idx + 1), 4500); }

  slides.forEach((_, i) => {
    const d = document.createElement("button");
    d.type = "button";
    d.className = "carousel__dot" + (i === 0 ? " is-active" : "");
    d.setAttribute("aria-label", `Función ${i + 1}`);
    d.addEventListener("click", () => { go(i); restart(); });
    dotsWrap.appendChild(d);
  });
  const dots = $$(".carousel__dot", dotsWrap);

  const car = $("#auth-carousel");
  if (car) {
    car.addEventListener("mouseenter", () => clearInterval(timer));
    car.addEventListener("mouseleave", restart);
  }
  restart();
})();

/* ====================================================================
   ACOMPAÑADO (módulo del paciente): login con código + clave, sesión persistente
==================================================================== */
const PAC_TOKEN_KEY = "sm_paciente_token";
const pacToken = () => localStorage.getItem(PAC_TOKEN_KEY);

$("#ir-paciente-login")?.addEventListener("click", () => show("paciente-login"));
$("#volver-familia")?.addEventListener("click", () => show("auth"));

$("#form-paciente-login")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("[data-error]", e.target);
  err.textContent = "";
  const f = new FormData(e.target);
  try {
    const r = await api("/acompanante/login", {
      method: "POST", auth: false,
      body: { codigo_acceso: (f.get("codigo") || "").trim(), clave: (f.get("clave") || "").trim() },
    });
    localStorage.setItem(PAC_TOKEN_KEY, r.token);
    enterAcompanado(r.nombre);
  } catch (ex) { err.textContent = ex.message || "Código o clave incorrectos"; }
});

async function enterAcompanado(nombrePrecargado) {
  let nombre = nombrePrecargado || "";
  if (!nombre) {
    try { nombre = (await api("/acompanante/me", { bearer: pacToken() })).nombre || ""; }
    catch { localStorage.removeItem(PAC_TOKEN_KEY); show("auth"); return; }
  }
  const primer = (nombre || "").trim().split(/\s+/)[0] || "";
  const hola = $("#acompanado-hola");
  if (hola) hola.textContent = primer ? `Hola, ${primer} 👋` : "Hola 👋";
  cerrarCall();
  show("acompanado");
}

$("#acompanado-salir")?.addEventListener("click", () => {
  if (!confirm("¿Cerrar la sesión?")) return;
  localStorage.removeItem(PAC_TOKEN_KEY);
  show("auth");
});

/* --- la "llamada" (charla con el acompañante) --- */
let callHist = [];
function pintarMensaje(quien, texto) {
  const wrap = $("#call-mensajes");
  if (!wrap || !texto) return;
  const div = document.createElement("div");
  div.className = "call-msg call-msg--" + quien;
  div.textContent = texto;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}
async function enviarCall(texto) {
  if (texto) { pintarMensaje("yo", texto); callHist.push({ role: "user", content: texto }); }
  try {
    const r = await api("/acompanante/chat", {
      method: "POST", bearer: pacToken(),
      body: { mensaje: texto, historial: callHist },
    });
    pintarMensaje("acomp", r.respuesta || "…");
    // Solo acumulamos turnos reales (con texto del usuario) para que el historial
    // con la IA quede balanceado (user → assistant → ...). El saludo inicial no cuenta.
    if (texto) callHist.push({ role: "assistant", content: r.respuesta || "" });
    if (r.configurado === false) {
      const est = $("#call-estado");
      if (est) est.textContent = "Pronto vamos a poder hablar 💛";
    }
  } catch {
    pintarMensaje("acomp", "Perdoná, ahora no puedo. Probá en un ratito 💛");
  }
}
function abrirCall() {
  callHist = [];
  const wrap = $("#call-mensajes"); if (wrap) wrap.innerHTML = "";
  $("#acompanado-home")?.classList.add("is-hidden");
  $("#acompanado-call")?.classList.remove("is-hidden");
  enviarCall("");  // saludo inicial del acompañante
}
function cerrarCall() {
  $("#acompanado-call")?.classList.add("is-hidden");
  $("#acompanado-home")?.classList.remove("is-hidden");
}
$("#btn-hablar")?.addEventListener("click", abrirCall);
$("#call-colgar")?.addEventListener("click", cerrarCall);
$("#form-call")?.addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("#call-input");
  const t = (input.value || "").trim();
  if (!t) return;
  input.value = "";
  enviarCall(t);
});

/* ---------- arranque ---------- */
if (pacToken()) enterAcompanado();
else if (token()) enterApp();
else show("auth");
