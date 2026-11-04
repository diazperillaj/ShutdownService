using System.Text;
using Microsoft.Extensions.Logging;

namespace ApagadoPcAgent.Service.Logging;

/// <summary>
/// Registro en archivos de texto dentro de C:\ProgramData\ApagadoPC\logs (§5), además del Visor
/// de eventos que ya añade AddWindowsService. Un archivo por día, con limpieza de los viejos.
/// </summary>
internal sealed class FileLoggerProvider : ILoggerProvider
{
    private const int RetainDays = 14;

    private readonly string _directory;
    private readonly LogLevel _minimum;
    private readonly Lock _gate = new();

    private DateOnly _currentDay;
    private bool _purgedToday;

    public FileLoggerProvider(string directory, LogLevel minimum = LogLevel.Information)
    {
        _directory = directory;
        _minimum = minimum;
    }

    public ILogger CreateLogger(string categoryName) => new FileLogger(this, categoryName);

    public void Dispose()
    {
    }

    internal bool IsEnabled(LogLevel level) => level >= _minimum && level != LogLevel.None;

    internal void Write(LogLevel level, string category, string message, Exception? exception)
    {
        var now = DateTime.Now;
        var line = new StringBuilder()
            .Append(now.ToString("yyyy-MM-dd HH:mm:ss.fff"))
            .Append(' ')
            .Append(Describe(level))
            .Append(' ')
            .Append(ShortCategory(category))
            .Append(": ")
            .Append(message)
            .AppendLine();

        if (exception is not null)
        {
            line.AppendLine(exception.ToString());
        }

        lock (_gate)
        {
            try
            {
                Directory.CreateDirectory(_directory);
                var day = DateOnly.FromDateTime(now);
                if (day != _currentDay)
                {
                    _currentDay = day;
                    _purgedToday = false;
                }
                if (!_purgedToday)
                {
                    _purgedToday = true;
                    PurgeOldFiles(now);
                }

                File.AppendAllText(Path.Combine(_directory, $"agente-{day:yyyy-MM-dd}.log"), line.ToString());
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // Quedarse sin log no es razón para tumbar el servicio: el Visor de eventos sigue.
            }
        }
    }

    private void PurgeOldFiles(DateTime now)
    {
        var cutoff = now.AddDays(-RetainDays);
        foreach (var file in Directory.EnumerateFiles(_directory, "agente-*.log"))
        {
            try
            {
                if (File.GetLastWriteTime(file) < cutoff)
                {
                    File.Delete(file);
                }
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // Se intentará de nuevo mañana.
            }
        }
    }

    private static string Describe(LogLevel level) => level switch
    {
        LogLevel.Trace => "TRACE",
        LogLevel.Debug => "DEBUG",
        LogLevel.Information => "INFO ",
        LogLevel.Warning => "WARN ",
        LogLevel.Error => "ERROR",
        LogLevel.Critical => "CRIT ",
        _ => "?????",
    };

    /// <summary>Solo el último tramo del namespace: las líneas quedan legibles.</summary>
    private static string ShortCategory(string category)
    {
        var lastDot = category.LastIndexOf('.');
        return lastDot < 0 ? category : category[(lastDot + 1)..];
    }

    private sealed class FileLogger(FileLoggerProvider provider, string category) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => provider.IsEnabled(logLevel);

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter)
        {
            if (!IsEnabled(logLevel))
            {
                return;
            }
            provider.Write(logLevel, category, formatter(state, exception), exception);
        }
    }
}

internal static class FileLoggerExtensions
{
    public static ILoggingBuilder AddFile(this ILoggingBuilder builder, string directory)
    {
        builder.AddProvider(new FileLoggerProvider(directory));
        return builder;
    }
}
