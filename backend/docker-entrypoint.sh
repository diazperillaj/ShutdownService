#!/bin/sh
set -e

# Con argumentos se ejecuta ese comando (por ejemplo, la CLI) en lugar del servidor.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Aplica las migraciones pendientes antes de arrancar.
python -m alembic upgrade head

# Un solo worker: la conexión con el PC vive en la memoria del proceso.
# El contenedor solo es accesible desde la red del proxy, por eso se confía en sus cabeceras X-Forwarded-*.
exec uvicorn app.main:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --workers 1 \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" \
    --ws-max-size 65536 \
    --no-server-header
