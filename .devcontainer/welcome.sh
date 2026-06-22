#!/usr/bin/env bash
# Mensaje de bienvenida al abrir el Codespace. Muestra los comandos clave y
# corre la demo automáticamente para que veas el sistema funcionando.

cat <<'EOF'

============================================================
  SeguimientoMedico — Monitor de Salud Agéntico
============================================================

  Todo se instaló solo. Comandos útiles:

    python scripts/demo_local.py   ->  ver el flujo completo (gratis, sin APIs)
    pytest                         ->  correr los 33 tests
    uvicorn health_monitor.main:app --port 8001   ->  levantar la API

  Corriendo la demo ahora para que veas que funciona...
============================================================

EOF

python scripts/demo_local.py
