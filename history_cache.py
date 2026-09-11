"""
Persistent MRU history for connection fields (IP, COM, start address).
Stored under ~/.ranaliz_modbus_iec/history.json — max 10 entries per key.
"""
import json
import pathlib

CACHE_DIR = pathlib.Path.home() / ".ranaliz_modbus_iec"
HISTORY_PATH = CACHE_DIR / "history.json"
MAX_ENTRIES = 10

KEYS = ("modbus_ips", "iec_ips", "com_ports", "start_addresses", "mqtt_hosts")


def _empty():
    return {k: [] for k in KEYS}


def load():
    """Return the full history dict (always includes all keys)."""
    data = _empty()
    if not HISTORY_PATH.is_file():
        return data
    try:
        raw = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k in KEYS:
                vals = raw.get(k, [])
                if isinstance(vals, list):
                    data[k] = [str(v) for v in vals if str(v).strip()][:MAX_ENTRIES]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return data


def save(data):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out = {k: list(data.get(k, []))[:MAX_ENTRIES] for k in KEYS}
        HISTORY_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def get(key):
    if key not in KEYS:
        return []
    return list(load().get(key, []))


def push(key, value):
    """Insert value at front of key list (dedupe). Returns updated list."""
    if key not in KEYS:
        return []
    text = str(value).strip() if value is not None else ""
    if not text:
        return get(key)
    data = load()
    items = [x for x in data.get(key, []) if x != text]
    items.insert(0, text)
    data[key] = items[:MAX_ENTRIES]
    save(data)
    return list(data[key])
