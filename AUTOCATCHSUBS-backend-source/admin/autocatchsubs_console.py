"""External, owned Console dock. Never resize the transcription window."""
from __future__ import annotations
import argparse
import sys
import ctypes
from ctypes import wintypes
import http.client
import json
from pathlib import Path
import queue
import threading
import time


def frontend_window(pid):
    """Find and rename only the known frontend PID; no focus or geometry changes."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SetThreadDpiAwarenessContext.argtypes=[wintypes.HANDLE]
    user.SetThreadDpiAwarenessContext.restype=wintypes.HANDLE
    dpi_context=user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    windows = []
    @callback_type
    def visit(hwnd, unused):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or user.GetWindow(hwnd, 4):
            return True
        title, rect, client = ctypes.create_unicode_buffer(256), wintypes.RECT(), wintypes.RECT()
        user.GetWindowTextW(hwnd, title, len(title))
        if title.value not in ("AutoSubs", "AUTOCATCHSUBS"):
            return True
        if title.value != "AUTOCATCHSUBS":
            user.SetWindowTextW(hwnd, "AUTOCATCHSUBS")
        if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        user.GetClientRect(hwnd, ctypes.byref(client))
        # GetWindowRect includes Windows' invisible resize margin. Attach to
        # the visible DWM frame so the tab meets the border without a gap.
        frame = wintypes.RECT(rect.left, rect.top, rect.right, rect.bottom)
        try:
            dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
            dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
            visible_frame = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(visible_frame), ctypes.sizeof(visible_frame)) == 0:
                if visible_frame.right > visible_frame.left and visible_frame.bottom > visible_frame.top:
                    frame = visible_frame
        except OSError:
            pass
        windows.append({"hwnd":int(hwnd), "title":"AUTOCATCHSUBS", "x":rect.left,"y":rect.top,
            "width":rect.right-rect.left,"height":rect.bottom-rect.top,
            "frameLeft":frame.left,"frameTop":frame.top,"frameRight":frame.right,"frameBottom":frame.bottom,
            "clientWidth":client.right-client.left,"clientHeight":client.bottom-client.top,
            "visible":bool(user.IsWindowVisible(hwnd)),"minimized":bool(user.IsIconic(hwnd))})
        return False
    try:user.EnumWindows(visit, 0)
    finally:
        if dpi_context:user.SetThreadDpiAwarenessContext(dpi_context)
    return windows[0] if windows else None


def dock_geometry(window, opened):
    """Attach to the visible right border without changing the main window."""
    right = window.get("frameRight", window["x"] + window["width"])
    top = window.get("frameTop", window["y"])
    bottom = window.get("frameBottom", window["y"] + window["height"])
    return (right, top if opened else bottom - 28,
            360 if opened else 104, max(220,bottom-top) if opened else 28)


def format_report(data, warning=""):
    changes = "\n".join(data.get("changes", []))
    ui = "\n".join(data.get("ui", []))
    return (f"AUTOCATCHSUBS · {data.get('revision','')}\n\n[CHANGELOG]\n{changes}\n\n"
        f"[SYSTEM_INFO] Text+: {data.get('templates',0)}\n\n[CONTROLLER]\n{data.get('controller','')}"
        f"\n\n[APP]\n{data.get('app','')}\n\n[UI]\n{ui}\n{warning}")


class ConsoleDock:
    def __init__(self, frontend_pid, resolve_pid, controller_pid, control_port=56103, app_port=56102, probe_file=None):
        dpi_user=ctypes.WinDLL("user32",use_last_error=True)
        dpi_user.SetProcessDpiAwarenessContext.argtypes=[wintypes.HANDLE]
        dpi_user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        import tkinter as tk
        self.tk, self.frontend_pid = tk, frontend_pid
        self.control_port, self.app_port = control_port, app_port
        self.probe_file = Path(probe_file) if probe_file else (Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent) / "state/console-window.json"
        self.stop, self.expanded, self.updates = threading.Event(), threading.Event(), queue.Queue(maxsize=12)
        self.report, self.opened, self.owner, self.last_geometry, self.last_probe = "Esperando registros…", False, None, None, None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handles = [self.kernel.OpenProcess(0x100000,False,pid) for pid in (frontend_pid,resolve_pid,controller_pid)]
        if not all(self.handles):
            raise RuntimeError("No se pudo vincular Console a la sesión propia")
        self.root = tk.Tk(); self.root.withdraw()
        self.window = tk.Toplevel(self.root); self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.title("AUTOCATCHSUBS · Console")
        self.window.configure(bg="#3b82f6")
        self.compact = tk.Frame(self.window,bg="#151b26")
        self.toggle = tk.Button(self.compact,text=">_ Console ▸",command=lambda:self.send_open(True),
            bg="#151b26",fg="#b9d5ff",activebackground="#202d43",activeforeground="#d7e0eb",
            relief="flat",borderwidth=0,font=("Segoe UI",9),cursor="hand2")
        self.toggle.pack(fill="both",expand=True)
        self.panel = tk.Frame(self.window,bg="#101318")
        header = tk.Frame(self.panel,bg="#151b26"); header.pack(fill="x")
        tk.Label(header,text=">_  AUTOCATCHSUBS · Console",bg="#151b26",fg="#9ec7ff",font=("Segoe UI",9,"bold")).pack(side="left",padx=8,pady=8)
        self.copy = tk.Button(header,text="Copiar Log",command=self.copy_log,bg="#1b2432",fg="#d7e0eb",
            activebackground="#202d43",activeforeground="#d7e0eb",relief="flat",font=("Segoe UI",9))
        self.copy.pack(side="right",padx=5,pady=5)
        tk.Button(header,text="×",command=lambda:self.send_open(False),bg="#151b26",fg="#b9d5ff",
            activebackground="#202d43",activeforeground="#d7e0eb",relief="flat",font=("Segoe UI",11)).pack(side="right",padx=3)
        body = tk.Frame(self.panel,bg="#101318"); body.pack(fill="both",expand=True)
        self.text = tk.Text(body,wrap="word",bg="#101318",fg="#d7e0eb",insertbackground="#60a5fa",
            selectbackground="#253b5e",relief="flat",borderwidth=0,font=("Consolas",9),padx=10,pady=10)
        scrollbar = tk.Scrollbar(body,command=self.text.yview,bg="#202d43")
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right",fill="y"); self.text.pack(fill="both",expand=True)
        for tag,color in (("error","#ef6068"),("warn","#e6b85c"),("info","#9ec7ff")):
            self.text.tag_configure(tag,foreground=color)
        self.text.configure(state="disabled")
        self.window.protocol("WM_DELETE_WINDOW",lambda:self.send_open(False))
        self.compact.pack(fill="both",expand=True,padx=1,pady=1)
        self.window.update_idletasks()
        user=ctypes.WinDLL("user32",use_last_error=True)
        user.GetParent.argtypes=[wintypes.HWND]; user.GetParent.restype=wintypes.HWND
        self.hwnd=int(user.GetParent(self.window.winfo_id()) or self.window.winfo_id())
        self.user=user
        user.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
        user.SetWindowLongPtrW.restype=ctypes.c_ssize_t
        user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        self.worker=threading.Thread(target=self.poll,daemon=True); self.worker.start()
        self.root.after(50,self.tick)

    def request(self, func, port, **values):
        connection=http.client.HTTPConnection("127.0.0.1",port,timeout=1.5)
        try:
            connection.request("POST","/",json.dumps(dict(func=func,**values)),{"Content-Type":"application/json"})
            result=json.loads(connection.getresponse().read(1024*1024))
            if result.get("error"): raise RuntimeError(result.get("detail") or result.get("message"))
            return result
        finally: connection.close()

    def publish(self, kind, value):
        try:self.updates.put_nowait((kind,value))
        except queue.Full:pass

    def poll(self):
        next_status,next_logs=0,0
        while not self.stop.is_set():
            if any(self.kernel.WaitForSingleObject(handle,0)!=258 for handle in self.handles):
                self.publish("exit",None); return
            now=time.monotonic()
            if now>=next_status:
                next_status=now+.5
                try:self.publish("state",self.request("Status",self.control_port))
                except Exception as error:self.publish("warning","[SYSTEM_WARN] "+str(error))
            if self.expanded.is_set() and now>=next_logs:
                next_logs=now+2.5
                try:self.publish("logs",format_report(self.request("GetDiagnostics",self.app_port)))
                except Exception as error:self.publish("warning","[SYSTEM_WARN] "+str(error))
            self.stop.wait(.15)

    def send_open(self, opened):
        def send():
            try:self.publish("state",self.request("SetConsoleOpen",self.control_port,open=opened))
            except Exception as error:self.publish("warning","[SYSTEM_WARN] "+str(error))
        threading.Thread(target=send,daemon=True).start()

    def set_state(self, state):
        if state.get("pid") != self.frontend_pid:return
        # Read the visible frame locally, including with an already-running
        # controller that predates frame coordinates. No backend restart.
        window=frontend_window(self.frontend_pid) if state.get("window") else None
        if not window or not window.get("visible") or window.get("minimized"):
            self.window.withdraw()
            if self.last_probe and self.last_probe.get("visible"):
                self.last_probe=dict(self.last_probe,visible=False)
                try:self.probe_file.write_text(json.dumps(self.last_probe),encoding="utf-8")
                except OSError:pass
            return
        if self.owner!=window["hwnd"]:
            self.user.SetWindowLongPtrW(self.hwnd,-8,window["hwnd"])
            self.owner=window["hwnd"]
        opened=bool(state.get("consoleOpen"))
        if opened!=self.opened:
            self.opened=opened
            if opened:
                self.compact.pack_forget(); self.panel.pack(fill="both",expand=True,padx=1,pady=1); self.expanded.set()
            else:
                self.panel.pack_forget(); self.compact.pack(fill="both",expand=True,padx=1,pady=1); self.expanded.clear()
            self.last_geometry=None
        geometry=dock_geometry(window,opened)
        self.window.deiconify()
        if geometry!=self.last_geometry:
            x,y,width,height=geometry
            self.window.geometry(f"{width}x{height}{x:+d}{y:+d}")
            self.window.update_idletasks()
            self.user.SetWindowPos(self.hwnd,None,x,y,width,height,0x4|0x10)
            self.last_geometry=geometry
        probe={"pid":self.frontend_pid,"owner":self.owner,"consoleHwnd":self.hwnd,"open":opened,
            "geometry":list(geometry),"mainWindow":window,"visible":True,
            "logCharacters":len(self.report),"containsError":"[AUTOCATCHSUBS_ERROR]" in self.report}
        if probe!=self.last_probe:
            try:
                self.probe_file.parent.mkdir(parents=True,exist_ok=True)
                self.probe_file.write_text(json.dumps(probe),encoding="utf-8")
                self.last_probe=probe
            except OSError:pass

    def update_report(self, report):
        if report==self.report:return
        self.report=report
        position=self.text.yview(); follow=position[1]>=.99
        selection=self.text.tag_ranges("sel")
        self.text.configure(state="normal"); self.text.delete("1.0","end")
        for line in report.splitlines(keepends=True):
            tag="error" if "[AUTOCATCHSUBS_ERROR]" in line else "warn" if "[SYSTEM_WARN]" in line else "info" if "[SYSTEM_INFO]" in line else ""
            self.text.insert("end",line,tag)
        if len(selection)==2:self.text.tag_add("sel",*selection)
        self.text.configure(state="disabled")
        if follow:self.text.see("end")
        else:self.text.yview_moveto(position[0])

    def copy_log(self):
        self.root.clipboard_clear(); self.root.clipboard_append(self.report)
        self.copy.configure(text="Copiado ✓")
        self.root.after(1800,lambda:self.copy.configure(text="Copiar Log"))

    def tick(self):
        if self.stop.is_set():return
        for _ in range(24):
            try:kind,value=self.updates.get_nowait()
            except queue.Empty:break
            if kind=="exit":self.close(); return
            if kind=="state":self.set_state(value)
            elif kind=="logs":self.update_report(value)
            elif kind=="warning":self.update_report(self.report+"\n"+value)
        self.root.after(75,self.tick)

    def close(self):
        self.stop.set()
        for handle in self.handles:
            if handle:self.kernel.CloseHandle(handle)
        self.root.destroy()

    def run(self):self.root.mainloop()


def main():
    parser=argparse.ArgumentParser()
    for name in ("frontend-pid","resolve-pid","controller-pid"):
        parser.add_argument("--"+name,type=int,required=True)
    parser.add_argument("--control-port",type=int,default=56103)
    parser.add_argument("--app-port",type=int,default=56102)
    parser.add_argument("--probe-file")
    args=parser.parse_args()
    ConsoleDock(args.frontend_pid,args.resolve_pid,args.controller_pid,args.control_port,args.app_port,args.probe_file).run()


if __name__=="__main__":main()
