#!/usr/bin/env bash
# Compile Apple packages on macOS CI. Device UI, signing, and store submission stay BLOCKED.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

swift test --package-path "$root/apps/WebMediaDLCore"
swift build --package-path "$root/apps/WebMediaDLMac"

compile_scheme() {
  local pkg="$1"
  local scheme="$2"
  local dest="$3"
  (
    cd "$root/apps/${pkg}"
    xcodebuild -list >/dev/null
    xcodebuild \
      -scheme "${scheme}" \
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
