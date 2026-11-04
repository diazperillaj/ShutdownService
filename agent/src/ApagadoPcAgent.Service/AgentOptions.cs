using System.ComponentModel.DataAnnotations;

namespace ApagadoPcAgent.Service;

/// <summary>Contenido de appsettings.json.</summary>
internal sealed class AgentOptions
{
    /// <summary>URL del canal del agente, por ejemplo wss://apagadopc.duckdns.org/ws/agent.</summary>
    [Required(ErrorMessage = "Falta ServerUrl en appsettings.json")]
    public string ServerUrl { get; set; } = string.Empty;

    /// <summary>Debe coincidir con AGENT_TOKEN del servidor.</summary>
    [Required(ErrorMessage = "Falta Token en appsettings.json")]
    [MinLength(32, ErrorMessage = "El Token debe tener al menos 32 caracteres")]
    public string Token { get; set; } = string.Empty;

    /// <summary>
    /// Acepta https/http además de wss/ws por comodidad al copiar la URL del panel,
    /// y los traduce al esquema de WebSocket.
    /// </summary>
    public Uri ResolveUri()
    {
        if (!Uri.TryCreate(ServerUrl.Trim(), UriKind.Absolute, out var uri))
        {
            throw new InvalidOperationException($"ServerUrl no es una URL válida: '{ServerUrl}'");
        }

        var scheme = uri.Scheme switch
        {
            "wss" or "ws" => uri.Scheme,
            "https" => "wss",
            "http" => "ws",
            _ => throw new InvalidOperationException($"ServerUrl debe usar wss:// o ws://, no '{uri.Scheme}://'"),
        };

        return new UriBuilder(uri) { Scheme = scheme }.Uri;
    }
}
