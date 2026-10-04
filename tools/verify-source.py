"""Check readable sources without executing a license operation or contacting Resolve."""
import ast
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
python_files = list((ROOT / 'AUTOCATCHSUBS-backend-source').rglob('*.py'))
python_files += list((ROOT / 'AUTOCATCHSUBS-licensing').glob('*.py'))
python_files += list((ROOT / 'tools').rglob('*.py'))
for file in python_files:
    ast.parse(file.read_text(encoding='utf-8-sig'), filename=str(file))
for relative in ('AUTOCATCHSUBS-licensing/activation.js',
                 'AUTOCATCHSUBS-licensing/service/worker.mjs',
                 'ui/overrides/patch_ui.cjs', 'tools/build-ui.cjs'):
    subprocess.run(['node', '--check', str(ROOT / relative)], check=True)
subprocess.run(['node', str(ROOT / 'ui/overrides/patch_ui.cjs')], check=True)
subprocess.run(['node', '--check', str(ROOT / 'ui/preview/assets/index-BRt8Z4DF.js')], check=True)
for edition in ('admin', 'jr'):
    config = json.loads((ROOT / f'AUTOCATCHSUBS-release-source/tauri.{edition}.json').read_text())
    assert config['build']['frontendDist'] == f'dist-{edition}'
print(f'Python parsed: {len(python_files)} files; JS and UI generator passed. No license activation performed.')
