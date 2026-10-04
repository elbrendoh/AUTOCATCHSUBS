"""Resolve process identity, separate from its per-script fuscript.exe hosts."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess

def process_snapshot():
    class Entry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                    ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                    ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent_pid", wintypes.DWORD), ("priority", wintypes.LONG),
                    ("flags", wintypes.DWORD), ("name", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        result = {}
        available = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while available:
            result[entry.pid] = {"name": entry.name, "parent_pid": entry.parent_pid}
            available = kernel.Process32NextW(handle, ctypes.byref(entry))
        return result
    finally:
        kernel.CloseHandle(handle)

def resolve_process_id(pid, processes):
    if pid is None:
        candidates = [key for key, value in processes.items() if value["name"].casefold() == "resolve.exe"]
        if len(candidates) != 1:
            raise RuntimeError("Abre una única instancia de DaVinci Resolve antes de iniciar AUTOCATCHSUBS")
        return candidates[0]
    start = processes.get(pid)
    if not start or start["name"].casefold() not in ("resolve.exe", "fuscript.exe"):
        raise RuntimeError("El proceso recibido no es Resolve ni su host de scripting")
    visited = set()
    for _ in range(16):
        item = processes.get(pid)
        if not item or pid in visited:
            break
        if item["name"].casefold() == "resolve.exe":
            return pid
        visited.add(pid)
        pid = item["parent_pid"]
    raise RuntimeError("Este puente pertenece a una sesión de Resolve que ya terminó; vuelve a ejecutar el menú AUTOCATCHSUBS")

def own_bridge_command(command, menu_path):
    value = (command or "").strip().casefold()
    exact = str(menu_path).casefold()
    return value.endswith('"' + exact + '"') or value.endswith(" " + exact)

def query_command_line(pid):
    # Only a validated integer enters this command. No plugin code is executed.
    command = f"Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' | Select-Object -ExpandProperty CommandLine"
    return subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", command],
                                   text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).strip()
