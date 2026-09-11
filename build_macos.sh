#!/bin/bash
# Build Ranaliz iOT Tester for macOS (.app bundle)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
cd "$PROJECT_DIR"

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON="$PROJECT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "Python 3 not found. Create .venv or install python3." >&2
  exit 1
fi

echo "Building macOS .app bundle with: $PYTHON"

# Zigbee/MQTT packages must live in the active env (do not rely on system-site only)
if ! "$PYTHON" -c "import zigpy, zigpy_znp, bellows, zigpy_deconz, paho.mqtt.client" 2>/dev/null; then
  echo "Missing Zigbee/MQTT packages in this Python env." >&2
  echo "Run: $PYTHON -m pip install -r requirements.txt" >&2
  exit 1
fi

# Clean previous builds
rm -rf build dist "Ranaliz iOT Tester.spec"

# Prefer .icns for macOS Dock; fall back to PNG if iconutil unavailable
ICON_PATH="logo512.png"
if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET_DIR="$(mktemp -d)/AppIcon.iconset"
  mkdir -p "$ICONSET_DIR"
  for sz in 16 32 128 256 512; do
    sips -z "$sz" "$sz" logo512.png --out "$ICONSET_DIR/icon_${sz}x${sz}.png" >/dev/null
    dbl=$((sz * 2))
    sips -z "$dbl" "$dbl" logo512.png --out "$ICONSET_DIR/icon_${sz}x${sz}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET_DIR" -o AppIcon.icns
  ICON_PATH="AppIcon.icns"
  echo "Generated AppIcon.icns"
fi

# Create PyInstaller spec (collect_all pulls zigpy radio stacks into the bundle)
cat > "Ranaliz iOT Tester.spec" << SPECEOF
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
    icon='${ICON_PATH}',
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
    icon='${ICON_PATH}',
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
SPECEOF

# Build with PyInstaller (module form is reliable on PATH-less setups)
"$PYTHON" -m PyInstaller "Ranaliz iOT Tester.spec" --clean

echo ""
echo "Build complete!"
echo "   App bundle: dist/Ranaliz iOT Tester.app"
echo ""
echo "To run:"
echo "   open 'dist/Ranaliz iOT Tester.app'"
