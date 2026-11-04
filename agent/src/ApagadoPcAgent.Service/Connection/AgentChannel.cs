using System.Net.WebSockets;
using System.Text;
using ApagadoPcAgent.Core.Protocol;

namespace ApagadoPcAgent.Service.Connection;

/// <summary>
/// Una conexión con el backend. El PC siempre inicia la conexión (saliente), así que no hay que
/// abrir puertos en la red de casa. Esta clase cubre una sola conexión; de reintentar se encarga
/// <see cref="AgentWorker"/>.
/// </summary>
internal sealed class AgentChannel : IAsyncDisposable
{
    private const int MaxMessageBytes = 64 * 1024;

    private readonly ClientWebSocket _socket;
    private readonly SemaphoreSlim _sendLock = new(1, 1);

    private AgentChannel(ClientWebSocket socket) => _socket = socket;

    public bool IsOpen => _socket.State == WebSocketState.Open;

    public static async Task<AgentChannel> ConnectAsync(
        Uri url, string token, TimeSpan keepAlive, CancellationToken cancellationToken)
    {
        var socket = new ClientWebSocket();
        socket.Options.SetRequestHeader("Authorization", $"Bearer {token}");
        // El servidor ya hace ping cada 30 s; este es el del lado del PC, para notar antes
        // una conexión muerta (por ejemplo si el router pierde la NAT).
        socket.Options.KeepAliveInterval = keepAlive;
        try
        {
            await socket.ConnectAsync(url, cancellationToken);
            return new AgentChannel(socket);
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    }

    public async Task SendAsync(object message, CancellationToken cancellationToken)
    {
        var bytes = Encoding.UTF8.GetBytes(ProtocolJson.Serialize(message));
        await _sendLock.WaitAsync(cancellationToken);
        try
        {
            await _socket.SendAsync(bytes, WebSocketMessageType.Text, endOfMessage: true, cancellationToken);
        }
        finally
        {
            _sendLock.Release();
        }
    }

    /// <summary>Devuelve el siguiente mensaje, o null si la conexión se cerró.</summary>
    public async Task<string?> ReceiveAsync(CancellationToken cancellationToken)
    {
        var buffer = new byte[8 * 1024];
        using var message = new MemoryStream();

        while (true)
        {
            WebSocketReceiveResult result;
            try
            {
                result = await _socket.ReceiveAsync(buffer, cancellationToken);
            }
            catch (WebSocketException)
            {
                return null;
            }

            if (result.MessageType == WebSocketMessageType.Close)
            {
                return null;
            }

            message.Write(buffer, 0, result.Count);
            if (message.Length > MaxMessageBytes)
            {
                throw new InvalidDataException("El servidor envió un mensaje demasiado grande");
            }

            if (result.EndOfMessage)
            {
                return Encoding.UTF8.GetString(message.GetBuffer(), 0, (int)message.Length);
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (_socket.State == WebSocketState.Open)
            {
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
                await _socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "adiós", timeout.Token);
            }
        }
        catch (Exception ex) when (ex is WebSocketException or OperationCanceledException or ObjectDisposedException)
        {
            // Cerrar con elegancia es un detalle; si la conexión ya está rota, da igual.
        }
        finally
        {
            _socket.Dispose();
            _sendLock.Dispose();
        }
    }
}
