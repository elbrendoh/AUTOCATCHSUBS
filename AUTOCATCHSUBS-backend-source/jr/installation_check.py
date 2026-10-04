"""Offline dependency check; never activates, revokes or changes a license."""
import json
from pathlib import Path
import subprocess
import sys

def check(root):
    import tkinter
    from backports.zstd import compress
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from autocatchsubs_catalog import generator_fields
    from release_config import ADMIN
    raw=b'\x32\x05Text+'
    blob=b'\0\0\0\2'+len(raw).to_bytes(4,'big')+b'\x81'+compress(raw)
    assert generator_fields(blob)[6]==b'Text+'
    assert tkinter.Tcl().eval('info patchlevel')
    result=subprocess.run([str(root/'AUTOCATCHSUBS.exe'),'--autocatch-check-license'],
        cwd=root,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    # A new JR install must pass without a license. Exit 23 means its verifier
    # loaded successfully, not that it activated or bypassed any guard.
    if result.returncode not in (0,23):
        raise RuntimeError('El cliente nativo no pudo iniciar; exit='+str(result.returncode))
    state=root/'state';state.mkdir(exist_ok=True)
    probe=state/'installation-write-check.tmp'
    probe.write_text('ok',encoding='ascii');probe.unlink()
    return {'passed':True,'edition':'admin' if ADMIN else 'jr',
            'native_exit':result.returncode,'runtime':True,'writable_state':True,
            'activation_performed':False}

def main(output):
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    try:result=check(root)
    except Exception as error:
        result={'passed':False,'error':str(error),'win32':getattr(error,'winerror',None)}
    Path(output).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return 0 if result['passed'] else 1
