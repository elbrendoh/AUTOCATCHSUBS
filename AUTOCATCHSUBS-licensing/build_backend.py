import os
from pathlib import Path
import subprocess
import sys
BASE=Path(__file__).resolve().parents[1]
edition=sys.argv[1]
assert edition in ('admin','jr')
(BASE/'AUTOCATCHSUBS-build-tools').mkdir(parents=True,exist_ok=True)
version_file=BASE/'AUTOCATCHSUBS-build-tools'/('backend-'+edition+'-version.txt')
product='AUTOCATCHSUBS JR' if edition=='jr' else 'AUTOCATCHSUBS'
version_file.write_text('''VSVersionInfo(
 ffi=FixedFileInfo(filevers=(3,8,11,0),prodvers=(3,8,11,0),mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),
 kids=[StringFileInfo([StringTable('040904B0',[
  StringStruct('CompanyName','AUTOCATCH'),StringStruct('FileDescription',PRODUCT+' Backend'),
  StringStruct('FileVersion','3.8.11.0'),StringStruct('InternalName','AUTOCATCHSUBSBackend'),
  StringStruct('OriginalFilename','AUTOCATCHSUBSBackend.exe'),StringStruct('ProductName',PRODUCT),
  StringStruct('ProductVersion','3.8.11')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])
'''.replace('PRODUCT',repr(product)),encoding='utf-8')
args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','AUTOCATCHSUBSBackend',
      '--distpath',str(BASE/'AUTOCATCHSUBS-backend-dist'/edition),
      '--workpath',str(BASE/'AUTOCATCHSUBS-build-tools'/('pyinstaller-'+edition)),
      '--specpath',str(BASE/'AUTOCATCHSUBS-backend-source'/edition),
      '--paths',str(BASE/'AUTOCATCHSUBS-backend-source'/edition),'--version-file',str(version_file)]
for name in ['PySide6','numpy','pandas','matplotlib']:args+=['--exclude-module',name]
args+=['--hidden-import','backports.zstd']
if edition=='admin':
    for name in ['admin_ui','owner_store','license_simulator']:args+=['--hidden-import',name]
args+=[str(BASE/'AUTOCATCHSUBS-backend-source'/edition/'backend_entry.py')]
with (BASE/'AUTOCATCHSUBS-build-tools'/('backend-'+edition+'-build.log')).open('w',encoding='utf-8') as log:
    subprocess.run(args,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Runtime con soporte Text+ comprimido compilado:',edition)
