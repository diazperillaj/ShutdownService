using ApagadoPcAgent.Core.Protocol;

namespace ApagadoPcAgent.Core.Scheduling;

public enum SchedulerEvent
{
    /// <summary>Nada que hacer.</summary>
    None,

    /// <summary>Se recuperó del disco un temporizador todavía vigente.</summary>
    Restored,

    /// <summary>Venció el plazo: hay que ejecutar la acción.</summary>
    Execute,

    /// <summary>El temporizador se tira sin ejecutar nada (D5 o D6).</summary>
    Discard,
}

/// <summary>Razones de un descarte. Viajan en el campo <c>reason</c> del evento.</summary>
public static class DiscardReasons
{
    /// <summary>El PC se encendió o reinició (D6).</summary>
    public const string Boot = "boot";

    /// <summary>El PC despertó con la hora ya vencida (D5).</summary>
    public const string Resume = "resume";

    /// <summary>El plazo venció mientras el servicio estaba detenido, sin reiniciar el PC.</summary>
    public const string Expired = "expired";
}

public sealed record SchedulerOutcome(SchedulerEvent Event, AgentAction? Action = null, string? Reason = null)
{
    public static readonly SchedulerOutcome None = new(SchedulerEvent.None);
}

/// <summary>
/// El temporizador vive aquí, en el PC (D1): el backend solo dice "acción X en N segundos".
/// Esta clase no toca el PC ni la red; decide y devuelve qué hacer, para poder probarla sola.
/// </summary>
public sealed class ActionScheduler(ITimerStore store, IClock clock, SchedulerTuning? tuning = null)
{
    private readonly ITimerStore _store = store;
    private readonly IClock _clock = clock;
    private readonly SchedulerTuning _tuning = tuning ?? SchedulerTuning.Default;

    // Última pareja (reloj de pared, reloj monótono) vista, para detectar suspensiones.
    // Se siembra al construir: si no, una suspensión entre programar y el primer sondeo
    // pasaría desapercibida y el descarte se atribuiría al motivo equivocado.
    private DateTime _lastWallClock = clock.UtcNow;
    private TimeSpan _lastMonotonic = clock.Monotonic;

    public PendingAction? Pending { get; private set; }

    /// <summary>
    /// Arranque del servicio: aplica D6 y restaura lo que siga vigente.
    /// <paramref name="bootTimeUtc"/> es el arranque actual del PC.
    /// </summary>
    public SchedulerOutcome Restore(DateTime bootTimeUtc)
    {
        MarkClocks();
        var saved = _store.Load();
        if (saved is null)
        {
            return SchedulerOutcome.None;
        }

        // D6: si el PC se encendió o reinició desde que se guardó, no se hereda nada.
        if (!SameBoot(saved.BootTimeUtc, bootTimeUtc))
        {
            _store.Clear();
            return new SchedulerOutcome(SchedulerEvent.Discard, saved.Action, DiscardReasons.Boot);
        }

        // Mismo arranque pero el plazo ya pasó mientras el servicio no corría: tampoco se ejecuta.
        if (saved.ExecuteAtUtc <= _clock.UtcNow)
        {
            _store.Clear();
            return new SchedulerOutcome(SchedulerEvent.Discard, saved.Action, DiscardReasons.Expired);
        }

        Pending = new PendingAction(saved.Action, saved.ExecuteAtUtc);
        return new SchedulerOutcome(SchedulerEvent.Restored, saved.Action);
    }

    /// <summary>Programa una acción. Una nueva reemplaza a la anterior (D8).</summary>
    public PendingAction Schedule(AgentAction action, int delaySeconds, DateTime bootTimeUtc)
    {
        if (!action.IsProgrammable())
        {
            throw new ArgumentException($"La acción '{action.ToWireName()}' solo puede ser inmediata", nameof(action));
        }
        if (delaySeconds < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(delaySeconds), delaySeconds, "El plazo no puede ser negativo");
        }

        var pending = new PendingAction(action, _clock.UtcNow.AddSeconds(delaySeconds));
        _store.Save(new PersistedTimer(pending.Action, pending.ExecuteAtUtc, bootTimeUtc));
        Pending = pending;
        return pending;
    }

    /// <summary>Anula lo programado. Devuelve si había algo.</summary>
    public bool Cancel()
    {
        var had = Pending is not null;
        Pending = null;
        _store.Clear();
        return had;
    }

    /// <summary>
    /// Olvida el temporizador porque ya se va a ejecutar. Se borra del disco ANTES de actuar,
    /// para que un apagado a medias no deje una acción que se repita al volver.
    /// </summary>
    public void Consume()
    {
        Pending = null;
        _store.Clear();
    }

    /// <summary>
    /// Se llama de forma periódica y al detectar una reanudación. Decide si toca ejecutar,
    /// descartar (D5) o esperar.
    /// </summary>
    public SchedulerOutcome Poll()
    {
        var sleptThrough = MarkClocks();
        var pending = Pending;
        if (pending is null)
        {
            return SchedulerOutcome.None;
        }

        var late = _clock.UtcNow - pending.ExecuteAtUtc;
        if (late < TimeSpan.Zero)
        {
            return SchedulerOutcome.None;
        }

        // D5: llegar muy tarde al plazo solo ocurre si el PC estuvo suspendido o detenido.
        // En condiciones normales se detecta el vencimiento dentro del intervalo de sondeo.
        if (late > _tuning.LateThreshold)
        {
            Consume();
            var reason = sleptThrough ? DiscardReasons.Resume : DiscardReasons.Expired;
            return new SchedulerOutcome(SchedulerEvent.Discard, pending.Action, reason);
        }

        return new SchedulerOutcome(SchedulerEvent.Execute, pending.Action);
    }

    public AgentStateReport Report()
    {
        var pending = Pending;
        return pending is null ? AgentStateReport.Idle : new AgentStateReport(pending.ToReport(_clock.UtcNow));
    }

    /// <summary>
    /// Compara el avance de los dos relojes: lo que el de pared avanzó de más es tiempo suspendido.
    /// Devuelve true si el PC estuvo dormido desde la última llamada.
    /// </summary>
    private bool MarkClocks()
    {
        var wall = _clock.UtcNow;
        var monotonic = _clock.Monotonic;

        var wallElapsed = wall - _lastWallClock;
        var monotonicElapsed = monotonic - _lastMonotonic;
        var slept = wallElapsed - monotonicElapsed > _tuning.SuspendDetectionThreshold;

        _lastWallClock = wall;
        _lastMonotonic = monotonic;
        return slept;
    }

    /// <summary>
    /// El arranque se estima a partir del tiempo encendido, así que no es exacto: el reloj se
    /// ajusta por NTP y la suspensión mete sesgo. Se compara con holgura para no descartar por
    /// error un temporizador al reiniciar el servicio (§10), que es el fallo más molesto.
    /// </summary>
    private bool SameBoot(DateTime saved, DateTime current)
        => (saved - current).Duration() <= _tuning.BootTimeTolerance;
}

/// <summary>Umbrales del temporizador. Separados para poder fijarlos en las pruebas.</summary>
public sealed record SchedulerTuning(
    TimeSpan LateThreshold,
    TimeSpan SuspendDetectionThreshold,
    TimeSpan BootTimeTolerance)
{
    public static readonly SchedulerTuning Default = new(
        LateThreshold: TimeSpan.FromSeconds(15),
        SuspendDetectionThreshold: TimeSpan.FromSeconds(5),
        BootTimeTolerance: TimeSpan.FromMinutes(1));
}
