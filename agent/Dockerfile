# syntax=docker/dockerfile:1

# Compila el agente sin instalar el SDK de .NET en el PC (ESPECIFICACION.md §5).
#
#   Publicar el .exe:  docker build --target export --output publish .
#   Pruebas:           docker build --target test -t apagadopc-agent-test .
#                      docker run --rm apagadopc-agent-test
#
# El .exe sale autocontenido para win-x64: en el PC no hace falta ningun runtime.

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS restore
WORKDIR /src
COPY Directory.Build.props ./
COPY src/ApagadoPcAgent.Core/ApagadoPcAgent.Core.csproj src/ApagadoPcAgent.Core/
COPY src/ApagadoPcAgent.Service/ApagadoPcAgent.Service.csproj src/ApagadoPcAgent.Service/
RUN dotnet restore src/ApagadoPcAgent.Service/ApagadoPcAgent.Service.csproj

FROM restore AS build
COPY src/ src/
RUN dotnet publish src/ApagadoPcAgent.Service/ApagadoPcAgent.Service.csproj \
    -c Release -o /publish

# Pruebas de la logica neutral (temporizador y protocolo); corren en Linux.
FROM restore AS test
COPY tests/ApagadoPcAgent.Core.Tests/ApagadoPcAgent.Core.Tests.csproj tests/ApagadoPcAgent.Core.Tests/
RUN dotnet restore tests/ApagadoPcAgent.Core.Tests/ApagadoPcAgent.Core.Tests.csproj
COPY src/ src/
COPY tests/ tests/
CMD ["dotnet", "test", "tests/ApagadoPcAgent.Core.Tests/ApagadoPcAgent.Core.Tests.csproj", "--nologo"]

# Etapa de salida: solo el ejecutable, para `docker build --output`.
FROM scratch AS export
COPY --from=build /publish/ApagadoPcAgent.exe /
