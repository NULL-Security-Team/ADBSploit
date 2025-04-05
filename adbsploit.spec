# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['adbsploit.py'],
    pathex=[],
    binaries=[],
    datas=[('app_icon.ico', '.'), ('platform-tools', 'platform-tools'), ('scrcpy', 'scrcpy')],
    hiddenimports=['PyQt6', 'patoolib'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6.QtWebEngine'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='adbsploit',
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
    icon=['app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='adbsploit',
)
