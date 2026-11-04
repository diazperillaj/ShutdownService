namespace ApagadoPcAgent.Core;

/// <summary>Las cinco acciones que el agente sabe ejecutar en el PC.</summary>
public enum AgentAction
{
    Shutdown,
    Restart,
    Sleep,
    Hibernate,
    Lock,
}

public static class AgentActions
{
    /// <summary>Comando del protocolo para anular lo programado; no es una acción del PC.</summary>
    public const string CancelCommand = "cancel";

    /// <summary>Bloquear solo existe como acción inmediata (D: tabla de acciones).</summary>
    public static bool IsProgrammable(this AgentAction action) => action != AgentAction.Lock;

    /// <summary>
    /// Nombre con el que viaja la acción en el protocolo. Se escribe a mano en lugar de derivarlo
    /// del enum para que renombrar un miembro no cambie en silencio lo que entiende el backend.
    /// </summary>
    public static string ToWireName(this AgentAction action) => action switch
    {
        AgentAction.Shutdown => "shutdown",
        AgentAction.Restart => "restart",
        AgentAction.Sleep => "sleep",
        AgentAction.Hibernate => "hibernate",
        AgentAction.Lock => "lock",
        _ => throw new ArgumentOutOfRangeException(nameof(action), action, "Acción desconocida"),
    };

    public static bool TryParse(string? wireName, out AgentAction action)
    {
        switch (wireName)
        {
            case "shutdown": action = AgentAction.Shutdown; return true;
            case "restart": action = AgentAction.Restart; return true;
            case "sleep": action = AgentAction.Sleep; return true;
            case "hibernate": action = AgentAction.Hibernate; return true;
            case "lock": action = AgentAction.Lock; return true;
            default: action = default; return false;
        }
    }
}
