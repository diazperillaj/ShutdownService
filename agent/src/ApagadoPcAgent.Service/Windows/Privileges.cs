using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace ApagadoPcAgent.Service.Windows;

/// <summary>
/// Habilita un privilegio en el token del proceso. LocalSystem tiene SeShutdownPrivilege, pero
/// viene presente y DESHABILITADO: sin activarlo, SetSuspendState falla.
/// </summary>
[SupportedOSPlatform("windows")]
internal static class Privileges
{
    public const string Shutdown = "SeShutdownPrivilege";

    private const int TokenAdjustPrivileges = 0x0020;
    private const int TokenQuery = 0x0008;
    private const uint PrivilegeEnabled = 0x0002;

    [StructLayout(LayoutKind.Sequential)]
    private struct Luid
    {
        public uint LowPart;
        public int HighPart;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenPrivileges
    {
        public uint PrivilegeCount;
        public Luid Luid;
        public uint Attributes;
    }

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(IntPtr process, int desiredAccess, out IntPtr token);

    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool LookupPrivilegeValue(string? system, string name, out Luid luid);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AdjustTokenPrivileges(
        IntPtr token,
        [MarshalAs(UnmanagedType.Bool)] bool disableAll,
        ref TokenPrivileges newState,
        int bufferLength,
        IntPtr previousState,
        IntPtr returnLength);

    /// <summary>Devuelve el error de Windows, o null si el privilegio quedó habilitado.</summary>
    public static string? TryEnable(string privilege)
    {
        if (!OpenProcessToken(GetCurrentProcess(), TokenAdjustPrivileges | TokenQuery, out var token))
        {
            return Describe("OpenProcessToken");
        }

        try
        {
            if (!LookupPrivilegeValue(null, privilege, out var luid))
            {
                return Describe("LookupPrivilegeValue");
            }

            var privileges = new TokenPrivileges
            {
                PrivilegeCount = 1,
                Luid = luid,
                Attributes = PrivilegeEnabled,
            };

            if (!AdjustTokenPrivileges(token, false, ref privileges, 0, IntPtr.Zero, IntPtr.Zero))
            {
                return Describe("AdjustTokenPrivileges");
            }

            // AdjustTokenPrivileges devuelve true aunque no haya podido asignar todos los
            // privilegios; el código de error es la única forma de saberlo.
            var lastError = Marshal.GetLastWin32Error();
            return lastError == 0 ? null : Describe("AdjustTokenPrivileges", lastError);
        }
        finally
        {
            CloseHandle(token);
        }
    }

    private static string Describe(string call, int? error = null)
    {
        var code = error ?? Marshal.GetLastWin32Error();
        return $"{call} falló (error {code}: {Marshal.GetPInvokeErrorMessage(code)})";
    }
}
