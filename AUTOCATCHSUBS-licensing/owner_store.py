"""Owner-only store. Excluded from the JR application and installer."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import secrets
from admin import Vault

class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def dpapi(value, decrypt=False):
    buffer = ctypes.create_string_buffer(value)
    incoming = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(incoming), 'AUTOCATCHSUBS Admin', None, None, None, 1, ctypes.byref(outgoing))
    if not ok:
        raise OSError('Windows no pudo abrir la bóveda privada de este usuario')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.data)

def open_vault(root, create=False):
    root = Path(root)
    key = root / 'owner.dpapi'
    path = root / 'licenses.enc.json'
    if key.exists():
        password = dpapi(key.read_bytes(), True).decode('ascii')
        return Vault(path, password)
    if not create or path.exists():
        raise RuntimeError('Bóveda Admin no configurada; no se regenera ninguna identidad')
    root.mkdir(parents=True, exist_ok=True)
    # The randomly generated password is wrapped for this Windows user only.
    password = secrets.token_urlsafe(48)
    vault = Vault.create(path, password)
    with key.open('xb') as stream:
        stream.write(dpapi(password.encode('ascii')))
    vault.export_codes(root / 'codes-private.txt')
    return vault
