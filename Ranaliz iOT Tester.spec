# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
# SPECPATH is injected by PyInstaller when executing the spec
project_dir = Path(SPECPATH)

extra_datas = []
extra_binaries = []
extra_hiddenimports = []
for pkg in ('paho', 'zigpy', 'zigpy_znp', 'bellows', 'zigpy_deconz'):
    d, b, h = collect_all(pkg)
    extra_datas += d
    extra_binaries += b
    extra_hiddenimports += h
    extra_hiddenimports += collect_submodules(pkg)

a = Analysis(
    ['main.py'],
    pathex=[str(project_dir)],
    binaries=extra_binaries,
    datas=[
        ('logo512.png', '.'),
        ('assets/chevron_down.svg', 'assets'),
        ('assets/chevron_up.svg', 'assets'),
        ('assets/flag_en.svg', 'assets'),
        ('assets/flag_tr.svg', 'assets'),
        ('assets/flag_sa.svg', 'assets'),
    ] + extra_datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'pymodbus',
        'serial',
        'c104',
        'openpyxl',
        'branding',
        'theme',
        'i18n',
        'history_cache',
        'dialogs',
        'formats',
        'excel_export',
        'modbus_worker',
        'iec104_worker',
        'mqtt_worker',
        'zigbee_worker',
        'mqtt_zigbee_panels',
        'paho',
        'paho.mqtt',
        'paho.mqtt.client',
        'zigpy',
        'zigpy_znp',
        'bellows',
        'zigpy_deconz',
        'zigpy_znp.zigbee.application',
        'bellows.zigbee.application',
        'zigpy_deconz.zigbee.application',
    ] + extra_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=['matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Ranaliz iOT Tester',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='AppIcon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Ranaliz iOT Tester',
)

app = BUNDLE(
    coll,
    name='Ranaliz iOT Tester.app',
    icon='AppIcon.icns',
    bundle_identifier='com.ranaliz.iot-tester',
    info_plist={
        'CFBundleName': 'Ranaliz iOT Tester',
        'CFBundleDisplayName': 'Ranaliz iOT Tester',
        'CFBundleShortVersionString': '1.0.0',
        'NSMainNibFile': '',
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.13.0',
    },
)
