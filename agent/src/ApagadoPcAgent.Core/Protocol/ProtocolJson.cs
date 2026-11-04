using System.Text.Json;
using System.Text.Json.Serialization;

namespace ApagadoPcAgent.Core.Protocol;

/// <summary>Serialización compartida por el canal con el backend y por el estado en disco.</summary>
public static class ProtocolJson
{
    public static readonly JsonSerializerOptions Options = Create();

    private static JsonSerializerOptions Create()
    {
        var options = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            PropertyNameCaseInsensitive = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.Never,
        };
        options.Converters.Add(new AgentActionConverter());
        return options;
    }

    public static string Serialize<T>(T value) => JsonSerializer.Serialize(value, Options);

    /// <summary>Devuelve null si el JSON no es válido, en lugar de lanzar.</summary>
    public static T? TryDeserialize<T>(string json) where T : class
    {
        try
        {
            return JsonSerializer.Deserialize<T>(json, Options);
        }
        catch (JsonException)
        {
            return null;
        }
    }
}

/// <summary>Convierte la acción usando los nombres del protocolo, no los del enum.</summary>
internal sealed class AgentActionConverter : JsonConverter<AgentAction>
{
    public override AgentAction Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var value = reader.GetString();
        if (!AgentActions.TryParse(value, out var action))
        {
            throw new JsonException($"Acción desconocida: '{value}'");
        }
        return action;
    }

    public override void Write(Utf8JsonWriter writer, AgentAction value, JsonSerializerOptions options)
        => writer.WriteStringValue(value.ToWireName());
}
