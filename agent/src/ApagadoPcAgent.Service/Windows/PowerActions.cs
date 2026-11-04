using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using ApagadoPcAgent.Core;
using Microsoft.Extensions.Logging;

namespace ApagadoPcAgent.Service.Windows;

internal sealed record PowerActionResult(bool Ok, string? Error)
{
    public static readonly PowerActionResult Success = new(true, null);

    public static PowerActionResult Failed(string error) => new(false, error);
}

internal interface IPowerActions
{
    Task<PowerActionResult> ExecuteAsync(AgentAction action, CancellationToken cancellationToken);
}

/// <summary>
/// Las cinco acciones sobre el PC (ESPECIFICACION.md §5). Todas son forzadas (D4): las apps se
/// cierran aunque tengan cambios sin guardar.
/// </summary>
[SupportedOSPlatform("windows")]
internal sealed class WindowsPowerActions(ILogger<WindowsPowerActions> logger) : IPowerActions
{
    /// <summary>Ruta absoluta a propósito: un servicio como LocalSystem no debe depender del PATH.</summary>
    private static readonly string ShutdownExe = Path.Combine(Environment.SystemDirectory, "shutdown.exe");

    private static readonly TimeSpan ShutdownExeTimeout = TimeSpan.FromSeconds(15);

    private const uint NoActiveSession = 0xFFFFFFFF;

    [DllImport("powrprof.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetSuspendState(
        [MarshalAs(UnmanagedType.Bool)] bool hibernate,
        [MarshalAs(UnmanagedType.Bool)] bool forceCritical,
        [MarshalAs(UnmanagedType.Bool)] bool disableWakeEvent);

    [DllImport("kernel32.dll")]
    private static extern uint WTSGetActiveConsoleSessionId();

    [DllImport("wtsapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool WTSDisconnectSession(
        IntPtr server,
        uint sessionId,
        [MarshalAs(UnmanagedType.Bool)] bool wait);

    public async Task<PowerActionResult> ExecuteAsync(AgentAction action, CancellationToken cancellationToken)
    {
        logger.LogInformation("Ejecutando la acción {Accion}", action.ToWireName());
        try
        {
            var result = action switch
            {
                AgentAction.Shutdown => await RunShutdownExeAsync("/s /f /t 0", cancellationToken),
                AgentAction.Restart => await RunShutdownExeAsync("/r /f /t 0", cancellationToken),
                // shutdown /h no admite /f y necesita la hibernación activada (powercfg /h on).
                AgentAction.Hibernate => await RunShutdownExeAsync("/h", cancellationToken),
                AgentAction.Sleep => await SuspendAsync(cancellationToken),
                AgentAction.Lock => Disconnect(),
                _ => PowerActionResult.Failed($"Acción no soportada: {action}"),
            };

            if (!result.Ok)
            {
                logger.LogError("La acción {Accion} falló: {Error}", action.ToWireName(), result.Error);
            }
            return result;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "La acción {Accion} lanzó una excepción", action.ToWireName());
            return PowerActionResult.Failed(ex.Message);
        }
    }

    private async Task<PowerActionResult> RunShutdownExeAsync(string arguments, CancellationToken cancellationToken)
    {
        var startInfo = new ProcessStartInfo(ShutdownExe, arguments)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
        };

        using var process = Process.Start(startInfo);
        if (process is null)
        {
            return PowerActionResult.Failed($"No se pudo ejecutar {ShutdownExe}");
        }

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(ShutdownExeTimeout);
        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return PowerActionResult.Failed("shutdown.exe no terminó a tiempo");
        }

        if (process.ExitCode == 0)
        {
            return PowerActionResult.Success;
        }

        var stderr = (await process.StandardError.ReadToEndAsync(cancellationToken)).Trim();
        var detail = string.IsNullOrEmpty(stderr) ? $"código {process.ExitCode}" : stderr;
        return PowerActionResult.Failed($"shutdown.exe {arguments}: {detail}");
    }

    private async Task<PowerActionResult> SuspendAsync(CancellationToken cancellationToken)
    {
        var privilegeError = Privileges.TryEnable(Privileges.Shutdown);
        if (privilegeError is not null)
        {
            return PowerActionResult.Failed($"No se pudo habilitar {Privileges.Shutdown}: {privilegeError}");
        }

        // SetSuspendState no vuelve hasta que el PC despierta, así que va en otro hilo.
        // hibernate: false => suspender. forceCritical: true => no se pregunta a las apps (D4).
        var ok = await Task.Run(() => SetSuspendState(false, true, false), cancellationToken);
        if (!ok)
        {
            var code = Marshal.GetLastWin32Error();
            return PowerActionResult.Failed(
                $"SetSuspendState falló (error {code}: {Marshal.GetPInvokeErrorMessage(code)})");
        }
        return PowerActionResult.Success;
    }

    /// <summary>
    /// LockWorkStation no funciona desde un servicio (necesita una sesión interactiva), así que se
    /// desconecta la sesión de consola activa, que deja el PC en la pantalla de inicio de sesión.
    /// </summary>
    private PowerActionResult Disconnect()
    {
        var sessionId = WTSGetActiveConsoleSessionId();
        if (sessionId == NoActiveSession)
        {
            return PowerActionResult.Failed("No hay ninguna sesión activa que bloquear");
        }

        if (!WTSDisconnectSession(IntPtr.Zero, sessionId, wait: false))
        {
            var code = Marshal.GetLastWin32Error();
            return PowerActionResult.Failed(
                $"WTSDisconnectSession falló (error {code}: {Marshal.GetPInvokeErrorMessage(code)})");
        }
        return PowerActionResult.Success;
    }
}
