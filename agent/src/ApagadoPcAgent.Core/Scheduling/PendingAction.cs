using ApagadoPcAgent.Core.Protocol;

namespace ApagadoPcAgent.Core.Scheduling;

/// <summary>Acción programada tal como vive en memoria.</summary>
public sealed record PendingAction(AgentAction Action, DateTime ExecuteAtUtc)
{
    public int RemainingSeconds(DateTime now)
    {
        var remaining = (ExecuteAtUtc - now).TotalSeconds;
        return remaining <= 0 ? 0 : (int)Math.Ceiling(remaining);
    }

    public AgentPending ToReport(DateTime now) => new(Action, RemainingSeconds(now));
}

/// <summary>
/// Lo que se guarda en disco. <c>BootTimeUtc</c> es lo que permite aplicar D6: si al arrancar
/// el servicio el arranque del PC es otro, el temporizador se descarta.
/// </summary>
public sealed record PersistedTimer(AgentAction Action, DateTime ExecuteAtUtc, DateTime BootTimeUtc);
