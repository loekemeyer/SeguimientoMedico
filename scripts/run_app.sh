#!/usr/bin/env bash
# Lanza la app web (frontend + API) para verla en el navegador.
#
# Usa SQLite local + secretos de desarrollo persistentes: NO depende de PostgreSQL
# ni de configurar claves a mano, así registrarte, crear pacientes (que cifran el
# teléfono) y la obra social funcionan de una. Una vez corriendo, abrí el puerto
# 8001 que Codespaces te ofrece ("Open in Browser").
set -e
cd "$(dirname "$0")/.."

# Secretos de desarrollo: se generan UNA sola vez y se reutilizan. Si se regeneraran
# en cada arranque, los datos cifrados de la corrida anterior quedarían ilegibles.
SECRETS_FILE=".dev_secrets.env"
if [ ! -f "$SECRETS_FILE" ]; then
  echo "==> Generando secretos de desarrollo en $SECRETS_FILE (solo la primera vez)"
  python - <<'PY' > "$SECRETS_FILE"
import secrets

from shared.security import generate_key

print(f"ENCRYPTION_KEY={generate_key()}")
print(f"JWT_SECRET={secrets.token_urlsafe(32)}")
PY
fi
set -a; . "$SECRETS_FILE"; set +a

export DATABASE_URL="${DATABASE_URL:-sqlite:///./local.db}"
echo "==> App en http://localhost:8001  (abrí el puerto 8001 en Codespaces)"
exec uvicorn health_monitor.main:app --host 0.0.0.0 --port 8001
