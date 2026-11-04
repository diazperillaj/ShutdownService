using ApagadoPcAgent.Core.Protocol;

namespace ApagadoPcAgent.Core.Scheduling;

/// <summary>Guarda el temporizador en un JSON (state.json), escribiendo de forma atómica.</summary>
public sealed class FileTimerStore(string path, Action<string, Exception>? onError = null) : ITimerStore
{
    private readonly string _path = path;
    private readonly Action<string, Exception>? _onError = onError;

    public PersistedTimer? Load()
    {
        try
        {
            if (!File.Exists(_path))
            {
                return null;
            }
            return ProtocolJson.TryDeserialize<PersistedTimer>(File.ReadAllText(_path));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _onError?.Invoke("No se pudo leer el temporizador guardado", ex);
            return null;
        }
    }

    public void Save(PersistedTimer timer)
    {
        try
        {
            var directory = Path.GetDirectoryName(_path);
            if (!string.IsNullOrEmpty(directory))
            {
                Directory.CreateDirectory(directory);
            }
            // Se escribe aparte y se mueve encima: si se corta la luz a mitad, el archivo
            // anterior sigue entero en lugar de quedar truncado.
            var temporary = _path + ".tmp";
            File.WriteAllText(temporary, ProtocolJson.Serialize(timer));
            File.Move(temporary, _path, overwrite: true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _onError?.Invoke("No se pudo guardar el temporizador", ex);
        }
    }

    public void Clear()
    {
        try
        {
            File.Delete(_path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _onError?.Invoke("No se pudo borrar el temporizador guardado", ex);
        }
    }
}
