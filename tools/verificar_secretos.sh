#!/usr/bin/env bash
# Busca credenciales en el proyecto. Devuelve 1 si encuentra algo.
set -uo pipefail

PATRONES='sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|[0-9]{4}~[A-Za-z0-9]{40,}|AIza[A-Za-z0-9_-]{30,}|AKIA[0-9A-Z]{16}'

HALLAZGOS=$(grep -rEIn \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.venv \
  --exclude-dir=venv \
  --exclude=".env" \
  --exclude="verificar_secretos.sh" \
  "$PATRONES" . 2>/dev/null || true)

if [ -n "$HALLAZGOS" ]; then
  echo "CREDENCIALES ENCONTRADAS - no hagas commit:"
  echo "$HALLAZGOS" | cut -c1-100
  exit 1
fi

echo "OK: sin credenciales detectadas."
