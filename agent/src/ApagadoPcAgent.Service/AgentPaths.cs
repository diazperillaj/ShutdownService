namespace ApagadoPcAgent.Service;

/// <summary>Rutas fijas del agente en el PC (ESPECIFICACION.md §5).</summary>
internal static class AgentPaths
{
    public const string ServiceName = "ApagadoPcAgent";

    /// <summary>C:\ProgramData\ApagadoPC (su ACL la fija install.ps1: solo SYSTEM y Administradores).</summary>
    public static string DataDirectory { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "ApagadoPC");

    public static string ConfigFile => Path.Combine(DataDirectory, "appsettings.json");

    public static string TimerFile => Path.Combine(DataDirectory, "state.json");

    public static string LogDirectory => Path.Combine(DataDirectory, "logs");
}
