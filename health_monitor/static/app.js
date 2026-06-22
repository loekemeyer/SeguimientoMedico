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

$("#form-register").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("[data-error]", e.target);
  err.textContent = "";
  const f = new FormData(e.target);
  try {
    const r = await api("/auth/register", {
      method: "POST", auth: false,
      body: { nombre: f.get("nombre"), email: f.get("email"), password: f.get("password") },
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
    <div class="pcard__foot">${estado}<span class="pcard__tag">Ver detalle →</span></div>`;
  el.addEventListener("click", () => openDetail(p.id));
  return el;
}

/* ---------- detalle ---------- */
async function openDetail(id) {
  showPage("detail");
  try {
    const [p, contactos, meds, evos] = await Promise.all([
      api(`/pacientes/${id}`),
      api(`/pacientes/${id}/contactos`).catch(() => []),
      api(`/pacientes/${id}/medicacion`).catch(() => []),
      api(`/pacientes/${id}/evoluciones`).catch(() => []),
    ]);
    renderDetail(p, contactos, meds, evos);
  } catch (e) { toast(e.message, true); }
}

function renderDetail(p, contactos, meds, evos) {
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

  $("#detail-contacts").innerHTML = contactos.length
    ? contactos.map((c) => `<div class="stack-item">👤 <div><div>${escapeHtml(c.nombre || "")}</div><small>${escapeHtml(c.relacion || "")} · ${escapeHtml(c.telefono || "")}</small></div></div>`).join("")
    : `<p class="empty">Sin contactos cargados.</p>`;

  $("#detail-meds").innerHTML = meds.length
    ? meds.map((m) => `<div class="stack-item">💊 <div><div>${escapeHtml(m.nombre || "")}</div><small>${escapeHtml(m.frecuencia || "")}</small></div></div>`).join("")
    : `<p class="empty">Sin medicación cargada.</p>`;

  $("#detail-history").innerHTML = evos.length
    ? evos.map(historyRow).join("")
    : `<p class="empty">Todavía no hay seguimientos registrados.</p>`;
}

function historyRow(e) {
  const fecha = new Date(e.fecha).toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
  const nivel = (e.nivel_alerta || "VERDE").toLowerCase();
  const resumen = e.readout?.resumen || (e.motivos || []).join("; ") || "Sin novedades";
  return `<div class="tl-item">
    <div class="tl-date">${fecha}</div>
    <div><div class="tl-summary">${escapeHtml(resumen)}</div>
      ${(e.motivos || []).length ? `<div class="tl-reasons">${escapeHtml(e.motivos.join(" · "))}</div>` : ""}</div>
    <span class="badge badge--${nivel}">${e.nivel_alerta}</span>
  </div>`;
}

$("#btn-back").addEventListener("click", () => { showPage("list"); loadPatients(); });
$("#btn-add").addEventListener("click", openModal);

/* ---------- modal alta de paciente ---------- */
function openModal() { $("#modal").classList.remove("is-hidden"); }
function closeModal() { $("#modal").classList.add("is-hidden"); $("#form-patient").reset(); $("[data-error]", $("#form-patient")).textContent = ""; }
$$("[data-close]").forEach((el) => el.addEventListener("click", closeModal));

$("#form-patient").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("[data-error]", e.target);
  err.textContent = "";
  const f = new FormData(e.target);
  const patologias = (f.get("patologias") || "").split(",").map((s) => s.trim()).filter(Boolean);
  try {
    const p = await api("/pacientes", {
      method: "POST",
      body: {
        nombre: f.get("nombre"),
        telefono_whatsapp: f.get("telefono_whatsapp"),
        consentimiento_firmado: f.get("consentimiento_firmado") === "on",
        patologias,
        programacion: { llamada_hora: f.get("llamada_hora") || "10:00" },
      },
    });
    // contacto de emergencia (opcional)
    if (f.get("contacto_nombre") && f.get("contacto_telefono")) {
      await api(`/pacientes/${p.id}/contactos`, {
        method: "POST",
        body: { nombre: f.get("contacto_nombre"), telefono: f.get("contacto_telefono"), relacion: "familiar", prioridad: 1 },
      }).catch(() => {});
    }
    closeModal();
    toast("Persona agregada ✅");
    await loadPatients();
  } catch (ex) { err.textContent = ex.message; }
});

/* ---------- util ---------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- arranque ---------- */
if (token()) enterApp(); else show("auth");
