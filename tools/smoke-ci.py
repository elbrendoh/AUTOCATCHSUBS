"""Offline smoke checks for the built candidate; no Resolve or real license required."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
package = ROOT / 'AUTOCATCHSUBS-packages/jr'
manifest = json.loads((package / 'manifest.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest, name
result = subprocess.run([str(package / 'AUTOCATCHSUBS.exe'), '--autocatch-check-license'],
                        cwd=package, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
assert result.returncode == 23, f'JR must require activation on a clean runner, got {result.returncode}'
output = ROOT / 'AUTOCATCHSUBS-build-tools/installation-check-ci.json'
result = subprocess.run([str(package / 'AUTOCATCHSUBSBackend.exe'), '--installation-check', str(output)],
                        cwd=package, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
report = json.loads(output.read_text())
assert result.returncode == 0 and report['passed'] and report['native_exit'] == 23
assert not report['activation_performed']
audio=ROOT/'AUTOCATCHSUBS-build-tools/synthetic-audio.wav'
result=subprocess.run([str(package/'ffmpeg.exe'),'-hide_banner','-loglevel','error',
                       '-f','lavfi','-i','sine=frequency=800:duration=0.2',
                       '-ar','16000','-ac','1','-y',str(audio)],
                      cwd=package,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
assert result.returncode==0 and audio.read_bytes()[:4]==b'RIFF'
audio.unlink()
print('Manifest, JR guard, Text+ compression, Tcl/Tk, backend and FFmpeg conversion passed offline.')
