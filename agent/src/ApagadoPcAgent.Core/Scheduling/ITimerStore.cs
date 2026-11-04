namespace ApagadoPcAgent.Core.Scheduling;

/// <summary>Persistencia del temporizador. Nunca lanza: un disco con problemas no debe tumbar el agente.</summary>
public interface ITimerStore
{
    PersistedTimer? Load();

    void Save(PersistedTimer timer);

    void Clear();
}
