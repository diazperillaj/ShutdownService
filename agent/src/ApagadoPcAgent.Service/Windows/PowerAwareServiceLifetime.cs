using System.Runtime.Versioning;
using System.ServiceProcess;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Hosting.WindowsServices;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace ApagadoPcAgent.Service.Windows;

/// <summary>
/// El ciclo de vida normal del servicio, más el aviso de energía: el host no expone
/// <c>OnPowerEvent</c>, así que hay que heredar de <see cref="WindowsServiceLifetime"/>
/// y pedir expresamente recibir esos eventos.
/// </summary>
[SupportedOSPlatform("windows")]
internal sealed class PowerAwareServiceLifetime : WindowsServiceLifetime
{
    private readonly ResumeSignal _resume;
    private readonly ILogger<PowerAwareServiceLifetime> _logger;

    public PowerAwareServiceLifetime(
        IHostEnvironment environment,
        IHostApplicationLifetime applicationLifetime,
        ILoggerFactory loggerFactory,
        IOptions<HostOptions> hostOptions,
        IOptions<WindowsServiceLifetimeOptions> windowsServiceOptions,
        ResumeSignal resume)
        : base(environment, applicationLifetime, loggerFactory, hostOptions, windowsServiceOptions)
    {
        // Debe quedar fijado antes de que el servicio arranque; por eso va en el constructor.
        CanHandlePowerEvent = true;
        _resume = resume;
        _logger = loggerFactory.CreateLogger<PowerAwareServiceLifetime>();
    }

    protected override bool OnPowerEvent(PowerBroadcastStatus powerStatus)
    {
        // ResumeAutomatic llega siempre al despertar; ResumeSuspend solo si hay alguien usando el PC.
        if (powerStatus is PowerBroadcastStatus.ResumeAutomatic or PowerBroadcastStatus.ResumeSuspend)
        {
            _logger.LogInformation("El PC despertó ({Estado}); se revisa el temporizador", powerStatus);
            _resume.Signal();
        }

        return base.OnPowerEvent(powerStatus);
    }
}
