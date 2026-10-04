"""Public verification only. Player never receives a signing key or code list."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PRODUCT = 'AUTOCATCHSUBS'


class LicenseError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify(envelope, public_key, kind):
    try:
        payload = envelope['payload']
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(envelope['signature'], validate=True), canonical(payload))
        if payload.get('product') != PRODUCT or payload.get('schema') != 1 or payload.get('kind') != kind:
            raise ValueError('product')
        if not re.fullmatch(r'ACS-\d{3}', payload.get('license_id', '')):
            raise ValueError('id')
        if type(payload.get('generation')) is not int or payload['generation'] < 1:
            raise ValueError('generation')
        if not re.fullmatch(r'[a-f0-9]{64}', payload.get('hwid', '')):
            raise ValueError('hwid')
        return payload
    except (KeyError, TypeError, ValueError, InvalidSignature) as error:
        raise LicenseError('Licencia inválida, de otro producto o firma alterada') from error


def fingerprint(parts):
    values = {key: str(parts.get(key, '')).strip().upper() for key in ('cpu', 'disk', 'windows_install')}
    if not all(values.values()):
        raise LicenseError('No se pudieron leer CPU, disco de Windows e identidad de instalación')
    return hashlib.sha256(b'AUTOCATCH-HWID-v1\0' + canonical(values)).hexdigest()


def current_hwid():
    import subprocess
    if os.name != 'nt':
        raise LicenseError('La activación de producción requiere Windows')
    script = r'''
$ErrorActionPreference='Stop'
$acsCpu=@(Get-CimInstance Win32_Processor | ForEach-Object {$_.ProcessorId} | Sort-Object)
$acsPartition=Get-Partition -DriveLetter $env:SystemDrive.Substring(0,1)
$acsDisk=$acsPartition | Get-Disk
$acsInstallation=(Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid).MachineGuid
@{cpu=($acsCpu -join '|');disk=$acsDisk.SerialNumber;windows_install=$acsInstallation} | ConvertTo-Json -Compress
'''
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=30, creationflags=0x08000000, check=True)
        return fingerprint(json.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise LicenseError('Windows no permitió leer el identificador del equipo') from error


class Player:
    def __init__(self, state, public_key, hwid, endpoint):
        if not re.fullmatch(r'[a-f0-9]{64}', hwid):
            raise LicenseError('HWID inválido')
        url = urllib.parse.urlsplit(endpoint)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise LicenseError('La activación requiere un servicio HTTPS configurado')
        self.state, self.public_key, self.hwid = Path(state), public_key, hwid
        self.endpoint = endpoint.rstrip('/')
        self.activation = self.state / 'activation.json'
        self.status_file = self.state / 'verified-status.json'

    def _read(self, path):
        return json.loads(path.read_text(encoding='utf-8'))

    def validate(self, envelope):
        payload = verify(envelope, self.public_key, 'activation')
        if payload['hwid'] != self.hwid:
            raise LicenseError('La licencia está vinculada a otro equipo o instalación de Windows')
        if self.status_file.exists():
            # Persist signed negative proofs; never unlock one by going offline.
            saved = self._read(self.status_file)
            for proof in saved.get('blocked', []):
                blocked = verify(proof, self.public_key, 'status')
                if blocked['hwid'] == self.hwid and blocked['license_id'] == payload['license_id'] and blocked['generation'] == payload['generation'] and blocked.get('active') is False:
                    raise LicenseError('Licencia revocada; solicita una nueva activación')
        return payload

    def require_active(self):
        try:
            return self.validate(self._read(self.activation))
        except OSError as error:
            raise LicenseError('Activa AUTOCATCHSUBS antes de iniciar este trabajo') from error

    def _post(self, path, payload):
        request = urllib.request.Request(self.endpoint + path, data=canonical(payload),
            headers={'Content-Type': 'application/json', 'User-Agent': 'AUTOCATCHSUBS-JR/3.8.10'}, method='POST')
        try:
            # Disallow redirects: a code must never be sent to an unconfigured host.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=8) as response:
                raw = response.read(32769)
                if len(raw) > 32768:
                    raise LicenseError('Respuesta de activación demasiado grande')
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code in (400, 409):
                raise LicenseError('Código inválido, revocado o vinculado a otro equipo') from error
            raise LicenseError('Servicio no disponible; reintenta con el mismo código') from error
        except (OSError, ValueError) as error:
            raise LicenseError('No se pudo conectar al servicio de activación') from error

    def activate(self, code, computer='', profile_name=''):
        code = str(code).strip().upper()
        if not re.fullmatch(r'[A-HJ-NP-Z2-9]{4}(?:-[A-HJ-NP-Z2-9]{4}){3}', code):
            raise LicenseError('Usa un código XXXX-XXXX-XXXX-XXXX')
        envelope = self._post('/v1/activate', {'product': PRODUCT, 'code': code, 'hwid': self.hwid,
                             'computer': str(computer)[:128], 'profile_name': str(profile_name)[:128]})
        payload = self.validate(envelope)
        atomic_json(self.activation, envelope)
        return payload

    def check_online(self):
        """Offline remains valid. Only signed, fresh status can revoke access."""
        active = self.require_active()
        nonce = secrets.token_hex(32)
        try:
            response = self._post('/v1/check', {'activation': self._read(self.activation), 'hwid': self.hwid, 'nonce': nonce})
            payload = verify(response, self.public_key, 'status')
            if any(payload.get(k) != v for k, v in {'hwid': self.hwid, 'nonce': nonce,
                    'license_id': active['license_id'], 'generation': active['generation']}.items()):
                raise LicenseError('Respuesta no corresponde a este equipo y consulta')
            if type(payload.get('active')) is not bool or type(payload.get('sequence')) is not int or payload['sequence'] < 0:
                raise LicenseError('Estado firmado inválido')
            saved = self._read(self.status_file) if self.status_file.exists() else {'sequence': 0, 'blocked': []}
            if payload['sequence'] < saved['sequence']:
                raise LicenseError('Se rechazó un estado anterior')
            saved['sequence'] = payload['sequence']
            if not payload['active']:
                saved['blocked'].append(response)
            atomic_json(self.status_file, saved)
        except (LicenseError, OSError, ValueError, KeyError):
            return {'active': True, 'online': False}
        if not payload['active']:
            return {'active': False, 'online': True}
        return {'active': True, 'online': True}
