"""Assemble an unsigned JR candidate from this checkout and verified build outputs."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'AUTOCATCHSUBS-licensing'))
from build_diagnostic import write as diagnostic

def main():
    package = ROOT / 'AUTOCATCHSUBS-packages/jr'
    native = ROOT / 'AUTOCATCHSUBS-release-binaries/jr'
    backend = ROOT / 'AUTOCATCHSUBS-backend-dist/jr/AUTOCATCHSUBSBackend'
    assert (native / 'AUTOCATCHSUBS.exe').stat().st_size > 1_000_000
    assert (backend / 'AUTOCATCHSUBSBackend.exe').is_file()
    shutil.copytree(native, package, dirs_exist_ok=True)
    shutil.copytree(backend, package, dirs_exist_ok=True)
    shutil.copy2(ROOT / 'AUTOCATCHSUBS-release-source/binaries/ffmpeg-x86_64-pc-windows-msvc.exe', package / 'ffmpeg.exe')
    crt = Path(os.environ['VCToolsRedistDir']) / 'x64/Microsoft.VC143.CRT'
    dlls = list(crt.glob('*.dll'))
    if not dlls:
        raise RuntimeError('VC++ runtime libraries missing')
    for dll in dlls:
        shutil.copy2(dll, package / dll.name)
    loader = Path(os.environ['WINDIR']) / 'System32/vulkan-1.dll'
    if not loader.is_file():
        raise RuntimeError('Official Vulkan loader missing')
    shutil.copy2(loader, package / loader.name)
    shutil.copy2(ROOT / 'AUTOCATCHSUBS-build-tools/LICENSE-Vulkan-Loader.txt', package / 'LICENSE-Vulkan.txt')
    notices = package / 'third-party/ffmpeg'
    notices.mkdir(parents=True, exist_ok=True)
    ffroot = next((ROOT / 'AUTOCATCHSUBS-build-tools/ffmpeg').iterdir())
    for item in ffroot.iterdir():
        if item.name == 'bin':
            continue
        if item.is_dir():
            shutil.copytree(item, notices / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, notices / item.name)
    lock = json.loads((ROOT / 'tools/ci-dependencies.json').read_text())
    (notices / 'SOURCE-PROVENANCE.txt').write_text(
        'Upstream FFmpeg binary, not signed using the AUTOCATCHSUBS identity.\n'
        + lock['ffmpeg']['url'] + '\nBuild scripts: ' + lock['ffmpeg']['sources']
        + '\nFFmpeg source revision: 330caae0c1 (n8.1.3-14).\n'
        + 'https://github.com/FFmpeg/FFmpeg/tree/330caae0c1\n'
        + 'Third-party license/source compliance must be reviewed before a production release.\n', encoding='utf-8')
    for name in ('LICENSE', 'PRIVACY.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, package / name)
    (package / 'ABRIR AUTOCATCHSUBS.cmd').write_text('@echo off\nstart "" "%~dp0AUTOCATCHSUBSBackend.exe"\n', encoding='ascii')
    diagnostic(package / 'DIAGNOSTICO AUTOCATCHSUBS.cmd', 'jr')
    files = {}
    forbidden = ('owner.dpapi', 'licenses.enc', 'codes-private', 'admin_token', 'private_pkcs8')
    for file in package.rglob('*'):
        if not file.is_file():
            continue
        if any(value in file.name.lower() for value in forbidden) or file.suffix == '.py' or 'state' in file.relative_to(package).parts:
            raise RuntimeError('Private data or mutable state in package')
        if file.name != 'manifest.json':
            files[file.relative_to(package).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    (package / 'manifest.json').write_text(json.dumps({'edition':'jr','version':'3.8.11','signed':False,'files':files}, indent=2), encoding='utf-8')
    print(f'JR unsigned candidate assembled: {len(files)} files; no activation performed.')

if __name__ == '__main__':
    main()
