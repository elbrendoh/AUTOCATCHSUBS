"""Small, GUI-free lifecycle/cache bridge for the original AutoSubs application."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
from pathlib import Path
import subprocess
import sys
from collections import deque
import threading
import time
from autocatchsubs_processes import process_snapshot, resolve_process_id, own_bridge_command, query_command_line
from autocatchsubs_catalog import inspect_catalog, filter_templates, inspect_local_library, catalog_missing
from autocatchsubs_console import frontend_window
from license_guard import require_active

ROOT = Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
STATE = ROOT / "state"
APP_PORT, CONTROL_PORT, LUA_PORT = 56102, 56103, 56104
LOG = logging.getLogger("AUTOCATCHSUBS")
REQUEST_ID = None

def launch_result(result, resolve_pid=None):
    if REQUEST_ID is None:
        return
    data = dict(result, request_id=REQUEST_ID, resolve_pid=resolve_pid)
    temporary = STATE / ("launch-result-" + str(os.getpid()) + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATE / "launch-result.json")

def lua_call(payload, timeout=3):
    connection = http.client.HTTPConnection("127.0.0.1", LUA_PORT, timeout=timeout)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request("POST", "/", body, {"Content-Type": "application/json", "Connection": "close"})
        response = connection.getresponse()
        data = response.read(16*1024*1024)
        if response.status != 200:
            raise RuntimeError("Resolve HTTP " + str(response.status))
        return json.loads(data)
    finally:
        connection.close()

class TemplateCache:
    def __init__(self, path, call=lua_call):
        self.path, self.call = Path(path), call
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.projects, self.active = {}, ""
        self.running, self.scanned = False, set()
        self.refresh_queued = False
        self.progress = {"phase":"counting", "current":0, "total":None, "percent":None}
        self.retry_after = 0
        self.stop = threading.Event()
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if saved.get("version") == 3:
                self.projects = saved.get("projects", {})
        except (OSError, ValueError, TypeError):
            pass

    def select(self, info):
        if isinstance(info, dict):
            with self.lock:
                self.active = info.get("projectName") or ""
        self.start()

    def start(self):
        with self.lock:
            if (self.running or (self.active and self.active in self.scanned) or self.stop.is_set()
                    or time.monotonic() < self.retry_after):
                return
            self.running = True
        threading.Thread(target=self.scan, name="AUTOCATCHSUBS-template-cache", daemon=True).start()

    def refresh(self):
        with self.lock:
            if self.running:
                self.refresh_queued = True
                return {"refreshing": True}
            result = self.call({"func": "ResetTemplateScan"}, 2)
            if not result.get("reset"):
                raise RuntimeError("Resolve no confirmó la actualización de estilos")
            self.scanned.discard(self.active)
            self.progress = {"phase":"counting", "current":0, "total":None, "percent":None}
            self.retry_after = 0
            self.start()
        LOG.info("[SYSTEM_INFO] Actualización de estilos solicitada; se conserva la lista hasta completar el escaneo")
        return {"refreshing": True}

    def scan(self):
        key = ""
        complete = False
        paths = []
        try:
            info = self.call({"func": "GetTimelineInfo"}, 2)
            key = info.get("projectName", "")
            if not key:
                return
            with self.lock:
                self.active = key
            deadline = time.monotonic() + 30
            while not self.stop.is_set() and time.monotonic() < deadline:
                items = self.call({"func": "GetTemplates"}, 2)
                status = self.call({"func": "GetTemplateScanStatus"}, 2)
                with self.lock:
                    count, total = int(status.get("count",0)), int(status.get("total",0))
                    phase = status.get("phase", "scanning")
                    self.progress = {"phase":phase, "current":count, "total":total or None,
                        "percent": min(99, round(100*count/total)) if total and phase == "scanning" else None}
                if status.get("error"):
                    raise RuntimeError(status["error"])
                if not isinstance(items, list):
                    raise RuntimeError("Resolve no devolvió una lista válida de candidatos")
                # Do not expose unverified generator clips while scanning. Resolve
                # labels adjustment clips and Text+ as the same broad Type.
                if not status.get("complete"):
                    self.stop.wait(0.01)
                    continue
                if self.active != key:
                    return
                with self.lock:
                    self.progress.update(phase="verifying", percent=None)
                exported = self.call({"func": "ExportTemplateCatalog"}, 20)
                if not exported.get("exported") or exported.get("projectKey") != status.get("projectKey"):
                    raise RuntimeError("Resolve no confirmó el catálogo del proyecto activo")
                names = exported.get("files", [])
                if not isinstance(names, list) or len(names) > 512 or any(
                        not isinstance(name, str) or not re.fullmatch(r"textplus-bin-\d{3}\.drb", name) for name in names):
                    raise RuntimeError("El catálogo devolvió rutas de bins no válidas")
                paths = [STATE / name for name in names]
                catalog = inspect_catalog(paths)
                missing = catalog_missing(items, catalog)
                LOG.info("[SYSTEM_INFO] Cobertura de exportación: %s/%s IDs activos; generadores exportados=%s",
                         len(items)-len(missing),len(items),catalog["generators"])
                if missing:
                    library = inspect_local_library(status["projectKey"], key, missing)
                    for field in ("ids","names","coveredIds","coveredNames"):
                        catalog[field] = set(catalog.get(field, set())) | set(library.get(field, set()))
                    catalog["source"] = library.get("source")
                missing = catalog_missing(items,catalog)
                if missing:
                    raise RuntimeError("Metadatos incompletos: %s/%s candidatos sin verificar; se conserva la caché"
                                       % (len(missing),len(items)))
                valid = filter_templates(
                    [x for x in items if isinstance(x, dict) and isinstance(x.get("value"), str)], catalog)
                LOG.info("[SYSTEM_INFO] Text+ verificados=%s; generadores descartados=%s",
                         len(valid), len(items)-len(valid))
                if catalog.get("source"):
                    LOG.info("[SYSTEM_INFO] Catálogo recuperado desde biblioteca local en solo lectura")
                try:
                    for path in paths:
                        path.unlink()
                except OSError:
                    pass
                with self.changed:
                    if self.active != key:
                        return
                    # An incomplete empty batch must not erase a valid durable cache.
                    if valid or status.get("complete"):
                        if not status.get("complete"):
                            previous = self.projects.get(key, {}).get("templates", [])
                            merged = {x["value"]: x for x in previous}
                            merged.update({x["value"]: x for x in valid})
                            valid = list(merged.values())
                        self.projects[key] = {"templates": valid, "complete": bool(status.get("complete")),
                                              "projectKey":status["projectKey"],
                                              "verifiedIds":{x["value"]:x.get("mediaId") for x in items
                                                  if x.get("mediaId") in catalog["ids"]},
                                              "updated": time.time()}
                        self.persist()
                        self.progress.update(phase="complete", percent=100, styles=len(valid))
                        self.changed.notify_all()
                if status.get("complete"):
                    complete = True
                    break
                self.stop.wait(0.01)
            LOG.info("[SYSTEM_INFO] Plantillas: proyecto=%s, completo=%s, cantidad=%s", key, complete,
                     len(self.projects.get(key, {}).get("templates", [])))
        except Exception as error:
            LOG.warning("[SYSTEM_WARN] API de plantillas no disponible; se conserva la caché: %s", error)
            with self.lock:
                self.progress.update(phase="waiting", message=str(error)[:180])
        finally:
            for path in paths:
                try:path.unlink(missing_ok=True)
                except OSError:pass
            with self.changed:
                if key and complete:
                    self.scanned.add(key)
                if not complete:
                    self.retry_after = time.monotonic() + 15
                    self.progress["phase"] = "waiting"
                self.running = False
                if complete and self.refresh_queued and not self.stop.is_set():
                    self.refresh_queued = False
                    try:
                        self.refresh()
                    except Exception as error:
                        LOG.warning("[SYSTEM_WARN] No se pudo repetir la actualización de estilos: %s", error)
                self.changed.notify_all()

    def persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 3, "filter": "textplus-and-custom-fusion-titles", "projects": self.projects}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def get(self, cold_timeout=2):
        self.start()
        # Cold cache only: bounded initial wait while the request runs separately
        # from the webview. Warm cache never waits for Resolve.
        deadline = time.monotonic() + cold_timeout
        with self.changed:
            while self.running and not self.projects.get(self.active, {}).get("complete"):
                if self.projects.get(self.active, {}).get("templates"):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.changed.wait(remaining)
            return list(self.projects.get(self.active, {}).get("templates", []))

    def validate_selection(self, name):
        """Confirm the chosen cached title still resolves to its exact live ID.

        No preview generation or timeline insertion. Used before either action
        to prevent an empty/removed template from falling back to an adjustment.
        """
        info = self.call({"func":"GetTimelineInfo"},3)
        key = info.get("projectName", "")
        with self.lock:
            entry = self.projects.get(key,{})
            templates = list(entry.get("templates",[]))
            ids = dict(entry.get("verifiedIds",{}))
            project_id = entry.get("projectKey")
        if not name and templates:name = templates[0]["value"]
        if not name or name not in ids:
            raise RuntimeError("El Text+ no está verificado en este proyecto; actualiza Estilo antes de insertarlo")
        candidates = self.call({"func":"GetTemplates"},3)
        status = self.call({"func":"GetTemplateScanStatus"},3)
        if not status.get("complete") or status.get("projectKey") != project_id:
            raise RuntimeError("El catálogo cambió de proyecto o sigue actualizándose; espera a que termine Estilo")
        if not any(x.get("value")==name and x.get("mediaId")==ids[name] for x in candidates):
            raise RuntimeError("El Text+ seleccionado fue renombrado o eliminado; actualiza Estilo y vuelve a seleccionarlo")
        return {"valid":True,"templateName":name,"mediaId":ids[name],"projectKey":project_id}

class Windows:
    def __init__(self, pid):
        self.resolve_pid = resolve_process_id(pid, process_snapshot())
        self.bridge_hosts = {}
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        k = self.kernel
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateMutexW.restype = wintypes.HANDLE
        self.mutex = k.CreateMutexW(None, False, "Local\\AUTOCATCHSUBS-original-app-controller")
        self.existing = ctypes.get_last_error() == 183
        self.resolve = k.OpenProcess(0x100000 | 0x1000, False, self.resolve_pid)
        if not self.resolve:
            raise RuntimeError("Resolve PID no accesible: " + str(pid))
        image, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        if not k.QueryFullProcessImageNameW(self.resolve, 0, image, ctypes.byref(size)) or Path(image.value).name.lower() != "resolve.exe":
            raise RuntimeError("El PID indicado no corresponde a Resolve.exe")
        self.job = None
        self._create_job()
        if pid and pid != self.resolve_pid and not self.existing:
            self.register_bridge(pid)

    def register_bridge(self, pid):
        pid = int(pid)
        if pid in self.bridge_hosts or pid == self.resolve_pid:
            return
        rows = process_snapshot()
        if rows.get(pid, {}).get("name", "").casefold() != "fuscript.exe":
            return
        if resolve_process_id(pid, rows) != self.resolve_pid:
            return
        menu = Path(os.environ["APPDATA"]) / "Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility/AUTOCATCHSUBS.lua"
        if not own_bridge_command(query_command_line(pid), menu):
            LOG.warning("[SYSTEM_WARN] Se rechazó un host que no ejecuta el menú AUTOCATCHSUBS")
            return
        handle = self.kernel.OpenProcess(0x100000 | 0x1000 | 1, False, pid)
        if handle:
            self.bridge_hosts[pid] = handle
            LOG.info("[SYSTEM_INFO] Host AUTOCATCHSUBS PID=%s vinculado a Resolve PID=%s", pid, self.resolve_pid)

    def _create_job(self):
        class Basic(ctypes.Structure):
            _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("Min", ctypes.c_size_t), ("Max", ctypes.c_size_t),
                        ("Active", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                        ("Priority", wintypes.DWORD), ("Scheduling", wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", Io), ("ProcessMemory", ctypes.c_size_t),
                        ("JobMemory", ctypes.c_size_t), ("PeakProcess", ctypes.c_size_t), ("PeakJob", ctypes.c_size_t)]
        k = self.kernel
        k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.job = k.CreateJobObjectW(None, None)
        limits = Extended()
        limits.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.job or not k.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())

    def attach(self, process):
        if not self.kernel.AssignProcessToJobObject(self.job, int(process._handle)):
            process.terminate()
            raise ctypes.WinError(ctypes.get_last_error())

    def alive(self, milliseconds=0):
        return self.kernel.WaitForSingleObject(self.resolve, milliseconds) == 258

    def show(self, pid):
        result = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetWindow.restype = wintypes.HWND
        self.user.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        self.user.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        @callback_type
        def visit(hwnd, unused):
            owner = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            # Only titled top-level windows owned by our exact child PID.
            title = ctypes.create_unicode_buffer(256)
            rect = wintypes.RECT()
            self.user.GetWindowTextW(hwnd, title, len(title))
            self.user.GetWindowRect(hwnd, ctypes.byref(rect))
            if (owner.value == pid and not self.user.GetWindow(hwnd, 4) and
                    title.value in ("AutoSubs", "AUTOCATCHSUBS") and
                    rect.right - rect.left > 300 and rect.bottom - rect.top > 200):
                self.user.SetWindowTextW(hwnd, "AUTOCATCHSUBS")
                self.user.ShowWindowAsync(hwnd, 9)
                self.user.SetForegroundWindow(hwnd)
                if self.user.IsWindowVisible(hwnd):
                    result.append({"hwnd": int(hwnd), "visible": True,
                                   "width": rect.right-rect.left, "height": rect.bottom-rect.top})
            return True
        self.user.EnumWindows(visit, 0)
        return result

    def close(self, terminate_bridge=False):
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        for handle in self.bridge_hosts.values():
            if terminate_bridge and self.kernel.WaitForSingleObject(handle, 0) == 258:
                self.kernel.TerminateProcess(handle, 0)
            self.kernel.CloseHandle(handle)
        self.bridge_hosts.clear()
        if self.job:
            self.kernel.TerminateJobObject(self.job, 0)
            self.kernel.CloseHandle(self.job)
        self.kernel.CloseHandle(self.resolve)
        self.kernel.CloseHandle(self.mutex)


class Runtime:
    def __init__(self, windows):
        self.windows, self.child = windows, None
        self.lock = threading.Lock()
        self.cache = TemplateCache(STATE / "templates.json")
        self.console_child, self.console_open = None, False
        self.ui_errors = deque(maxlen=150)

    def ensure_console(self):
        if self.console_child and self.console_child.poll() is None:
            return
        with (STATE / "console-startup.log").open("ab") as output:
            self.console_child = subprocess.Popen([sys.executable,"--console",
                "--frontend-pid",str(self.child.pid),"--resolve-pid",str(self.windows.resolve_pid),
                "--controller-pid",str(os.getpid())],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
        self.windows.attach(self.console_child)
        LOG.info("[SYSTEM_INFO] Console externa iniciada, PID=%s",self.console_child.pid)

    def status(self):
        alive = bool(self.child and self.child.poll() is None)
        return {"suite":"AUTOCATCHSUBS", "pid":self.child.pid if alive else None,
            "resolveAlive":self.windows.alive(),"resolvePid":self.windows.resolve_pid,
            "bridgeHosts":list(self.windows.bridge_hosts),"window":frontend_window(self.child.pid) if alive else None,
            "consoleOpen":self.console_open if alive else False,
            "consolePid":self.console_child.pid if self.console_child and self.console_child.poll() is None else None}

    def set_console(self, opened):
        with self.lock:
            if not isinstance(opened,bool) or not self.child or self.child.poll() is not None:
                raise ValueError("No hay ventana propia activa para abrir Console")
            self.ensure_console()
            self.console_open=opened
            LOG.info("[SYSTEM_INFO] Console externa %s","abierta" if opened else "cerrada")
            return self.status()

    def open(self):
        with self.lock:
            if not self.windows.alive():
                raise RuntimeError("Resolve se ha cerrado")
            if not self.child or self.child.poll() is not None:
                if self.console_child and self.console_child.poll() is None:
                    self.console_child.terminate()
                self.console_child=None
                self.console_open=False
                # No CLI arguments: this is the original full GUI, never headless.
                with (STATE / "app-startup.log").open("ab") as output:
                    self.child = subprocess.Popen([str(ROOT / "AUTOCATCHSUBS.exe")], cwd=ROOT,
                                                  stdout=output, stderr=subprocess.STDOUT)
                self.windows.attach(self.child)
                LOG.info("[SYSTEM_INFO] Interfaz original iniciada, PID=%s", self.child.pid)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and self.child.poll() is None and self.windows.alive():
                windows = self.windows.show(self.child.pid)
                if windows:
                    self.ensure_console()
                    return {"opened": True, "pid": self.child.pid, "windows": windows}
                time.sleep(0.1)
            error = "No se detectó una ventana visible de AUTOCATCHSUBS"
            LOG.error("[AUTOCATCHSUBS_ERROR] %s; exit=%s", error, self.child.poll())
            return {"opened": False, "error": error, "pid": self.child.pid, "exit": self.child.poll()}

def handler(runtime, control=False):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def setup(self):
            super().setup()
            self.connection.settimeout(3)
        def log_message(self, *args):
            pass
        def respond(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            self.close_connection = True
        def do_GET(self):
            self.respond({"suite": "AUTOCATCHSUBS", "updater": "disabled"}, 404)
        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4*1024*1024:
                    raise ValueError("Invalid content length")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Invalid payload")
                func = payload.get("func")
                if func in ("ExportAudio","AddSubtitles","GeneratePreview","StartPresetEdit","CapturePresetSettings"):
                    require_active()
                if not control and func == "ConsoleLayout":
                    self.respond(runtime.set_console(payload.get("open")))
                    return
                if not control and func == "RecordUiError":
                    if payload.get("tag") not in ("SYSTEM_WARN","AUTOCATCHSUBS_ERROR") or not isinstance(payload.get("text"),str):
                        raise ValueError("Registro de interfaz no válido")
                    runtime.ui_errors.append(time.strftime("%Y-%m-%d %H:%M:%S")+" ["+payload["tag"]+"] "+payload["text"][:1800])
                    self.respond({"ok":True})
                    return
                if not control and func == "GetDiagnostics":
                    def tail(name, limit=24000):
                        try:
                            with (STATE / name).open("rb") as stream:
                                stream.seek(0, 2)
                                stream.seek(max(0, stream.tell() - limit))
                                return stream.read(limit).decode("utf-8", errors="replace")
                        except OSError:
                            return ""
                    self.respond({"suite": "AUTOCATCHSUBS", "revision": "arranque-2026-10-03-r11",
                        "resolveAlive": runtime.windows.alive(),
                        "templates": len(runtime.cache.get(cold_timeout=0)),
                        "catalog":{"projectName":runtime.cache.active,"progress":dict(runtime.cache.progress),
                            "projectKey":runtime.cache.projects.get(runtime.cache.active,{}).get("projectKey"),
                            "updated":runtime.cache.projects.get(runtime.cache.active,{}).get("updated")},
                        "controller": tail("controller.log"), "app": tail("app-startup.log")+tail("console-startup.log"),
                        "ui":list(runtime.ui_errors),
                        "changes": ["Nombre AUTOCATCHSUBS; integración exclusiva con DaVinci Resolve",
                            "Text+: validación por IDs; exportaciones parciales no borran la caché",
                            "Estilo: catálogo verificado Text+ y buscador por nombre",
                            "Actualización de estilos con progreso y total de clips",
                            "Console externa a la derecha; ancho de subtítulos intacto; Copiar Log",
                            "ELIMINAR con Deshacer; filas vacías omitidas al añadir a timeline"]})
                    return
                if not control and func == "UiEvent":
                    allowed = {"subtitle-deleted", "subtitle-restored", "console-opened"}
                    event = payload.get("event")
                    if event not in allowed:
                        self.respond({"error": True, "message": "Evento no permitido"}, 400)
                        return
                    LOG.info("[SYSTEM_INFO] Interfaz: %s", event)
                    self.respond({"ok": True})
                    return
                if control:
                    if func == "ShowWindow":
                        self.respond(runtime.open())
                    elif func == "Status":
                        self.respond(runtime.status())
                    elif func == "SetConsoleOpen":
                        self.respond(runtime.set_console(payload.get("open")))
                    else:
                        self.respond({"error": True, "message": "Unknown control"}, 400)
                elif func == "GetTemplates":
                    self.respond(runtime.cache.get())
                elif func == "GetTemplateCacheStatus":
                    with runtime.cache.lock:
                        self.respond({"complete": bool(runtime.cache.projects.get(runtime.cache.active, {}).get("complete")),
                                      "scanning": runtime.cache.running,
                                      "progress":dict(runtime.cache.progress),
                                      "pending": bool(runtime.cache.active and runtime.cache.active not in runtime.cache.scanned)})
                elif func == "RefreshTemplates":
                    self.respond(runtime.cache.refresh())
                elif func == "ValidateTemplateSelection":
                    self.respond(runtime.cache.validate_selection(payload.get("templateName")))
                elif func == "Exit":
                    LOG.info("[SYSTEM_INFO] Ventana cerrada; el puente continúa disponible")
                    self.respond({"message": "Window closed; bridge kept alive"})
                else:
                    if func in ("AddSubtitles","GeneratePreview"):
                        selection = runtime.cache.validate_selection(payload.get("templateName"))
                        payload = dict(payload,templateName=selection["templateName"])
                    timeout = 180 if func in ("ExportAudio", "AddSubtitles", "GeneratePreview", "StartPresetEdit", "CapturePresetSettings") else 3
                    result = lua_call(payload, timeout)
                    if isinstance(result, dict) and (result.get("error") or
                            isinstance(result.get("result"), dict) and result["result"].get("error")):
                        LOG.error("[AUTOCATCHSUBS_ERROR] %s: %s", func,
                                  str(result.get("message") or result.get("result", {}).get("message", "Error en Resolve"))[:1500])
                    if func == "GetTimelineInfo":
                        runtime.cache.select(result)
                    self.respond(result)
            except Exception as error:
                LOG.warning("[SYSTEM_WARN] Petición: %s", error)
                self.respond({"error": True, "message": "AUTOCATCHSUBS: enlace con Resolve no disponible", "detail": str(error)})
    return Handler

def main():
    global REQUEST_ID
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--resolve-pid", type=int)
    source.add_argument("--host-pid", type=int)
    parser.add_argument("--request-id")
    args = parser.parse_args()
    REQUEST_ID = args.request_id
    STATE.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[RotatingFileHandler(STATE / "controller.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")])
    win = Windows(args.host_pid or args.resolve_pid)
    if win.existing:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", CONTROL_PORT, timeout=10)
            conn.request("POST", "/", json.dumps({"func": "ShowWindow"}), {"Content-Type": "application/json"})
            result = json.loads(conn.getresponse().read())
            LOG.info("[SYSTEM_INFO] Reapertura comprobada: %s", result)
            launch_result(result, win.resolve_pid)
            conn.close()
        except Exception:
            LOG.exception("[AUTOCATCHSUBS_ERROR] No se pudo restaurar la ventana existente")
            launch_result({"opened": False, "error": "No se pudo restaurar la ventana existente"}, win.resolve_pid)
        finally:
            win.close()
        return
    runtime = Runtime(win)
    servers = []
    try:
        for port, control in ((APP_PORT, False), (CONTROL_PORT, True)):
            server = ThreadingHTTPServer(("127.0.0.1", port), handler(runtime, control))
            server.daemon_threads = True
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        LOG.info("[SYSTEM_INFO] Sesión ligada a Resolve PID=%s; argumento host=%s", win.resolve_pid, args.host_pid)
        runtime.cache.start()
        opened = runtime.open()
        launch_result(opened, win.resolve_pid)
        (STATE / "window.json").write_text(json.dumps(opened), encoding="utf-8")
        next_ping = time.monotonic() + 15
        next_title = time.monotonic() + 1
        while win.alive(250):
            if time.monotonic() >= next_title:
                next_title = time.monotonic() + 1
                if runtime.child and runtime.child.poll() is None:
                    frontend_window(runtime.child.pid)
            if time.monotonic() >= next_ping:
                next_ping = time.monotonic() + 15
                def keepalive():
                    try:
                        identity = lua_call({"func": "Ping"}, 2)
                        if identity.get("suite") == "AUTOCATCHSUBS" and identity.get("resolvePid") == win.resolve_pid:
                            win.register_bridge(identity["hostPid"])
                        runtime.cache.start()
                    except Exception as error:
                        LOG.warning("[SYSTEM_WARN] Resolve ocupado; se mantiene el servicio: %s", error)
                threading.Thread(target=keepalive, daemon=True).start()
        LOG.info("[SYSTEM_INFO] Resolve terminó; cierre del árbol de AUTOCATCHSUBS")
    except Exception:
        LOG.exception("[AUTOCATCHSUBS_ERROR] Error del controlador")
        launch_result({"opened": False, "error": "Error del controlador; revisa state/controller.log"}, win.resolve_pid)
    finally:
        runtime.cache.stop.set()
        # Terminate owned children first, before joining potentially busy workers.
        win.close(terminate_bridge=not win.alive())
        for server in servers:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        STATE.mkdir(exist_ok=True)
        LOG.exception("[AUTOCATCHSUBS_ERROR] Fallo de inicio: %s", error)
        launch_result({"opened": False, "error": str(error)})
        (STATE / "startup-error.txt").write_text(str(error), encoding="utf-8")
