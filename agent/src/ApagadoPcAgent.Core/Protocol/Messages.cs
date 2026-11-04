namespace ApagadoPcAgent.Core.Protocol;

/// <summary>
/// Mensajes JSON del canal con el backend (ESPECIFICACION.md §4.3).
/// Los nombres viajan en camelCase; ver <see cref="ProtocolJson"/>.
/// </summary>

// --- Estado que el agente informa ---

/// <summary>Se informan los segundos que faltan, no una hora: los relojes no tienen que coincidir (D2).</summary>
public sealed record AgentPending(AgentAction Action, int RemainingSeconds);

/// <summary><c>Pending</c> en null significa que no hay nada programado.</summary>
public sealed record AgentStateReport(AgentPending? Pending)
{
    public static readonly AgentStateReport Idle = new((AgentPending?)null);
}

// --- Agente → servidor ---

public sealed record HelloMessage(string Hostname, string Version, AgentStateReport State)
{
    public string Type => "hello";
}

public sealed record AckMessage(string Id, bool Ok, string? Error, AgentStateReport State)
{
    public string Type => "ack";
}

public sealed record StateMessage(AgentStateReport State)
{
    public string Type => "state";
}

public sealed record EventMessage(string Event, AgentAction Action, string? Reason)
{
    public const string Executing = "executing";
    public const string Discarded = "discarded";

    public string Type => "event";
}

// --- Servidor → agente ---

/// <summary>
/// Se lee con todo opcional a propósito: un mensaje incompleto o desconocido se descarta
/// en <c>AgentWorker</c> en lugar de romper la conexión.
/// </summary>
public sealed record CommandMessage
{
    public string? Type { get; init; }
    public string? Id { get; init; }
    public string? Action { get; init; }
    public int? DelaySeconds { get; init; }

    public const string TypeName = "command";
}
