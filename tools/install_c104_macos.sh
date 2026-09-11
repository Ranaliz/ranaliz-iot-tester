#!/usr/bin/env bash
# Install c104 on macOS from sdist with a Clang fix.
# PyPI ships no macOS wheels; c104 2.x sdist fails on newer Apple Clang because
# DateTime.cpp re-adds a default argument on an out-of-line constructor.
set -euo pipefail

PYTHON="${1:-python3}"
WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

cd "$WORKDIR"
"$PYTHON" -m pip download 'c104>=0.15.0' --no-binary=:all: -d .
tar -xzf c104-*.tar.gz
SRC_DIR="$(echo c104-*/)"

"$PYTHON" - <<'PY'
from pathlib import Path
import glob

path = Path(glob.glob("c104-*/src/object/DateTime.cpp")[0])
text = path.read_text(encoding="utf-8")
old = (
    "DateTime::DateTime(const std::chrono::system_clock::time_point t =\n"
    "                       std::chrono::system_clock::now())"
)
new = "DateTime::DateTime(const std::chrono::system_clock::time_point t)"
if old not in text:
    # Already fixed (e.g. newer upstream) — install as-is
    if "system_clock::now())" not in text.split("DateTime::DateTime", 1)[-1][:200]:
        print(f"No patch needed for {path}")
    else:
        raise SystemExit(f"Unexpected DateTime.cpp contents; cannot patch {path}")
else:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Patched {path}")
PY

"$PYTHON" -m pip install "./${SRC_DIR}"
"$PYTHON" -c "import c104; print('c104 OK', getattr(c104, '__version__', '?'))"
