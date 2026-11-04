<#
.SYNOPSIS
    Compila el agente y deja ApagadoPcAgent.exe en .\publish

.DESCRIPTION
    Por defecto usa Docker, asi que no hace falta el SDK de .NET en el PC. Con -Local usa el
    SDK instalado, que es mas rapido si lo tienes.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Local
#>
[CmdletBinding()]
param(
    # Compila con el SDK de .NET instalado en lugar de Docker.
    [switch]$Local,

    # Ejecuta tambien las pruebas de la logica del temporizador y del protocolo.
    [switch]$Test
)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $publishDir = Join-Path $PSScriptRoot 'publish'

    if ($Local) {
        if ($Test) {
            & dotnet test tests/ApagadoPcAgent.Core.Tests/ApagadoPcAgent.Core.Tests.csproj --nologo
            if ($LASTEXITCODE -ne 0) { throw 'Las pruebas fallaron' }
        }
        & dotnet publish src/ApagadoPcAgent.Service/ApagadoPcAgent.Service.csproj -c Release -o $publishDir
        if ($LASTEXITCODE -ne 0) { throw 'La compilacion fallo' }
    } else {
        if ($Test) {
            & docker build --target test -t apagadopc-agent-test .
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo construir la imagen de pruebas' }
            & docker run --rm apagadopc-agent-test
            if ($LASTEXITCODE -ne 0) { throw 'Las pruebas fallaron' }
        }
        & docker build --target export --output $publishDir .
        if ($LASTEXITCODE -ne 0) { throw 'La compilacion fallo' }
    }

    $exe = Join-Path $publishDir 'ApagadoPcAgent.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw "No se genero $exe" }

    $size = [math]::Round((Get-Item -LiteralPath $exe).Length / 1MB, 1)
    Write-Host ''
    Write-Host "Listo: $exe ($size MB)" -ForegroundColor Green
    Write-Host 'Instalalo con, en una consola de Administrador:'
    Write-Host '  .\install.ps1 -ServerUrl wss://tu-dominio/ws/agent -Token (Read-Host Token)'
} finally {
    Pop-Location
}
