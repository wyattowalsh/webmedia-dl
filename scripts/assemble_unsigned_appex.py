#!/usr/bin/env python3
"""Assemble unsigned ``.appex`` bundle layouts from share-extension sources.

Signed Xcode NSExtension wrapping stays BLOCKED. This writes inspectable
unsigned bundle directories so Linux and macOS CI can prove Info.plist,
PrivacyInfo, package type, and principal-class contracts without a signing
identity. macOS CI separately ``xcodebuild``s ``com.apple.product-type.app-extension``
targets from ``scripts/generate_unsigned_appex_xcodeproj.py``.
"""

from __future__ import annotations

import argparse
import plistlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHARE_EXTENSIONS: tuple[tuple[str, str, str], ...] = (
    (
        "apps/WebMediaDLiOS/ShareExtension",
        "WebMediaDLiOSShareExtension",
        "WebMediaDLiOSShareExtensionPrincipal",
    ),
    (
        "apps/WebMediaDLiPadOS/ShareExtension",
        "WebMediaDLiPadOSShareExtension",
        "WebMediaDLiPadOSShareExtensionPrincipal",
    ),
    (
        "apps/WebMediaDLVision/ShareExtension",
        "WebMediaDLVisionShareExtension",
        "WebMediaDLVisionShareExtensionPrincipal",
    ),
    (
        "apps/WebMediaDLMac/ShareExtension",
        "WebMediaDLMacShareExtension",
        "WebMediaDLMacShareExtensionPrincipal",
    ),
)


def assemble(root: Path, dest: Path) -> list[Path]:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for relative, name, principal in SHARE_EXTENSIONS:
        source = root / relative
        info_path = source / "Info.plist"
        privacy_path = source / "PrivacyInfo.xcprivacy"
        if not info_path.is_file():
            msg = f"missing share-extension Info.plist: {info_path}"
            raise FileNotFoundError(msg)
        if not privacy_path.is_file():
            msg = f"missing share-extension PrivacyInfo.xcprivacy: {privacy_path}"
            raise FileNotFoundError(msg)
        payload = plistlib.loads(info_path.read_bytes())
        extension = payload.get("NSExtension")
        if not isinstance(extension, dict):
            msg = f"{info_path} is missing NSExtension"
            raise ValueError(msg)
        if extension.get("NSExtensionPointIdentifier") != "com.apple.share-services":
            msg = f"{info_path} is not a share-services extension"
            raise ValueError(msg)
        if extension.get("NSExtensionPrincipalClass") != principal:
            msg = f"{info_path} principal {extension.get('NSExtensionPrincipalClass')!r} != {principal}"
            raise ValueError(msg)
        payload["CFBundlePackageType"] = "XPC!"
        payload["CFBundleExecutable"] = name
        payload.setdefault("CFBundleName", "WebMedia DL")
        bundle = dest / f"{name}.appex"
        if bundle.exists():
            shutil.rmtree(bundle)
        bundle.mkdir(parents=True)
        (bundle / "Info.plist").write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML))
        shutil.copy2(privacy_path, bundle / "PrivacyInfo.xcprivacy")
        created.append(bundle)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--dest",
        type=Path,
        default=ROOT / "apps" / ".ci-derived-appex",
    )
    args = parser.parse_args(argv)
    for path in assemble(args.root, args.dest):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
