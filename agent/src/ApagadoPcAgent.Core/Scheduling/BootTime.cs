namespace ApagadoPcAgent.Core.Scheduling;

public interface IBootTimeProvider
{
    DateTime GetBootTimeUtc();
}

/// <summary>Estima el arranque del PC restando el tiempo encendido a la hora actual.</summary>
public sealed class SystemBootTime : IBootTimeProvider
{
    /// <remarks>
    /// En Windows, Environment.TickCount64 (GetTickCount64) SÍ incluye el tiempo que el PC pasó
    /// suspendido, así que esta estimación se mantiene estable al despertar y solo cambia de verdad
    /// cuando el PC arranca de nuevo. Eso es justo lo que necesita D6. No es exacta al milisegundo,
    /// por eso ActionScheduler la compara con holgura.
    /// </remarks>
    public DateTime GetBootTimeUtc() => DateTime.UtcNow - TimeSpan.FromMilliseconds(Environment.TickCount64);
}
