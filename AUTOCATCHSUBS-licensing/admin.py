"""Private local Admin tool. Never include this folder/vault in a Player package."""
from __future__ import annotations
import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import secrets
import urllib.request
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from player import PRODUCT, LicenseError, atomic_json, canonical

AAD = b'AUTOCATCHSUBS-VAULT-v1'
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def code():
    return '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4))


def code_hash(value):
    return hashlib.sha256((PRODUCT + '\0' + value).encode()).hexdigest()


def b64(value):
    return base64.b64encode(value).decode('ascii')


class Vault:
    def __init__(self, path, password, data=None):
        if len(password) < 12:
            raise LicenseError('La contraseña debe tener al menos 12 caracteres')
        self.path, self.password = Path(path), password
        if data is not None:
            self.data = data
            return
        try:
            envelope = json.loads(self.path.read_text(encoding='utf-8'))
            salt = base64.b64decode(envelope['salt'], validate=True)
            key = Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(password.encode())
            plain = AESGCM(key).decrypt(base64.b64decode(envelope['nonce'], validate=True),
                base64.b64decode(envelope['ciphertext'], validate=True), AAD)
            self.data = json.loads(plain)
            if self.data['product'] != PRODUCT:
                raise ValueError('product')
        except Exception as error:
            raise LicenseError('Contraseña incorrecta o bóveda dañada') from error

    @classmethod
    def create(cls, path, password):
        path = Path(path)
        if path.exists():
            raise LicenseError('La bóveda ya existe; no se regeneran identidad ni códigos')
        key = Ed25519PrivateKey.generate()
        entries, used = [], set()
        for index in range(1, 101):
            value = code()
            while value in used:
                value = code()
            used.add(value)
            entries.append({'id': f'ACS-{index:03d}', 'code': value, 'generation': 1})
        vault = cls(path, password, {'product': PRODUCT, 'schema': 1,
            'private_pkcs8': b64(key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())),
            'public_key': b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)),
            'admin_token': secrets.token_urlsafe(48), 'entries': entries})
        vault.save()
        return vault

    def save(self):
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        key = Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(self.password.encode())
        cipher = AESGCM(key).encrypt(nonce, canonical(self.data), AAD)
        atomic_json(self.path, {'schema': 1, 'salt': b64(salt), 'nonce': b64(nonce), 'ciphertext': b64(cipher)})

    def export_codes(self, path):
        path = Path(path)
        if path.exists():
            raise LicenseError('El respaldo de códigos ya existe; elige otro nombre')
        with path.open('x', encoding='utf-8') as stream:
            stream.write('AUTOCATCHSUBS — LISTA PRIVADA ADMIN. NO DISTRIBUIR.\n')
            for entry in self.data['entries']:
                stream.write(f"{entry['id']} | {entry['code']} | generación {entry['generation']}\n")

    def public_config(self, endpoint):
        from player import Player
        Player(Path('.'), self.data['public_key'], '0'*64, endpoint)
        return {'product': PRODUCT, 'schema': 1, 'endpoint': endpoint.rstrip('/'), 'public_key': self.data['public_key']}

    def post(self, endpoint, operation, data):
        self.public_config(endpoint)
        request = urllib.request.Request(endpoint.rstrip('/') + '/admin/' + operation,
            data=canonical(data), headers={'Content-Type': 'application/json', 'User-Agent': 'AUTOCATCHSUBS-Admin/3.8.10', 'Authorization': 'Bearer ' + self.data['admin_token']})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(131073)
            if len(raw) > 131072:
                raise LicenseError('Respuesta demasiado grande')
            return json.loads(raw)

    def seed(self, endpoint):
        entries = self.data['entries']
        for start in range(0, len(entries), 20):
            self.post(endpoint, 'seed', {'seats': [{'id': x['id'], 'code_hash': code_hash(x['code'])} for x in entries[start:start+20]]})

def main():
    parser = argparse.ArgumentParser(description='Herramienta privada de licencias AUTOCATCHSUBS')
    parser.add_argument('operation', choices=('init', 'export', 'seed', 'list', 'revoke', 'alias', 'config'))
    parser.add_argument('--vault', type=Path, required=True)
    parser.add_argument('--endpoint')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--id')
    parser.add_argument('--alias', default='')
    args = parser.parse_args()
    password = getpass.getpass('Contraseña de la bóveda (no se mostrará): ')
    if args.operation == 'init':
        if password != getpass.getpass('Repite la contraseña: '):
            raise LicenseError('Las contraseñas no coinciden')
        Vault.create(args.vault, password)
        print('Bóveda creada con 100 códigos propios. Ningún código ni secreto se imprime.')
        return
    vault = Vault(args.vault, password)
    if args.operation == 'export':
        if not args.output:
            parser.error('--output requerido')
        vault.export_codes(args.output)
    elif args.operation == 'config':
        if not args.output or not args.endpoint:
            parser.error('--output y --endpoint requeridos')
        atomic_json(args.output, vault.public_config(args.endpoint))
    elif args.operation == 'seed':
        vault.seed(args.endpoint)
    elif args.operation == 'list':
        data = vault.post(args.endpoint, 'list', {})
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        vault.post(args.endpoint, args.operation, {'id': args.id, 'alias': args.alias})
    print('Operación completada. Guarda un respaldo actualizado de la bóveda.')


if __name__ == '__main__':
    main()
