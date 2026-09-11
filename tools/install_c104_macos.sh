#!/usr/bin/env bash
# Install c104 on macOS from sdist with Clang/linker fixes.
# PyPI ships no macOS wheels. Known issues on newer Apple toolchains:
# 1) DateTime.cpp re-adds a default argument on an out-of-line constructor
# 2) lib60870 links -lrt (Linux-only; absent on Darwin)
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

root = Path(glob.glob("c104-*/")[0])

# Patch 1: DateTime default-argument redeclaration
dt = root / "src/object/DateTime.cpp"
text = dt.read_text(encoding="utf-8")
old = (
    "DateTime::DateTime(const std::chrono::system_clock::time_point t =\n"
    "                       std::chrono::system_clock::now())"
)
new = "DateTime::DateTime(const std::chrono::system_clock::time_point t)"
if old in text:
    dt.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Patched {dt}")
else:
    print(f"DateTime patch skipped (already fixed?): {dt}")

# Patch 2: drop -lrt on Unix CMake link lines (not available on macOS)
for rel in (
    "depends/lib60870/lib60870-C/src/CMakeLists.txt",
    "depends/lib60870/lib60870-C/src/hal/CMakeLists.txt",
):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    if "-lrt" not in t:
        print(f"librt patch skipped: {p}")
        continue
    p.write_text(t.replace("        -lrt\n", "").replace("\t-lrt\n", ""), encoding="utf-8")
    print(f"Patched librt out of {p}")
PY

"$PYTHON" -m pip install "./${SRC_DIR}"
"$PYTHON" -c "import c104; print('c104 OK', getattr(c104, '__version__', '?'))"
