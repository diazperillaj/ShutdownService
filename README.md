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

Ejecutar las pruebas del agente (temporizador y protocolo), desde `agent/`:

```bash
docker build --target test -t apagadopc-agent-test .
```

```bash
docker run --rm apagadopc-agent-test
```

## Instalación

### Agente de Windows

Compilar el ejecutable, desde `agent/`. Con Docker no hace falta instalar el SDK de .NET:

```bash
docker build --target export --output publish .
```

Si tienes el SDK, desde PowerShell es más rápido: `.\build.ps1 -Local`

Instalar el servicio en una consola de PowerShell **como Administrador**, desde `agent/`:

```powershell
.\install.ps1 -ServerUrl wss://tu-dominio/ws/agent -Token (Read-Host 'Token')
```

El script copia el `.exe` a `C:\Program Files\ApagadoPC`, escribe la configuración en
`C:\ProgramData\ApagadoPC\appsettings.json` con permisos solo para SYSTEM y Administradores,
registra el servicio `ApagadoPcAgent` como LocalSystem con inicio automático diferido y lo deja
reiniciándose solo si falla.

Para que funcione hibernar, la hibernación tiene que estar activada en el PC:

```powershell
powercfg /h on
```

Los logs quedan en `C:\ProgramData\ApagadoPC\logs` y en el Visor de eventos, con origen
`ApagadoPcAgent`.

Para desinstalarlo: `.\uninstall.ps1` (con `-RemoveData` borra también la configuración y los logs).

### Backend y panel

Pendiente: se documentará al completar el despliegue.

## Licencia

Por definir.
