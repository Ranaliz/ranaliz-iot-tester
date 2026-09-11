#!/usr/bin/env python3
"""Write the Windows PyInstaller .spec next to the project root."""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    icon = "AppIcon.ico" if (root / "AppIcon.ico").is_file() else "logo512.png"
    spec_path = root / "Ranaliz iOT Tester.spec"

    # Verify Zigbee/MQTT packages are importable in this interpreter
    try:
        import zigpy  # noqa: F401
        import zigpy_znp  # noqa: F401
        import bellows  # noqa: F401
        import zigpy_deconz  # noqa: F401
        import paho.mqtt.client  # noqa: F401
    except ImportError as e:
        print(f"Missing Zigbee/MQTT package: {e}", file=sys.stderr)
        print("Run: python -m pip install -r requirements.txt", file=sys.stderr)
        return 1

    spec = f"""# -*- mode: python ; coding: utf-8 -*-
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
    hooksconfig={{}},
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Ranaliz iOT Tester',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='{icon}',
)
"""
    spec_path.write_text(spec, encoding="utf-8")
    print(f"Wrote {spec_path.name} (icon={icon})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
