import os
from pathlib import Path
import subprocess
import sys
BASE=Path(__file__).resolve().parents[1]
edition=sys.argv[1]
assert edition in ('admin','jr')
(BASE/'AUTOCATCHSUBS-build-tools').mkdir(parents=True,exist_ok=True)
args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','AUTOCATCHSUBSBackend',
      '--distpath',str(BASE/'AUTOCATCHSUBS-backend-dist'/edition),
      '--workpath',str(BASE/'AUTOCATCHSUBS-build-tools'/('pyinstaller-'+edition)),
      '--specpath',str(BASE/'AUTOCATCHSUBS-backend-source'/edition),
      '--paths',str(BASE/'AUTOCATCHSUBS-backend-source'/edition)]
for name in ['PySide6','numpy','pandas','matplotlib']:args+=['--exclude-module',name]
args+=['--hidden-import','backports.zstd']
if edition=='admin':
    for name in ['admin_ui','owner_store','license_simulator']:args+=['--hidden-import',name]
args+=[str(BASE/'AUTOCATCHSUBS-backend-source'/edition/'backend_entry.py')]
with (BASE/'AUTOCATCHSUBS-build-tools'/('backend-'+edition+'-build.log')).open('w',encoding='utf-8') as log:
    subprocess.run(args,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Runtime con soporte Text+ comprimido compilado:',edition)
