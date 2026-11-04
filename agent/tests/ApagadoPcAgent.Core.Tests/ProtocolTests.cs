using System.Text.Json;
using ApagadoPcAgent.Core;
using ApagadoPcAgent.Core.Protocol;
using Xunit;

namespace ApagadoPcAgent.Core.Tests;

/// <summary>
/// El backend valida los mensajes con Pydantic en camelCase (backend/app/schemas/agent.py).
/// Estas pruebas fijan el formato exacto para que un cambio aquí no rompa el canal en silencio.
/// </summary>
public class ProtocolTests
{
    [Fact]
    public void Hello_se_serializa_como_lo_espera_el_backend()
    {
        var hello = new HelloMessage("PC-CASA", "1.0.0", AgentStateReport.Idle);

        var json = JsonSerializer.Deserialize<JsonElement>(ProtocolJson.Serialize(hello));

        Assert.Equal("hello", json.GetProperty("type").GetString());
        Assert.Equal("PC-CASA", json.GetProperty("hostname").GetString());
        Assert.Equal("1.0.0", json.GetProperty("version").GetString());
        Assert.Equal(JsonValueKind.Null, json.GetProperty("state").GetProperty("pending").ValueKind);
    }

    [Fact]
    public void El_estado_pendiente_usa_camelCase()
    {
        var state = new AgentStateReport(new AgentPending(AgentAction.Shutdown, 1234));

        var json = JsonSerializer.Deserialize<JsonElement>(ProtocolJson.Serialize(new StateMessage(state)));
        var pending = json.GetProperty("state").GetProperty("pending");

        Assert.Equal("state", json.GetProperty("type").GetString());
        Assert.Equal("shutdown", pending.GetProperty("action").GetString());
        Assert.Equal(1234, pending.GetProperty("remainingSeconds").GetInt32());
    }

    [Fact]
    public void El_ack_lleva_id_ok_error_y_estado()
    {
        var ack = new AckMessage("abc123", Ok: false, Error: "la hibernación está deshabilitada", AgentStateReport.Idle);

        var json = JsonSerializer.Deserialize<JsonElement>(ProtocolJson.Serialize(ack));

        Assert.Equal("ack", json.GetProperty("type").GetString());
        Assert.Equal("abc123", json.GetProperty("id").GetString());
        Assert.False(json.GetProperty("ok").GetBoolean());
        Assert.Equal("la hibernación está deshabilitada", json.GetProperty("error").GetString());
        Assert.True(json.TryGetProperty("state", out _));
    }

    [Fact]
    public void El_evento_lleva_evento_accion_y_razon()
    {
        var message = new EventMessage(EventMessage.Discarded, AgentAction.Shutdown, "resume");

        var json = JsonSerializer.Deserialize<JsonElement>(ProtocolJson.Serialize(message));

        Assert.Equal("event", json.GetProperty("type").GetString());
        Assert.Equal("discarded", json.GetProperty("event").GetString());
        Assert.Equal("shutdown", json.GetProperty("action").GetString());
        Assert.Equal("resume", json.GetProperty("reason").GetString());
    }

    [Fact]
    public void Se_lee_un_comando_programado()
    {
        var command = ProtocolJson.TryDeserialize<CommandMessage>(
            """{"type":"command","id":"uuid-1","action":"shutdown","delaySeconds":1800}""");

        Assert.NotNull(command);
        Assert.Equal("command", command.Type);
        Assert.Equal("uuid-1", command.Id);
        Assert.Equal("shutdown", command.Action);
        Assert.Equal(1800, command.DelaySeconds);
    }

    [Fact]
    public void Se_lee_un_cancel_sin_delaySeconds()
    {
        // El backend omite delaySeconds en cancel (exclude_none en CommandMessage.to_json).
        var command = ProtocolJson.TryDeserialize<CommandMessage>(
            """{"type":"command","id":"uuid-2","action":"cancel"}""");

        Assert.NotNull(command);
        Assert.Equal("cancel", command.Action);
        Assert.Null(command.DelaySeconds);
    }

    [Fact]
    public void Un_JSON_invalido_devuelve_null_en_lugar_de_lanzar()
    {
        Assert.Null(ProtocolJson.TryDeserialize<CommandMessage>("{esto no es json"));
    }

    [Fact]
    public void Una_accion_desconocida_no_rompe_el_agente()
    {
        Assert.Null(ProtocolJson.TryDeserialize<AgentStateReport>(
            """{"pending":{"action":"formatear","remainingSeconds":1}}"""));
    }

    [Theory]
    [InlineData(AgentAction.Shutdown, "shutdown")]
    [InlineData(AgentAction.Restart, "restart")]
    [InlineData(AgentAction.Sleep, "sleep")]
    [InlineData(AgentAction.Hibernate, "hibernate")]
    [InlineData(AgentAction.Lock, "lock")]
    public void Las_cinco_acciones_viajan_con_su_nombre(AgentAction action, string wireName)
    {
        Assert.Equal(wireName, action.ToWireName());
        Assert.True(AgentActions.TryParse(wireName, out var parsed));
        Assert.Equal(action, parsed);
    }

    [Theory]
    [InlineData("cancel")]
    [InlineData("apagar")]
    [InlineData("0")]
    [InlineData(null)]
    public void No_se_confunde_otra_cosa_con_una_accion(string? value)
    {
        Assert.False(AgentActions.TryParse(value, out _));
    }

    [Fact]
    public void Solo_bloquear_queda_fuera_del_temporizador()
    {
        Assert.False(AgentAction.Lock.IsProgrammable());
        Assert.True(AgentAction.Shutdown.IsProgrammable());
        Assert.True(AgentAction.Restart.IsProgrammable());
        Assert.True(AgentAction.Sleep.IsProgrammable());
        Assert.True(AgentAction.Hibernate.IsProgrammable());
    }
}
