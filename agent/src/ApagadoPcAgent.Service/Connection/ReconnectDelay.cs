namespace ApagadoPcAgent.Service.Connection;

/// <summary>Espera creciente entre reintentos: 2 s, 4 s, 8 s... hasta 60 s (§5).</summary>
internal sealed class ReconnectDelay
{
    private static readonly TimeSpan First = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan Max = TimeSpan.FromSeconds(60);

    private TimeSpan _current = First;

    public TimeSpan Next()
    {
        var delay = _current;
        var doubled = _current * 2;
        _current = doubled > Max ? Max : doubled;
        return delay;
    }

    /// <summary>Tras una conexión que funcionó, el siguiente corte vuelve a reintentar rápido.</summary>
    public void Reset() => _current = First;
}
