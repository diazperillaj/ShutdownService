using System.Diagnostics;

namespace ApagadoPcAgent.Core.Scheduling;

public interface IClock
{
    DateTime UtcNow { get; }

    /// <summary>
    /// Reloj monótono que NO avanza mientras el PC está suspendido. Comparar su avance con el de
    /// <see cref="UtcNow"/> revela cuánto tiempo estuvo dormido el PC, que es el respaldo del
    /// evento de energía para la regla D5.
    /// </summary>
    TimeSpan Monotonic { get; }
}

public sealed class SystemClock : IClock
{
    // Stopwatch usa el contador de alto rendimiento, que se congela durante la suspensión;
    // DateTime.UtcNow sigue el reloj de pared, que no.
    private readonly Stopwatch _monotonic = Stopwatch.StartNew();

    public DateTime UtcNow => DateTime.UtcNow;

    public TimeSpan Monotonic => _monotonic.Elapsed;
}
