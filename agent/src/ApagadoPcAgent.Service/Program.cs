using ApagadoPcAgent.Core.Scheduling;
using ApagadoPcAgent.Service;
using ApagadoPcAgent.Service.Logging;
using ApagadoPcAgent.Service.Windows;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Hosting.WindowsServices;
using Microsoft.Extensions.Logging;

var builder = Host.CreateApplicationBuilder(args);

// La configuración vive fuera del ejecutable, en C:\ProgramData\ApagadoPC\appsettings.json,
// con una ACL que solo deja entrar a SYSTEM y Administradores (la fija install.ps1).
// Opcional a propósito: de que estén ServerUrl y Token se encarga la validación de
// AgentOptions, que da un mensaje claro, y así el .exe se puede probar desde una consola
// pasándolos como --ServerUrl=... --Token=... sin tocar ProgramData.
builder.Configuration.AddJsonFile(AgentPaths.ConfigFile, optional: true, reloadOnChange: false);

builder.Services.AddWindowsService(options => options.ServiceName = AgentPaths.ServiceName);

builder.Logging.AddFile(AgentPaths.LogDirectory);
if (!WindowsServiceHelpers.IsWindowsService())
{
    // Ejecutado a mano desde una consola, para probar.
    builder.Logging.AddSimpleConsole(options => options.SingleLine = true);
}

builder.Services
    .AddOptions<AgentOptions>()
    .Bind(builder.Configuration)
    .ValidateDataAnnotations()
    .ValidateOnStart();

builder.Services.AddSingleton<ResumeSignal>();
builder.Services.AddSingleton<IBootTimeProvider, SystemBootTime>();
builder.Services.AddSingleton<IClock, SystemClock>();
builder.Services.AddSingleton<IPowerActions, WindowsPowerActions>();

builder.Services.AddSingleton<ITimerStore>(provider =>
{
    var logger = provider.GetRequiredService<ILogger<FileTimerStore>>();
    return new FileTimerStore(
        AgentPaths.TimerFile,
        (message, exception) => logger.LogError(exception, "{Mensaje}", message));
});

builder.Services.AddSingleton(provider => new ActionScheduler(
    provider.GetRequiredService<ITimerStore>(),
    provider.GetRequiredService<IClock>()));

builder.Services.AddHostedService<AgentWorker>();

// Solo como servicio: WindowsServiceLifetime no funciona si no hay un servicio detrás, y al
// ejecutar el .exe a mano conviene dejar el ciclo de vida de consola. Sin el evento de energía,
// el respaldo del salto de reloj en ActionScheduler cubre igual la regla D5.
if (WindowsServiceHelpers.IsWindowsService())
{
    builder.Services.Replace(
        ServiceDescriptor.Singleton<IHostLifetime, PowerAwareServiceLifetime>());
}

var host = builder.Build();
await host.RunAsync();
