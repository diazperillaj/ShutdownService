# ShutdownService

Control remoto de un PC con Windows desde una web propia y desde Alexa: apagar, reiniciar, suspender, hibernar o bloquear, de inmediato o con temporizador.

> 🚧 Proyecto en desarrollo.

## Funcionalidades

- Programar una acción con temporizador (de 1 minuto a 24 horas) o ejecutarla de inmediato.
- Panel web con el estado del PC en tiempo real y una cuenta regresiva.
- Extender o cancelar una acción programada.
- Control por voz con una skill de Alexa (español).
- Historial de acciones con su origen (web o Alexa).
- Funciona sin notificaciones en el PC: todo se consulta desde la web.

| Acción | Programable | Inmediata |
|---|:-:|:-:|
| Apagar | ✅ | ✅ |
| Reiniciar | ✅ | ✅ |
| Suspender | ✅ | ✅ |
| Hibernar | ✅ | ✅ |
| Bloquear | — | ✅ |

## Arquitectura

```
  Navegador            Alexa
      │                  │
      └──── HTTPS ───────┘
              │
   ┌──────── Docker Compose ────────┐
   │  web   React + Tailwind (nginx)│
   │  api   FastAPI                 │
   │  db    PostgreSQL              │
   └───────────────▲────────────────┘
                   │ WebSocket iniciado por el PC
                   │
        Servicio de Windows (.NET)
```

- **El PC inicia la conexión** con el servidor, así que no hay que abrir puertos en la red de casa.
- **El temporizador vive en el PC:** si se pierde la conexión, la acción programada se ejecuta igual.
- **Un solo backend** atiende el panel web, la skill de Alexa y al agente.

## Stack

| Componente | Tecnología |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Base de datos | PostgreSQL |
| Frontend | React, Vite, TypeScript, Tailwind CSS, nginx |
| Agente | .NET (Windows Service) |
| Voz | Alexa Custom Skill |
| Despliegue | Docker Compose detrás de un reverse proxy con HTTPS |

## Estructura

```
backend/    API, autenticación, WebSockets y endpoint de Alexa
frontend/   Panel web
agent/      Servicio de Windows
alexa/      Modelo de interacción de la skill
deploy/     Docker Compose, ejemplo de proxy y variables de entorno
```

## Requisitos

- Un servidor con Docker y Docker Compose.
- Un dominio con HTTPS y un reverse proxy que soporte WebSocket.
- Windows 10/11 en el PC que se va a controlar.
- Opcional: una cuenta de desarrollador de Amazon para la skill de Alexa.

## Configuración

Toda la configuración sensible va en un archivo `.env`, que nunca se sube al repositorio. Usa `deploy/.env.example` como plantilla.

## Seguridad

- Login con usuario y contraseña. Las contraseñas se guardan con hash Argon2id.
- Sesiones del lado del servidor en una cookie `HttpOnly`, `Secure` y `SameSite=Strict`.
- Protección contra fuerza bruta: bloqueo temporal tras varios intentos fallidos.
- El agente se autentica con un token secreto, independiente del login web.
- Las peticiones de Alexa se verifican con la firma de Amazon y se restringen a una cuenta autorizada.
- La base de datos no está expuesta fuera de la red interna de Docker.

## Desarrollo

Todo corre en Docker. Desde la carpeta `deploy/`, con un `.env` creado a partir de `.env.example`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Crear el usuario del panel (solo se permite uno):

```bash
docker compose exec api python -m app.cli create-user <usuario>
```

Generar un valor para `AGENT_TOKEN`:

```bash
docker compose run --rm --no-deps api python -m app.cli gen-token
```

Ejecutar las pruebas del backend:

```bash
docker build --target test -t shutdownservice-api-test ../backend
docker run --rm shutdownservice-api-test
```

## Instalación

Pendiente: se documentará al completar cada componente.

## Licencia

Por definir.
