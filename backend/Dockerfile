# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Pruebas: docker build --target test -t shutdownservice-api-test backend
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY . .
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

# Imagen de producción (etapa por defecto).
FROM base AS runtime
RUN useradd --system --uid 10001 --no-create-home app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini docker-entrypoint.sh ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
ENTRYPOINT ["sh", "./docker-entrypoint.sh"]
