# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Users/Documents/ChatGPT/New project 2/AUTOCATCHSUBS-backend-source/admin/backend_entry.py'],
    pathex=['C:/Users/Users/Documents/ChatGPT/New project 2/AUTOCATCHSUBS-backend-source/admin'],
    binaries=[],
    datas=[],
    hiddenimports=['backports.zstd', 'admin_ui', 'owner_store', 'license_simulator'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'numpy', 'pandas', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AUTOCATCHSUBSBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AUTOCATCHSUBSBackend',
)
