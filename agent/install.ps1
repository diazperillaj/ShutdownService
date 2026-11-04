<#
.SYNOPSIS
    Instala (o reinstala) el servicio ApagadoPcAgent en este PC.

.DESCRIPTION
    Copia el ejecutable, crea la configuracion en C:\ProgramData\ApagadoPC con una ACL que solo
    deja entrar a SYSTEM y Administradores, registra el servicio como LocalSystem con inicio
    automatico diferido y configura el reinicio automatico si falla.

    Hay que ejecutarlo en una consola de PowerShell abierta como Administrador.

.EXAMPLE
    .\install.ps1 -ServerUrl wss://apagadopc.duckdns.org/ws/agent -Token (Read-Host 'Token')
#>
[CmdletBinding()]
param(
    # URL del canal del agente en el servidor.
    [Parameter(Mandatory = $true)]
    [string]$ServerUrl,

    # Debe coincidir con AGENT_TOKEN del servidor.
    [Parameter(Mandatory = $true)]
    [string]$Token,

    # Ejecutable publicado (ver build.ps1).
    [string]$SourceExe = (Join-Path $PSScriptRoot 'publish\ApagadoPcAgent.exe'),

    [string]$InstallDir = (Join-Path $env:ProgramFiles 'ApagadoPC')
)

$ErrorActionPreference = 'Stop'

$serviceName = 'ApagadoPcAgent'
$displayName = 'ApagadoPC Agent'
$dataDir = Join-Path $env:ProgramData 'ApagadoPC'
$configFile = Join-Path $dataDir 'appsettings.json'
$targetExe = Join-Path $InstallDir 'ApagadoPcAgent.exe'

# --- Comprobaciones ---

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Hay que ejecutar este script como Administrador.'
}

if (-not (Test-Path -LiteralPath $SourceExe)) {
    throw "No se encontro el ejecutable '$SourceExe'. Compilalo primero con .\build.ps1"
}

if ($Token.Length -lt 32) {
    throw 'El token debe tener al menos 32 caracteres. Generalo en el servidor con: python -m app.cli gen-token'
}

if ($ServerUrl -notmatch '^(wss|ws|https|http)://') {
    throw "ServerUrl debe empezar por wss:// (o ws:// en pruebas locales): '$ServerUrl'"
}

if ($ServerUrl -match '^(ws|http)://' -and $ServerUrl -notmatch '^(ws|http)://(localhost|127\.0\.0\.1)') {
    Write-Warning 'Estas usando una URL sin cifrar hacia un equipo remoto: el token viajaria en claro.'
}

# --- Servicio existente ---

$existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Deteniendo el servicio existente..."
    if ($existing.Status -ne 'Stopped') {
        Stop-Service -Name $serviceName -Force
        $existing.WaitForStatus('Stopped', '00:00:30')
    }
    & sc.exe delete $serviceName | Out-Null
    # sc.exe delete vuelve antes de que el servicio desaparezca del registro.
    Start-Sleep -Seconds 2
}

# --- Ejecutable ---

Write-Host "Copiando el ejecutable a $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -LiteralPath $SourceExe -Destination $targetExe -Force

# --- Configuracion y permisos ---

Write-Host "Preparando $dataDir"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dataDir 'logs') | Out-Null

# SID conocidos en lugar de nombres: asi funciona en cualquier idioma de Windows.
$system = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
$administrators = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')

$acl = Get-Acl -LiteralPath $dataDir
# Corta la herencia y no copia las reglas heredadas: dentro solo quedan las dos que se anaden.
$acl.SetAccessRuleProtection($true, $false)
foreach ($account in @($system, $administrators)) {
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
        $account,
        [Security.AccessControl.FileSystemRights]::FullControl,
        @([Security.AccessControl.InheritanceFlags]::ContainerInherit,
          [Security.AccessControl.InheritanceFlags]::ObjectInherit),
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow)))
}
$acl.SetOwner($administrators)
Set-Acl -LiteralPath $dataDir -AclObject $acl

Write-Host "Escribiendo $configFile"
$config = [ordered]@{ ServerUrl = $ServerUrl; Token = $Token }
$json = $config | ConvertTo-Json
# Sin BOM: el lector de configuracion de .NET lo acepta igual, pero asi el archivo queda limpio.
[IO.File]::WriteAllText($configFile, $json, (New-Object Text.UTF8Encoding($false)))

# El archivo hereda la ACL del directorio, pero se vuelve a aplicar por si ya existia.
$fileAcl = Get-Acl -LiteralPath $configFile
$fileAcl.SetAccessRuleProtection($true, $false)
foreach ($account in @($system, $administrators)) {
    $fileAcl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
        $account,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow)))
}
Set-Acl -LiteralPath $configFile -AclObject $fileAcl

# --- Registro del servicio ---

Write-Host "Registrando el servicio $serviceName"
# sc.exe espera un espacio DESPUES del '=', por eso cada 'clave=' va como argumento aparte.
$create = @(
    'create', $serviceName,
    'binPath=', $targetExe,
    'start=', 'delayed-auto',
    'obj=', 'LocalSystem',
    'DisplayName=', $displayName
)
& sc.exe $create | Out-Null
if ($LASTEXITCODE -ne 0) { throw "sc.exe create fallo con el codigo $LASTEXITCODE" }

& sc.exe description $serviceName 'Ejecuta las acciones de energia pedidas desde el panel de ApagadoPC.' | Out-Null

# Si el proceso se cae, Windows lo reinicia a los 5 s, 10 s y 30 s; el contador se reinicia cada dia.
& sc.exe failure $serviceName 'reset=' '86400' 'actions=' 'restart/5000/restart/10000/restart/30000' | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Warning "No se pudo configurar el reinicio automatico (codigo $LASTEXITCODE)" }

Write-Host 'Iniciando el servicio'
Start-Service -Name $serviceName

$service = Get-Service -Name $serviceName
Write-Host ''
Write-Host "Listo: $serviceName esta $($service.Status)." -ForegroundColor Green
Write-Host "Logs: $(Join-Path $dataDir 'logs')"
Write-Host "Tambien en el Visor de eventos, en Registros de Windows > Aplicacion, origen $serviceName."
