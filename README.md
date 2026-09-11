# Ranaliz iOT Tester

Desktop app for testing **Modbus** (TCP/UDP/RTU), **IEC 60870-5-104**, **MQTT**, and **Zigbee**, with Ranaliz branding, Excel/CSV export, and multi-language UI (EN / TR / AR).

**Repository:** [github.com/Ranaliz/ranaliz-iot-tester](https://github.com/Ranaliz/ranaliz-iot-tester)

## Features

### Modbus (TCP/UDP/RTU)
- Protocols: TCP, UDP, Serial (RTU)
- Functions: FC01–FC16
- Formats: raw registers, int/uint/float variants, hex, binary, ASCII/UTF-8/UTF-16
- Endianness: big/little and swapped variants
- Poll rates, timeouts, serial parameters, transaction history

### IEC 60870-5-104
- Client mode: connect to RTU, GI, commands, live point updates
- Server mode: RTU simulator for master testing
- Point types via c104 (M_SP, M_DP, M_ME, C_SC, C_DC, C_SE, …)

### MQTT & Zigbee
- MQTT broker connect/subscribe/publish (TLS optional)
- Zigbee coordinator workflows (radio/serial)

### Export & UI
- Branded Excel/CSV export
- Dark navy/teal Ranaliz theme, header language switcher

## Installation (from source)

```bash
git clone https://github.com/Ranaliz/ranaliz-iot-tester.git
cd ranaliz-iot-tester

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py
```

## Pre-built binaries

- **macOS:** `dist/Ranaliz iOT Tester.app` (from Releases or local build)
- **Windows:** `dist/Ranaliz iOT Tester.exe` (one-file; run on Windows — no installer wizard)

## Usage (short)

**Modbus:** set TCP/UDP or Serial → Connect → choose function / slave / address / count → view table → export via File menu.

**IEC-104 client:** add points → Connect → GI / commands → live log.  
**IEC-104 server:** add points → Start server → monitor activity.

## Building

PyInstaller must run on the **target OS** (no cross-compile).

### macOS

```bash
cd ranaliz-iot-tester
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pyinstaller pyinstaller-hooks-contrib pillow
bash build_macos.sh
# → dist/Ranaliz iOT Tester.app
```

### Windows

```bat
cd ranaliz-iot-tester
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller pyinstaller-hooks-contrib pillow
build_windows.bat
```

Output: `dist\Ranaliz iOT Tester.exe`

## Architecture

| File | Role |
|------|------|
| `main.py` | Main window, tabs |
| `dialogs.py` | Dialogs |
| `modbus_worker.py` | Modbus poll thread |
| `iec104_worker.py` | IEC-104 client/server |
| `mqtt_worker.py` / `zigbee_worker.py` | MQTT / Zigbee |
| `mqtt_zigbee_panels.py` | MQTT/Zigbee UI |
| `formats.py` | Register decode/display |
| `excel_export.py` | Excel export |
| `theme.py` / `branding.py` | QSS + logo/icons |
| `i18n.py` | Translations |

## License

MIT — see [LICENSE](LICENSE). Copyright © 2026 Ranaliz.

## Support

- **Email:** info@ranaliz.com  
- **Web:** https://ranaliz.com
