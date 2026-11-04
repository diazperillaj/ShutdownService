namespace ApagadoPcAgent.Service.Windows;

/// <summary>
/// Avisa al temporizador de que el PC acaba de despertar, para revisar la regla D5 en el momento
/// en lugar de esperar al siguiente sondeo.
/// </summary>
internal sealed class ResumeSignal
{
    private readonly SemaphoreSlim _signal = new(0, 1);

    public void Signal()
    {
        try
        {
            _signal.Release();
        }
        catch (SemaphoreFullException)
        {
            // Ya había un aviso sin atender: con uno basta.
        }
    }

    /// <summary>
    /// Espera a que el PC despierte o a que venza el plazo. Devuelve true si fue un despertar.
    /// Hace también de pausa del bucle de sondeo, así que no hace falta otro Task.Delay.
    /// </summary>
    public Task<bool> WaitAsync(TimeSpan timeout, CancellationToken cancellationToken)
        => _signal.WaitAsync(timeout, cancellationToken);
}
