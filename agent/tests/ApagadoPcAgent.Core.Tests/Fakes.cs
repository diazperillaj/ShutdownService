using ApagadoPcAgent.Core.Scheduling;

namespace ApagadoPcAgent.Core.Tests;

/// <summary>Reloj manejado a mano: se avanza el de pared y el monótono por separado para simular suspensiones.</summary>
internal sealed class FakeClock(DateTime start) : IClock
{
    public DateTime UtcNow { get; private set; } = start;

    public TimeSpan Monotonic { get; private set; } = TimeSpan.Zero;

    /// <summary>Pasa el tiempo con el PC encendido: los dos relojes avanzan igual.</summary>
    public void Advance(TimeSpan amount)
    {
        UtcNow += amount;
        Monotonic += amount;
    }

    /// <summary>El PC estuvo suspendido: el reloj de pared avanza y el monótono se queda quieto.</summary>
    public void Suspend(TimeSpan amount) => UtcNow += amount;
}

internal sealed class MemoryTimerStore : ITimerStore
{
    public PersistedTimer? Current { get; set; }

    public int SaveCount { get; private set; }

    public int ClearCount { get; private set; }

    public PersistedTimer? Load() => Current;

    public void Save(PersistedTimer timer)
    {
        Current = timer;
        SaveCount++;
    }

    public void Clear()
    {
        Current = null;
        ClearCount++;
    }
}
