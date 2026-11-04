#!/bin/sh
set -e

# Con argumentos se ejecuta ese comando (por ejemplo, la CLI) en lugar del servidor.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Aplica las migraciones pendientes antes de arrancar.
python -m alembic upgrade head

# Un solo worker: la conexión con el PC vive en la memoria del proceso.
#
# Solo se confía en las cabeceras X-Forwarded-* del proxy: FORWARDED_ALLOW_IPS debe contener
# la IP o la subred de Caddy (ver deploy/.env.example). Sin configurar no se confía en nadie,
# así que la IP que ve la app es la del proxy: el límite de intentos por IP se vuelve global
# en lugar de poder falsearse con una cabecera.
#
# Ping cada 30 s en los WebSockets (agente y panel) para detectar conexiones muertas.
exec uvicorn app.main:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --workers 1 \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --ws-ping-interval 30 --ws-ping-timeout 10 \
    --ws-max-size 65536 \
    --no-server-header
