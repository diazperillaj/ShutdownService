using System.Collections.Concurrent;
using System.Reflection;
using ApagadoPcAgent.Core;
using ApagadoPcAgent.Core.Protocol;
using ApagadoPcAgent.Core.Scheduling;
using ApagadoPcAgent.Service.Connection;
using ApagadoPcAgent.Service.Windows;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace ApagadoPcAgent.Service;

/// <summary>
/// Junta las dos mitades del agente: el temporizador, que vive aquí y corre pase lo que pase (D1),
/// y el canal con el backend, que se reconecta solo.
/// </summary>
internal sealed class AgentWorker : BackgroundService
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan StateInterval = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan KeepAlive = TimeSpan.FromSeconds(30);

    /// <summary>Margen para que el mensaje salga por la red antes de que el PC se apague.</summary>
    private static readonly TimeSpan FlushDelay = TimeSpan.FromMilliseconds(400);

    private const int MaxQueuedEvents = 20;
    private const int MaxHostnameLength = 64;
    private const int MaxVersionLength = 32;

    private readonly ActionScheduler _scheduler;
    private readonly IPowerActions _actions;
    private readonly IBootTimeProvider _bootTime;
    private readonly ResumeSignal _resume;
    private readonly AgentOptions _options;
    private readonly ILogger<AgentWorker> _logger;

    /// <summary>Eventos que ocurrieron sin conexión; se envían al reconectar para no perder el historial.</summary>
    private readonly ConcurrentQueue<EventMessage> _queuedEvents = new();

    private readonly string _hostname = Truncate(Environment.MachineName, MaxHostnameLength);
    private readonly string _version = Truncate(ResolveVersion(), MaxVersionLength);

    private AgentChannel? _channel;

    public AgentWorker(
        ActionScheduler scheduler,
        IPowerActions actions,
        IBootTimeProvider bootTime,
        ResumeSignal resume,
        IOptions<AgentOptions> options,
        ILogger<AgentWorker> logger)
    {
        _scheduler = scheduler;
        _actions = actions;
        _bootTime = bootTime;
        _resume = resume;
        _options = options.Value;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Agente {Version} iniciando en {Hostname}", _version, _hostname);
        RestoreTimer();

        // Las dos mitades corren a la vez: si se cae la red, el temporizador sigue su cuenta.
        await Task.WhenAll(
            RunSchedulerLoopAsync(stoppingToken),
            RunConnectionLoopAsync(stoppingToken));
    }

    /// <summary>Arranque del servicio: aplica D6 y recupera lo que siga vigente.</summary>
    private void RestoreTimer()
    {
        var outcome = _scheduler.Restore(_bootTime.GetBootTimeUtc());
        switch (outcome.Event)
        {
            case SchedulerEvent.Restored:
                _logger.LogInformation(
                    "Temporizador recuperado: {Accion} en {Segundos} s",
                    outcome.Action!.Value.ToWireName(),
                    _scheduler.Pending!.RemainingSeconds(DateTime.UtcNow));
                break;

            case SchedulerEvent.Discard:
                _logger.LogInformation(
                    "Temporizador descartado ({Razon}): {Accion}",
                    outcome.Reason,
                    outcome.Action!.Value.ToWireName());
                QueueEvent(new EventMessage(EventMessage.Discarded, outcome.Action.Value, outcome.Reason));
                break;
        }
    }

    // --- Temporizador ---

    private async Task RunSchedulerLoopAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            bool resumed;
            try
            {
                // La espera hace de pausa del sondeo y de aviso de despertar, a la vez.
                resumed = await _resume.WaitAsync(PollInterval, stoppingToken);
            }
            catch (OperationCanceledException)
            {
                return;
            }

            var outcome = _scheduler.Poll();
            if (resumed && outcome.Event == SchedulerEvent.None)
            {
                _logger.LogDebug("El PC despertó sin nada pendiente que revisar");
            }

            try
            {
                switch (outcome.Event)
                {
                    case SchedulerEvent.Execute:
                        await ExecuteScheduledActionAsync(outcome.Action!.Value, stoppingToken);
                        break;

                    case SchedulerEvent.Discard:
                        _logger.LogInformation(
                            "Acción descartada ({Razon}): {Accion}",
                            outcome.Reason,
                            outcome.Action!.Value.ToWireName());
                        await ReportEventAsync(
                            new EventMessage(EventMessage.Discarded, outcome.Action.Value, outcome.Reason),
                            stoppingToken);
                        await TrySendStateAsync(stoppingToken);
                        break;
                }
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }
    }

    private async Task ExecuteScheduledActionAsync(AgentAction action, CancellationToken stoppingToken)
    {
        // Se olvida del disco ANTES de actuar: si el apagado queda a medias, la acción no se repite.
        _scheduler.Consume();
        await ReportEventAsync(new EventMessage(EventMessage.Executing, action, null), stoppingToken);
        await Task.Delay(FlushDelay, stoppingToken);

        var result = await _actions.ExecuteAsync(action, stoppingToken);
        if (!result.Ok)
        {
            // El protocolo no tiene forma de informar que una acción programada falló; queda en
            // el log local y el panel verá que ya no hay nada pendiente.
            _logger.LogError("La acción programada {Accion} falló: {Error}", action.ToWireName(), result.Error);
        }
        await TrySendStateAsync(stoppingToken);
    }

    // --- Canal con el backend ---

    private async Task RunConnectionLoopAsync(CancellationToken stoppingToken)
    {
        var url = _options.ResolveUri();
        var backoff = new ReconnectDelay();

        while (!stoppingToken.IsCancellationRequested)
        {
            await ConnectOnceAsync(url, backoff, stoppingToken);

            if (stoppingToken.IsCancellationRequested)
            {
                return;
            }

            var delay = backoff.Next();
            _logger.LogInformation("Se reintenta la conexión en {Segundos} s", (int)delay.TotalSeconds);
            try
            {
                await Task.Delay(delay, stoppingToken);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }
    }

    private async Task ConnectOnceAsync(Uri url, ReconnectDelay backoff, CancellationToken stoppingToken)
    {
        try
        {
            await using var channel = await AgentChannel.ConnectAsync(
                url, _options.Token, KeepAlive, stoppingToken);

            _channel = channel;
            backoff.Reset();
            _logger.LogInformation("Conectado a {Url}", url);

            await channel.SendAsync(
                new HelloMessage(_hostname, _version, _scheduler.Report()), stoppingToken);
            await FlushQueuedEventsAsync(channel, stoppingToken);
            await PumpAsync(channel, stoppingToken);

            _logger.LogWarning("El servidor cerró la conexión");
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Sin conexión con el servidor: {Mensaje}", ex.Message);
        }
        finally
        {
            _channel = null;
        }
    }

    /// <summary>Lee comandos mientras, en paralelo, informa el estado cada 60 s (D3).</summary>
    private async Task PumpAsync(AgentChannel channel, CancellationToken stoppingToken)
    {
        using var pump = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        var heartbeat = SendStatePeriodicallyAsync(channel, pump.Token);
        try
        {
            while (true)
            {
                var text = await channel.ReceiveAsync(stoppingToken);
                if (text is null)
                {
                    return;
                }

                var command = ProtocolJson.TryDeserialize<CommandMessage>(text);
                if (command is null || command.Type != CommandMessage.TypeName || string.IsNullOrEmpty(command.Id))
                {
                    _logger.LogWarning("Mensaje del servidor ignorado: {Texto}", Truncate(text, 200));
                    continue;
                }

                await HandleCommandAsync(channel, command, stoppingToken);
            }
        }
        finally
        {
            await pump.CancelAsync();
            try
            {
                await heartbeat;
            }
            catch (OperationCanceledException)
            {
            }
        }
    }

    private async Task SendStatePeriodicallyAsync(AgentChannel channel, CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            await Task.Delay(StateInterval, cancellationToken);
            await channel.SendAsync(new StateMessage(_scheduler.Report()), cancellationToken);
        }
    }

    private async Task HandleCommandAsync(
        AgentChannel channel, CommandMessage command, CancellationToken stoppingToken)
    {
        var ok = true;
        string? error = null;
        AgentAction? immediate = null;

        if (command.Action == AgentActions.CancelCommand)
        {
            var had = _scheduler.Cancel();
            _logger.LogInformation(had ? "Programación cancelada" : "No había nada programado que cancelar");
        }
        else if (!AgentActions.TryParse(command.Action, out var action))
        {
            ok = false;
            error = $"Acción desconocida: '{command.Action}'";
        }
        else if (command.DelaySeconds is null or 0)
        {
            immediate = action;
        }
        else if (!action.IsProgrammable())
        {
            ok = false;
            error = $"La acción '{action.ToWireName()}' solo puede ejecutarse de inmediato";
        }
        else
        {
            var pending = _scheduler.Schedule(action, command.DelaySeconds.Value, _bootTime.GetBootTimeUtc());
            _logger.LogInformation(
                "Programado: {Accion} en {Segundos} s", action.ToWireName(), command.DelaySeconds.Value);
            _ = pending;
        }

        if (error is not null)
        {
            _logger.LogWarning("Comando rechazado: {Error}", error);
        }

        // Bloquear es la única acción inmediata que deja vivo al proceso, así que se ejecuta antes
        // de confirmar y el panel recibe el resultado de verdad.
        if (immediate == AgentAction.Lock)
        {
            var result = await _actions.ExecuteAsync(AgentAction.Lock, stoppingToken);
            immediate = null;
            ok = result.Ok;
            error = result.Error;
        }

        await channel.SendAsync(new AckMessage(command.Id!, ok, error, _scheduler.Report()), stoppingToken);

        // Las demás acciones inmediatas matan o congelan el proceso: si se ejecutaran antes del ack,
        // el backend respondería 504 aunque todo hubiera ido bien. Van detrás, y sin esperar aquí
        // para no bloquear la lectura de mensajes.
        if (immediate is not null)
        {
            RunDetached(immediate.Value);
        }
    }

    /// <summary>
    /// Ejecuta sin esperar y a propósito sin token: la acción la pidió el usuario y debe ocurrir
    /// aunque el servicio se esté deteniendo justo en ese momento.
    /// </summary>
    private void RunDetached(AgentAction action)
    {
        _ = Task.Run(async () =>
        {
            try
            {
                await Task.Delay(FlushDelay, CancellationToken.None);
                await _actions.ExecuteAsync(action, CancellationToken.None);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Falló la acción inmediata {Accion}", action.ToWireName());
            }
        });
    }

    // --- Envíos ---

    /// <summary>Envía el evento; si no hay conexión, lo guarda para el reencuentro.</summary>
    private async Task ReportEventAsync(EventMessage message, CancellationToken cancellationToken)
    {
        var channel = _channel;
        if (channel is null || !channel.IsOpen)
        {
            QueueEvent(message);
            return;
        }

        try
        {
            await channel.SendAsync(message, cancellationToken);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            _logger.LogWarning("No se pudo avisar al servidor: {Mensaje}", ex.Message);
            QueueEvent(message);
        }
    }

    /// <summary>El estado no se guarda si no hay conexión: el hello del reencuentro ya lo lleva.</summary>
    private async Task TrySendStateAsync(CancellationToken cancellationToken)
    {
        var channel = _channel;
        if (channel is null || !channel.IsOpen)
        {
            return;
        }

        try
        {
            await channel.SendAsync(new StateMessage(_scheduler.Report()), cancellationToken);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            _logger.LogDebug("No se pudo informar el estado: {Mensaje}", ex.Message);
        }
    }

    private void QueueEvent(EventMessage message)
    {
        _queuedEvents.Enqueue(message);
        while (_queuedEvents.Count > MaxQueuedEvents && _queuedEvents.TryDequeue(out _))
        {
        }
    }

    private async Task FlushQueuedEventsAsync(AgentChannel channel, CancellationToken cancellationToken)
    {
        while (_queuedEvents.TryDequeue(out var message))
        {
            await channel.SendAsync(message, cancellationToken);
        }
    }

    private static string ResolveVersion()
    {
        var informational = Assembly.GetExecutingAssembly()
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
        // Quita el sufijo del commit que añade el SDK (1.0.0+abc123).
        return informational?.Split('+')[0] ?? "1.0.0";
    }

    private static string Truncate(string value, int maxLength)
        => value.Length <= maxLength ? value : value[..maxLength];
}
