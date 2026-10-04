"""Private Admin window; bundled only with AUTOCATCHSUBS Admin."""
import json
import os
from pathlib import Path
import queue
import threading
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from owner_store import open_vault
from release_config import ENDPOINT

def main():
    root=tk.Tk();root.title('AUTOCATCHSUBS · Gestión de licencias');root.geometry('850x510');root.minsize(710,410);root.configure(bg='#10141d')
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('Treeview',background='#17202e',foreground='#e6ecf5',fieldbackground='#17202e',rowheight=28)
    style.configure('Treeview.Heading',background='#253044',foreground='#e6ecf5')
    style.map('Treeview',background=[('selected','#2257a2')])
    tk.Label(root,text='AUTOCATCHSUBS · Licencias de editores',font=('Segoe UI',14,'bold'),bg='#10141d',fg='white').pack(anchor='w',padx=20,pady=(18,5))
    tk.Label(root,text='Un código · una PC · vínculo permanente. Revocar no libera el código.',bg='#10141d',fg='#9aaecb',font=('Segoe UI',10)).pack(anchor='w',padx=20,pady=(0,12))
    columns=('id','state','alias','computer','profile')
    frame=tk.Frame(root,bg='#10141d');frame.pack(fill='both',expand=True,padx=20)
    tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse')
    for col,title,width in zip(columns,('Código','Estado','Alias','Equipo','Editor'),(90,105,140,190,150)):
        tree.heading(col,text=title);tree.column(col,width=width,minwidth=65)
    scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');tree.pack(side='left',fill='both',expand=True)
    status=tk.StringVar(value='Conectando…')
    tk.Label(root,textvariable=status,bg='#10141d',fg='#aec2e4',anchor='w').pack(fill='x',padx=20,pady=10)
    bar=tk.Frame(root,bg='#10141d');bar.pack(fill='x',padx=20,pady=(0,16))
    updates=queue.Queue();cache={};busy=False;vault=None
    # The management window belongs to its frontend; do not leave an orphan helper.
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    owner=None
    if '--owner-pid' in sys.argv:
        owner=kernel.OpenProcess(0x100000,False,int(sys.argv[sys.argv.index('--owner-pid')+1]))
    try:vault=open_vault(Path(os.environ['LOCALAPPDATA'])/'AUTOCATCHSUBS-Admin')
    except Exception as error:status.set(str(error))
    def task(operation,data=None):
        nonlocal busy
        if busy or not vault:return
        busy=True;status.set('Consultando Cloudflare…')
        def work():
            try:
                if operation!='list':vault.post(ENDPOINT,operation,data or {})
                updates.put(('ok',vault.post(ENDPOINT,'list',{})['seats']))
            except Exception:updates.put(('error','No se pudo conectar. La lista anterior se conserva; pulsa Actualizar para reintentar.'))
        threading.Thread(target=work,daemon=True).start()
    def selected():
        keys=tree.selection();return cache.get(keys[0]) if keys else None
    def copy():
        row=selected()
        if not row or not vault:return
        if row['state']!='FREE':status.set('Ese código ya está consumido y no se puede rotar.');return
        code=next(x['code'] for x in vault.data['entries'] if x['id']==row['id'])
        root.clipboard_clear();root.clipboard_append(code);status.set('Código copiado. Entrégalo únicamente al editor asignado.')
    def alias():
        row=selected()
        if not row:return
        value=simpledialog.askstring('Alias','Nombre para identificar este código:',initialvalue=row.get('alias',''),parent=root)
        if value is not None:task('alias',{'id':row['id'],'alias':value[:128]})
    def revoke():
        row=selected()
        if not row or row['state']!='ACTIVE':status.set('Selecciona una licencia activa para revocar.');return
        if messagebox.askyesno('Revocar licencia',f"Revocar {row['id']} bloqueará ese editor cuando vuelva a conectarse. El código seguirá consumido y no se podrá reasignar. ¿Continuar?",parent=root):task('revoke',{'id':row['id']})
    def simulator():
        # Entirely isolated simulation; never changes a production seat.
        from license_simulator import simulate
        passed=simulate()
        messagebox.showinfo('Simulador aislado', 'Pruebas completadas:\n✓ Primer equipo aceptado\n✓ Segundo equipo rechazado\n✓ Reintento del mismo equipo conservado\n✓ Revocación bloquea y no libera\n\nNo se consumió ni modificó ningún código real.' if passed else 'La simulación detectó un fallo.',parent=root)
    for title,command in [('Actualizar',lambda:task('list')),('Copiar código',copy),('Editar alias',alias),('Revocar',revoke),('Simulador',simulator)]:
        tk.Button(bar,text=title,command=command,bg='#245dc0',fg='white',activebackground='#3475da',activeforeground='white',relief='flat',padx=12,pady=7).pack(side='left',padx=(0,7))
    def poll():
        nonlocal busy
        if owner and kernel.WaitForSingleObject(owner,0)!=258:
            kernel.CloseHandle(owner);root.destroy();return
        try:
            while True:
                kind,value=updates.get_nowait();busy=False
                if kind=='error':status.set(value);continue
                previous=tree.selection();tree.delete(*tree.get_children());cache.clear()
                labels={'FREE':'Libre','ACTIVE':'Activada','REVOKED':'Revocada'}
                for row in value:
                    cache[row['id']]=row;tree.insert('', 'end', iid=row['id'],values=(row['id'],labels.get(row['state'],row['state']),row.get('alias',''),row.get('computer',''),row.get('profile','')))
                if previous and previous[0] in cache:tree.selection_set(previous)
                status.set(f"{sum(x['state']=='FREE' for x in value)} libres · {sum(x['state']=='ACTIVE' for x in value)} activadas · {sum(x['state']=='REVOKED' for x in value)} revocadas")
        except queue.Empty:pass
        root.after(100,poll)
    task('list');poll();root.mainloop()

if __name__=='__main__':main()
