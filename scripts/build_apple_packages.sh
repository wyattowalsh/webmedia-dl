#!/usr/bin/env bash
# Compile Apple packages on macOS CI. Device UI, signing, and store submission stay BLOCKED.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

swift test --package-path "$root/apps/WebMediaDLCore"
xcrun --sdk macosx swiftc -typecheck \
  "$root/extensions/safari/SafariWebExtensionHandler.swift"
swift build --package-path "$root/apps/WebMediaDLMac"
swift build --package-path "$root/apps/WebMediaDLMac" --target WebMediaDLMacShareExtension

scheme_listed() {
  local listing="$1"
  local scheme="$2"
  printf '%s\n' "$listing" | awk -v wanted="$scheme" '
    BEGIN { in_schemes = 0; found = 0 }
    /Schemes:/ { in_schemes = 1; next }
    in_schemes && $0 ~ /^[[:space:]]+[A-Za-z0-9_.-]+[[:space:]]*$/ {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      if ($0 == wanted) found = 1
    }
    END { exit found ? 0 : 1 }
  '
}

compile_scheme() {
  local pkg="$1"
  local scheme="$2"
  local dest="$3"
  (
    cd "$root/apps/${pkg}"
    local listing
    listing="$(xcodebuild -list)"
    printf '%s\n' "$listing"
    local use_scheme="${scheme}"
    if [[ "${scheme}" == *ShareExtension ]]; then
      echo "Compiling share extension ${scheme} via executable product ${pkg} (library product + target dependency)."
      use_scheme="${pkg}"
    elif ! scheme_listed "$listing" "${scheme}"; then
      echo "error: workspace ${pkg} has no scheme ${scheme}" >&2
      exit 1
    fi
    xcodebuild \
      -scheme "${use_scheme}" \
      -destination "${dest}" \
      -derivedDataPath "${root}/apps/${pkg}/.ci-derived" \
      -skipPackagePluginValidation \
      CODE_SIGNING_ALLOWED=NO \
      CODE_SIGNING_REQUIRED=NO \
      CODE_SIGN_IDENTITY="" \
      build
  )
}

compile_scheme WebMediaDLiOS WebMediaDLiOS "generic/platform=iOS"
compile_scheme WebMediaDLiOS WebMediaDLiOSShareExtension "generic/platform=iOS"
compile_scheme WebMediaDLiPadOS WebMediaDLiPadOS "generic/platform=iOS"
compile_scheme WebMediaDLiPadOS WebMediaDLiPadOSShareExtension "generic/platform=iOS"
compile_scheme WebMediaDLVision WebMediaDLVision "generic/platform=visionOS"
compile_scheme WebMediaDLVision WebMediaDLVisionShareExtension "generic/platform=visionOS"
compile_scheme WebMediaDLWatch WebMediaDLWatch "generic/platform=watchOS"
compile_scheme WebMediaDLTV WebMediaDLTV "generic/platform=tvOS"

python3 "$root/scripts/generate_unsigned_appex_xcodeproj.py" --root "$root" --check

compile_unsigned_appex() {
  local name="$1"
  local dest="$2"
  xcodebuild \
    -project "$root/apps/WebMediaDLShareExtensions/WebMediaDLShareExtensions.xcodeproj" \
    -scheme "$name" \
    -destination "$dest" \
    -derivedDataPath "$root/apps/.ci-derived-appex-xcode" \
    -skipPackagePluginValidation \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY="" \
    build
}

echo "Building unsigned com.apple.product-type.app-extension share-sheet products."
compile_unsigned_appex WebMediaDLiOSShareExtension "generic/platform=iOS"
compile_unsigned_appex WebMediaDLiPadOSShareExtension "generic/platform=iOS"
compile_unsigned_appex WebMediaDLVisionShareExtension "generic/platform=visionOS"
compile_unsigned_appex WebMediaDLMacShareExtension "generic/platform=macOS"
python3 "$root/scripts/generate_unsigned_appex_xcodeproj.py" \
  --root "$root" \
  --inspect-derived "$root/apps/.ci-derived-appex-xcode" \
  --require-macho

python3 "$root/scripts/assemble_unsigned_appex.py" --dest "$root/apps/.ci-derived-appex"
for name in \
  WebMediaDLiOSShareExtension \
  WebMediaDLiPadOSShareExtension \
  WebMediaDLVisionShareExtension \
  WebMediaDLMacShareExtension
do
  bundle="$root/apps/.ci-derived-appex/${name}.appex"
  test -d "$bundle"
  test -f "$bundle/Info.plist"
  test -f "$bundle/PrivacyInfo.xcprivacy"
done
