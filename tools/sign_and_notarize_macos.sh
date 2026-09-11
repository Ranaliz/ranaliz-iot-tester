#!/usr/bin/env bash
# Sign + notarize a macOS .app for Gatekeeper (Developer ID + notarytool).
# Required env:
#   APPLE_CERTIFICATE_P12       base64-encoded .p12
#   APPLE_CERTIFICATE_PASSWORD  p12 password
#   APPLE_TEAM_ID               10-char Team ID
#   APPLE_API_KEY               AuthKey_XXXXXX.p8 file contents
#   APPLE_API_KEY_ID            Key ID
#   APPLE_API_ISSUER            Issuer UUID
# Optional:
#   APP_PATH                    path to .app (default: dist/Ranaliz iOT Tester.app)
#   ENTITLEMENTS                entitlements plist (default: entitlements.plist)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

APP_PATH="${APP_PATH:-dist/Ranaliz iOT Tester.app}"
ENTITLEMENTS="${ENTITLEMENTS:-entitlements.plist}"

missing=()
for v in APPLE_CERTIFICATE_P12 APPLE_CERTIFICATE_PASSWORD APPLE_TEAM_ID \
         APPLE_API_KEY APPLE_API_KEY_ID APPLE_API_ISSUER; do
  if [[ -z "${!v:-}" ]]; then
    missing+=("$v")
  fi
done
if ((${#missing[@]})); then
  echo "Missing required Apple signing secrets: ${missing[*]}" >&2
  echo "Add them under repo Settings → Secrets and variables → Actions." >&2
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "App not found: $APP_PATH" >&2
  exit 1
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "Entitlements not found: $ENTITLEMENTS" >&2
  exit 1
fi

KEYCHAIN_NAME="ranaliz-signing.keychain-db"
KEYCHAIN_PASSWORD="$(openssl rand -base64 32)"
P12_PATH="$(mktemp /tmp/cert.XXXXXX.p12)"
API_KEY_PATH="$(mktemp /tmp/AuthKey.XXXXXX.p8)"
NOTARY_ZIP="$(mktemp /tmp/notary.XXXXXX.zip)"

cleanup() {
  security delete-keychain "$KEYCHAIN_NAME" 2>/dev/null || true
  rm -f "$P12_PATH" "$API_KEY_PATH" "$NOTARY_ZIP"
}
trap cleanup EXIT

echo "Importing Developer ID certificate into temporary keychain..."
echo -n "$APPLE_CERTIFICATE_P12" | base64 --decode > "$P12_PATH"

security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_NAME"
security set-keychain-settings -lut 21600 "$KEYCHAIN_NAME"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_NAME"
security import "$P12_PATH" -k "$KEYCHAIN_NAME" -P "$APPLE_CERTIFICATE_PASSWORD" \
  -T /usr/bin/codesign -T /usr/bin/security -T /usr/bin/productsign
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN_NAME"
security list-keychains -d user -s "$KEYCHAIN_NAME" $(security list-keychains -d user | sed -e 's/"//g')

IDENTITY="$(security find-identity -v -p codesigning "$KEYCHAIN_NAME" \
  | awk -F'"' '/Developer ID Application/ {print $2; exit}')"
if [[ -z "$IDENTITY" ]]; then
  echo "No 'Developer ID Application' identity found in imported certificate." >&2
  security find-identity -v -p codesigning "$KEYCHAIN_NAME" >&2 || true
  exit 1
fi
echo "Signing with: $IDENTITY"

# Remove existing signatures, then sign nested Mach-O from the inside out,
# finally the outer .app with hardened runtime + entitlements.
find "$APP_PATH" -type f \( -perm -111 -o -name '*.dylib' -o -name '*.so' \) -print0 \
  | while IFS= read -r -d '' bin; do
      file -b "$bin" | grep -q 'Mach-O' || continue
      codesign --force --options runtime --timestamp \
        --entitlements "$ENTITLEMENTS" \
        --sign "$IDENTITY" "$bin" || true
    done

codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$IDENTITY" "$APP_PATH"

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
echo "codesign OK"

echo "Submitting to Apple notarization..."
ditto -c -k --keepParent "$APP_PATH" "$NOTARY_ZIP"

printf '%s' "$APPLE_API_KEY" > "$API_KEY_PATH"
# notarytool expects AuthKey_<KEY_ID>.p8 filename
API_KEY_NAMED="$(dirname "$API_KEY_PATH")/AuthKey_${APPLE_API_KEY_ID}.p8"
cp "$API_KEY_PATH" "$API_KEY_NAMED"

xcrun notarytool submit "$NOTARY_ZIP" \
  --key "$API_KEY_NAMED" \
  --key-id "$APPLE_API_KEY_ID" \
  --issuer "$APPLE_API_ISSUER" \
  --wait

echo "Stapling notarization ticket..."
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
echo "Notarization + staple complete: $APP_PATH"

rm -f "$API_KEY_NAMED"
