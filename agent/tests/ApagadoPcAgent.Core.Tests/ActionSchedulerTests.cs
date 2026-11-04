using ApagadoPcAgent.Core;
using ApagadoPcAgent.Core.Scheduling;
using Xunit;

namespace ApagadoPcAgent.Core.Tests;

public class ActionSchedulerTests
{
    private static readonly DateTime Start = new(2026, 11, 3, 20, 0, 0, DateTimeKind.Utc);
    private static readonly DateTime BootTime = new(2026, 11, 3, 8, 0, 0, DateTimeKind.Utc);

    private static (ActionScheduler Scheduler, FakeClock Clock, MemoryTimerStore Store) Build()
    {
        var clock = new FakeClock(Start);
        var store = new MemoryTimerStore();
        return (new ActionScheduler(store, clock), clock, store);
    }

    [Fact]
    public void Schedule_guarda_el_temporizador_en_disco()
    {
        var (scheduler, _, store) = Build();

        var pending = scheduler.Schedule(AgentAction.Shutdown, 1800, BootTime);

        Assert.Equal(Start.AddMinutes(30), pending.ExecuteAtUtc);
        Assert.Equal(new PersistedTimer(AgentAction.Shutdown, Start.AddMinutes(30), BootTime), store.Current);
    }

    [Fact]
    public void Schedule_reemplaza_la_programacion_anterior()
    {
        var (scheduler, _, store) = Build();

        scheduler.Schedule(AgentAction.Shutdown, 1800, BootTime);
        scheduler.Schedule(AgentAction.Restart, 60, BootTime);

        Assert.Equal(AgentAction.Restart, scheduler.Pending!.Action);
        Assert.Equal(AgentAction.Restart, store.Current!.Action);
    }

    [Fact]
    public void Bloquear_no_se_puede_programar()
    {
        var (scheduler, _, _) = Build();

        Assert.Throws<ArgumentException>(() => scheduler.Schedule(AgentAction.Lock, 60, BootTime));
    }

    [Fact]
    public void Poll_no_hace_nada_antes_del_plazo()
    {
        var (scheduler, clock, _) = Build();
        scheduler.Schedule(AgentAction.Shutdown, 600, BootTime);

        clock.Advance(TimeSpan.FromMinutes(9));

        Assert.Equal(SchedulerEvent.None, scheduler.Poll().Event);
    }

    [Fact]
    public void Poll_ejecuta_al_vencer_el_plazo()
    {
        var (scheduler, clock, _) = Build();
        scheduler.Schedule(AgentAction.Shutdown, 600, BootTime);

        clock.Advance(TimeSpan.FromMinutes(10));
        var outcome = scheduler.Poll();

        Assert.Equal(SchedulerEvent.Execute, outcome.Event);
        Assert.Equal(AgentAction.Shutdown, outcome.Action);
    }

    [Fact]
    public void D5_al_despertar_con_la_hora_vencida_se_descarta()
    {
        var (scheduler, clock, store) = Build();
        scheduler.Schedule(AgentAction.Shutdown, 600, BootTime);

        // El PC se suspende y despierta una hora después: el plazo pasó mientras dormía.
        clock.Suspend(TimeSpan.FromHours(1));
        var outcome = scheduler.Poll();

        Assert.Equal(SchedulerEvent.Discard, outcome.Event);
        Assert.Equal(AgentAction.Shutdown, outcome.Action);
        Assert.Equal(DiscardReasons.Resume, outcome.Reason);
        Assert.Null(scheduler.Pending);
        Assert.Null(store.Current);
    }

    [Fact]
    public void Un_retraso_corto_todavia_ejecuta()
    {
        var (scheduler, clock, _) = Build();
        scheduler.Schedule(AgentAction.Sleep, 600, BootTime);

        // 5 s de retraso: es el sondeo normal llegando algo tarde, no una suspensión.
        clock.Advance(TimeSpan.FromMinutes(10) + TimeSpan.FromSeconds(5));

        Assert.Equal(SchedulerEvent.Execute, scheduler.Poll().Event);
    }

