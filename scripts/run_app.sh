#!/usr/bin/env bash
# Lanza la app web (frontend + API) para verla en el navegador.
# Usa SQLite local para no depender de PostgreSQL. Una vez corriendo,
# abrí el puerto 8001 que Codespaces te ofrece ("Open in Browser").
set -e
cd "$(dirname "$0")/.."
export DATABASE_URL="sqlite:///./local.db"
echo "==> App en http://localhost:8001  (abrí el puerto 8001 en Codespaces)"
exec uvicorn health_monitor.main:app --host 0.0.0.0 --port 8001
