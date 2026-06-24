/* Service worker — guarda el "shell" estático para que la app sea instalable y
   funcione offline, pero con estrategia "RED PRIMERO": cuando hay conexión sirve
   siempre lo último (así los cambios se ven al toque), y usa el cache solo como
   respaldo si no hay red. NO intercepta la API (ni POST ni GET de datos): esos van
   siempre a la red, así nunca se sirven datos clínicos viejos del cache. */
const CACHE = "sm-shell-v3";
const SHELL = ["/", "/index.html", "/app.js", "/styles.css", "/manifest.webmanifest",
  "/icon.svg", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function esShell(url) {
  if (SHELL.includes(url.pathname)) return true;
  return [".css", ".js", ".svg", ".png", ".webmanifest"].some((ext) => url.pathname.endsWith(ext));
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;                  // la API que escribe nunca se toca
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // recursos externos: a la red
  if (!esShell(url)) return;                          // datos de la API: a la red, sin cache
  // Shell estático: RED PRIMERO. Si hay conexión, sirvo lo último y refresco el
  // cache; si no hay red, caigo al cache guardado (offline).
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200) {
          const copia = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copia));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
