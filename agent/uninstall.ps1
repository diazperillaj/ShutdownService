<#
.SYNOPSIS
    Quita el servicio ApagadoPcAgent de este PC.

.DESCRIPTION
    Detiene y borra el servicio y elimina el ejecutable. La configuracion y los logs de
    C:\ProgramData\ApagadoPC se conservan salvo que se pase -RemoveData.

.EXAMPLE
    .\uninstall.ps1 -RemoveData
#>
[CmdletBinding()]
param(
    # Borra tambien la configuracion, el temporizador guardado y los logs.
    [switch]$RemoveData,

    [string]$InstallDir = (Join-Path $env:ProgramFiles 'ApagadoPC')
)

$ErrorActionPreference = 'Stop'

$serviceName = 'ApagadoPcAgent'
$dataDir = Join-Path $env:ProgramData 'ApagadoPC'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Hay que ejecutar este script como Administrador.'
}

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne 'Stopped') {
        Write-Host 'Deteniendo el servicio'
        Stop-Service -Name $serviceName -Force
        $service.WaitForStatus('Stopped', '00:00:30')
    }
    & sc.exe delete $serviceName | Out-Null
    Write-Host "Servicio $serviceName eliminado"
} else {
    Write-Host "El servicio $serviceName no estaba instalado"
}

if (Test-Path -LiteralPath $InstallDir) {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
    Write-Host "Eliminado $InstallDir"
}

if ($RemoveData) {
    if (Test-Path -LiteralPath $dataDir) {
        Remove-Item -LiteralPath $dataDir -Recurse -Force
        Write-Host "Eliminado $dataDir"
    }
} elseif (Test-Path -LiteralPath $dataDir) {
    Write-Host "Se conserva $dataDir (usa -RemoveData para borrarlo)"
}
