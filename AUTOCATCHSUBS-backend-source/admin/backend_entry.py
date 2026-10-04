"""Frozen entry point; one self-contained runtime per edition."""
import sys
from pathlib import Path

def main():
    if '--installation-check' in sys.argv:
        from installation_check import main as check
        return sys.exit(check(sys.argv[sys.argv.index('--installation-check')+1]))
    if '--self-test' in sys.argv:
        import json
        import tkinter
        from backports.zstd import compress
        from autocatchsubs_catalog import generator_fields
        from release_config import ADMIN
        from license_guard import require_active
        raw=b'\x32\x05Text+'
        blob=b'\0\0\0\2'+len(raw).to_bytes(4,'big')+b'\x81'+compress(raw)
        assert generator_fields(blob)[6]==b'Text+'
        tcl=tkinter.Tcl();assert tcl.eval('info patchlevel')
        try:require_active();active=True
        except Exception:active=False
        report={'passed':True,'edition':'admin' if ADMIN else 'jr','compressed_textplus':True,'tk_runtime':True,'license_active':active}
        if ADMIN:
            import importlib
            import os
            from release_config import ENDPOINT
            owner=importlib.import_module('owner_store')
            vault=owner.open_vault(Path(os.environ['LOCALAPPDATA'])/'AUTOCATCHSUBS-Admin')
            report['vault_codes']=len(vault.data['entries'])
            report['cloudflare_seats']=len(vault.post(ENDPOINT,'list',{})['seats'])
        Path(sys.argv[sys.argv.index('--self-test')+1]).write_text(json.dumps(report),encoding='utf-8')
        return
    if '--console' in sys.argv:
        sys.argv.remove('--console')
        from autocatchsubs_console import main
        return main()
    if '--licenses' in sys.argv:
        from release_config import ADMIN
        if not ADMIN:raise RuntimeError('Función exclusiva de Admin')
        # The JR build excludes this import and all private Admin modules.
        import importlib
        return importlib.import_module('admin_ui').main()
    from controller import main
    return main()

if __name__=='__main__':
    try:main()
    except Exception as error:
        import ctypes
        import json
        try:
            root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
            state=root/'state';state.mkdir(exist_ok=True)
            (state/'backend-error.json').write_text(json.dumps({'error':str(error),'type':type(error).__name__,'win32':getattr(error,'winerror',None)},ensure_ascii=False),encoding='utf-8')
        except OSError:
            pass
        ctypes.windll.user32.MessageBoxW(None,str(error),'AUTOCATCHSUBS',0x10)
        sys.exit(1)