    [Fact]
    public void D6_al_reiniciar_el_PC_el_temporizador_se_descarta()
    {
        var (scheduler, _, store) = Build();
        store.Current = new PersistedTimer(AgentAction.Shutdown, Start.AddMinutes(30), BootTime);

        // El PC arrancó de nuevo: el arranque actual es otro.
        var outcome = scheduler.Restore(Start.AddMinutes(-1));

        Assert.Equal(SchedulerEvent.Discard, outcome.Event);
        Assert.Equal(DiscardReasons.Boot, outcome.Reason);
        Assert.Null(scheduler.Pending);
        Assert.Null(store.Current);
    }

    [Fact]
    public void Al_reiniciar_el_servicio_en_el_mismo_arranque_se_restaura()
    {
        var (scheduler, _, store) = Build();
        store.Current = new PersistedTimer(AgentAction.Shutdown, Start.AddMinutes(30), BootTime);

        var outcome = scheduler.Restore(BootTime);

        Assert.Equal(SchedulerEvent.Restored, outcome.Event);
        Assert.Equal(Start.AddMinutes(30), scheduler.Pending!.ExecuteAtUtc);
        Assert.NotNull(store.Current);
    }

    [Fact]
    public void El_arranque_se_compara_con_holgura()
    {
        var (scheduler, _, store) = Build();
        store.Current = new PersistedTimer(AgentAction.Shutdown, Start.AddMinutes(30), BootTime);

        // El arranque se estima a partir del tiempo encendido: unos segundos de diferencia
        // son normales y no deben descartar el temporizador.
        var outcome = scheduler.Restore(BootTime.AddSeconds(20));

        Assert.Equal(SchedulerEvent.Restored, outcome.Event);
    }

    [Fact]
    public void Restaurar_un_plazo_ya_vencido_lo_descarta()
    {
        var (scheduler, _, store) = Build();
        store.Current = new PersistedTimer(AgentAction.Shutdown, Start.AddMinutes(-5), BootTime);

        var outcome = scheduler.Restore(BootTime);

        Assert.Equal(SchedulerEvent.Discard, outcome.Event);
        Assert.Equal(DiscardReasons.Expired, outcome.Reason);
        Assert.Null(store.Current);
    }

    [Fact]
    public void Restaurar_sin_nada_guardado_no_hace_nada()
    {
        var (scheduler, _, _) = Build();

        Assert.Equal(SchedulerEvent.None, scheduler.Restore(BootTime).Event);
        Assert.Null(scheduler.Pending);
    }

    [Fact]
    public void Cancel_borra_el_temporizador_y_dice_si_habia_algo()
    {
        var (scheduler, _, store) = Build();

        Assert.False(scheduler.Cancel());

        scheduler.Schedule(AgentAction.Shutdown, 600, BootTime);
        Assert.True(scheduler.Cancel());
        Assert.Null(scheduler.Pending);
        Assert.Null(store.Current);
    }

    [Fact]
    public void Consume_olvida_el_temporizador_antes_de_ejecutar()
    {
        var (scheduler, _, store) = Build();
        scheduler.Schedule(AgentAction.Shutdown, 600, BootTime);

        scheduler.Consume();

        Assert.Null(scheduler.Pending);
        Assert.Null(store.Current);
    }

    [Fact]
    public void El_estado_informa_los_segundos_que_faltan_redondeando_hacia_arriba()
    {
        var (scheduler, clock, _) = Build();
        scheduler.Schedule(AgentAction.Hibernate, 600, BootTime);

        clock.Advance(TimeSpan.FromSeconds(0.5));
        var report = scheduler.Report();

        Assert.Equal(AgentAction.Hibernate, report.Pending!.Action);
        Assert.Equal(600, report.Pending.RemainingSeconds);
    }

    [Fact]
    public void Sin_nada_programado_el_estado_va_vacio()
    {
        var (scheduler, _, _) = Build();

        Assert.Null(scheduler.Report().Pending);
    }
}
