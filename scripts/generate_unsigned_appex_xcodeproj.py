#!/usr/bin/env python3
"""Generate an unsigned Xcode app-extension project for share sheets.

Signed Xcode NSExtension wrapping stays BLOCKED. This writes a ``.xcodeproj``
whose native targets use ``com.apple.product-type.app-extension`` so macOS CI
can ``xcodebuild`` real ``.appex`` bundles and inspect their Mach-O executables
without a signing identity.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import plistlib
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = ROOT / "apps/WebMediaDLShareExtensions/WebMediaDLShareExtensions.xcodeproj"

MACHO_MAGICS = (
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
)

PLATFORM: dict[str, dict[str, str]] = {
    "WebMediaDLiOSShareExtension": {
        "sdkroot": "iphoneos",
        "supported_platforms": "iphoneos iphonesimulator",
        "destination": "generic/platform=iOS",
        "device_family": "1",
        "deployment_key": "IPHONEOS_DEPLOYMENT_TARGET",
        "deployment_value": "17.0",
        "runpath": ("$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks"),
    },
    "WebMediaDLiPadOSShareExtension": {
        "sdkroot": "iphoneos",
        "supported_platforms": "iphoneos iphonesimulator",
        "destination": "generic/platform=iOS",
        "device_family": "2",
        "deployment_key": "IPHONEOS_DEPLOYMENT_TARGET",
        "deployment_value": "17.0",
        "runpath": ("$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks"),
    },
    "WebMediaDLVisionShareExtension": {
        "sdkroot": "xros",
        "supported_platforms": "xros xrsimulator",
        "destination": "generic/platform=visionOS",
        "device_family": "7",
        "deployment_key": "XROS_DEPLOYMENT_TARGET",
        "deployment_value": "1.0",
        "runpath": ("$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks"),
    },
    "WebMediaDLMacShareExtension": {
        "sdkroot": "macosx",
        "supported_platforms": "macosx",
        "destination": "generic/platform=macOS",
        "device_family": "",
        "deployment_key": "MACOSX_DEPLOYMENT_TARGET",
        "deployment_value": "14.0",
        "runpath": (
            "$(inherited) @executable_path/../Frameworks @executable_path/../../../../Frameworks"
        ),
    },
}


def load_share_extensions() -> tuple[tuple[str, str, str], ...]:
    path = Path(__file__).with_name("assemble_unsigned_appex.py")
    spec = importlib.util.spec_from_file_location("assemble_unsigned_appex", path)
    if spec is None or spec.loader is None:
        msg = f"unable to load {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    extensions = getattr(module, "SHARE_EXTENSIONS", None)
    if not isinstance(extensions, tuple) or not extensions:
        msg = "assemble_unsigned_appex.SHARE_EXTENSIONS is missing"
        raise RuntimeError(msg)
    return extensions


def oid(*parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest().upper()
    return digest[:24]


def pbx_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def pbx_settings(settings: dict[str, str]) -> str:
    lines = []
    for key in sorted(settings):
        lines.append(f"\t\t\t\t{key} = {pbx_quote(settings[key])};")
    return "\n".join(lines)


def extension_rows(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    project_dir = root / "apps/WebMediaDLShareExtensions"
    for source_rel, name, principal in load_share_extensions():
        platform = PLATFORM.get(name)
        if platform is None:
            msg = f"no unsigned xcode platform mapping for {name}"
            raise KeyError(msg)
        source = root / source_rel
        swift = source / f"{name}.swift"
        info = source / "Info.plist"
        privacy = source / "PrivacyInfo.xcprivacy"
        entitlements = source / "WebMediaDL.entitlements"
        for path in (swift, info, privacy, entitlements):
            if not path.is_file():
                msg = f"missing share-extension file: {path}"
                raise FileNotFoundError(msg)
        payload = plistlib.loads(info.read_bytes())
        bundle_id = payload.get("CFBundleIdentifier")
        if not isinstance(bundle_id, str) or not bundle_id:
            msg = f"{info} is missing CFBundleIdentifier"
            raise ValueError(msg)
        rows.append(
            {
                "name": name,
                "principal": principal,
                "bundle_id": bundle_id,
                "swift": _rel(project_dir, swift),
                "info": _rel(project_dir, info),
                "privacy": _rel(project_dir, privacy),
                "entitlements": _rel(project_dir, entitlements),
                **platform,
            }
        )
    return rows


def _rel(start: Path, path: Path) -> str:
    return os.path.relpath(path, start).replace("\\", "/")


def render_pbxproj(root: Path) -> str:
    rows = extension_rows(root)
    ids: dict[str, str] = {}

    def ident(*parts: str) -> str:
        key = "::".join(parts)
        value = oid(*parts)
        previous = ids.get(value)
        if previous is not None and previous != key:
            msg = f"object id collision {value}: {previous} vs {key}"
            raise RuntimeError(msg)
        ids[value] = key
        return value

    project_id = ident("project")
    products_id = ident("group", "products")
    sources_id = ident("group", "sources")
    package_id = ident("package", "WebMediaDLCore")
    project_cfg_list = ident("cfglist", "project")
    project_debug = ident("cfg", "project", "Debug")
    project_release = ident("cfg", "project", "Release")

    build_files: list[str] = []
    file_refs: list[str] = []
    frameworks_phases: list[str] = []
    resource_phases: list[str] = []
    source_phases: list[str] = []
    native_targets: list[str] = []
    target_cfg_lists: list[str] = []
    target_cfgs: list[str] = []
    product_deps: list[str] = []
    product_ids: list[str] = []
    target_ids: list[str] = []
    source_file_ids: list[str] = []

    common_project = {
        "ALWAYS_SEARCH_USER_PATHS": "NO",
        "CLANG_ENABLE_MODULES": "YES",
        "CLANG_ENABLE_OBJC_ARC": "YES",
        "CODE_SIGNING_ALLOWED": "NO",
        "CODE_SIGNING_REQUIRED": "NO",
        "CODE_SIGN_IDENTITY": "",
        "CODE_SIGN_STYLE": "Manual",
        "DEVELOPMENT_TEAM": "",
        "ENABLE_STRICT_OBJC_MSGSEND": "YES",
        "GCC_NO_COMMON_BLOCKS": "YES",
        "IPHONEOS_DEPLOYMENT_TARGET": "17.0",
        "MACOSX_DEPLOYMENT_TARGET": "14.0",
        "SWIFT_VERSION": "6.0",
        "XROS_DEPLOYMENT_TARGET": "1.0",
    }
    debug_project = {
        **common_project,
        "COPY_PHASE_STRIP": "NO",
        "GCC_PREPROCESSOR_DEFINITIONS": "DEBUG=1 $(inherited)",
        "SWIFT_ACTIVE_COMPILATION_CONDITIONS": "DEBUG",
        "SWIFT_OPTIMIZATION_LEVEL": "-Onone",
    }
    release_project = {
        **common_project,
        "COPY_PHASE_STRIP": "YES",
        "SWIFT_OPTIMIZATION_LEVEL": "-O",
    }

    for row in rows:
        name = row["name"]
        product_ref = ident("product", name)
        swift_ref = ident("file", name, "swift")
        privacy_ref = ident("file", name, "privacy")
        swift_build = ident("build", name, "swift")
        privacy_build = ident("build", name, "privacy")
        frameworks_build = ident("build", name, "frameworks")
        product_dep = ident("productdep", name)
        sources_phase = ident("phase", name, "sources")
        frameworks_phase = ident("phase", name, "frameworks")
        resources_phase = ident("phase", name, "resources")
        target_id = ident("target", name)
        cfg_list = ident("cfglist", name)
        cfg_debug = ident("cfg", name, "Debug")
        cfg_release = ident("cfg", name, "Release")
        info_ref = ident("file", name, "info")
        product_ids.append(product_ref)
        target_ids.append(target_id)
        source_file_ids.extend(
            [
                f"{swift_ref} /* {name}.swift */",
                f"{info_ref} /* {name} Info.plist */",
                f"{privacy_ref} /* {name} PrivacyInfo.xcprivacy */",
            ]
        )

        file_refs.append(
            f"\t\t{product_ref} /* {name}.appex */ = {{isa = PBXFileReference; "
            f'explicitFileType = "wrapper.app-extension"; includeInIndex = 0; '
            f"path = {pbx_quote(name + '.appex')}; sourceTree = BUILT_PRODUCTS_DIR; }};"
        )
        file_refs.append(
            f"\t\t{swift_ref} /* {name}.swift */ = {{isa = PBXFileReference; "
            f"lastKnownFileType = sourcecode.swift; "
            f"name = {pbx_quote(name + '.swift')}; path = {pbx_quote(row['swift'])}; "
            f'sourceTree = "<group>"; }};'
        )
        file_refs.append(
            f"\t\t{info_ref} /* {name} Info.plist */ = {{isa = PBXFileReference; "
            f"lastKnownFileType = text.plist.xml; name = Info.plist; "
            f'path = {pbx_quote(row["info"])}; sourceTree = "<group>"; }};'
        )
        file_refs.append(
            f"\t\t{privacy_ref} /* {name} PrivacyInfo.xcprivacy */ = {{"
            f"isa = PBXFileReference; lastKnownFileType = text.xml; "
            f"name = PrivacyInfo.xcprivacy; path = {pbx_quote(row['privacy'])}; "
            f'sourceTree = "<group>"; }};'
        )
        build_files.append(
            f"\t\t{swift_build} /* {name}.swift in Sources */ = {{"
            f"isa = PBXBuildFile; fileRef = {swift_ref} /* {name}.swift */; }};"
        )
        build_files.append(
            f"\t\t{privacy_build} /* PrivacyInfo.xcprivacy in Resources */ = {{"
            f"isa = PBXBuildFile; fileRef = {privacy_ref} /* {name} PrivacyInfo.xcprivacy */; }};"
        )
        build_files.append(
            f"\t\t{frameworks_build} /* WebMediaDLCore in Frameworks */ = {{"
            f"isa = PBXBuildFile; productRef = {product_dep} /* WebMediaDLCore */; }};"
        )
        source_phases.append(
            f"\t\t{sources_phase} /* Sources */ = {{\n"
            f"\t\t\tisa = PBXSourcesBuildPhase;\n"
            f"\t\t\tbuildActionMask = 2147483647;\n"
            f"\t\t\tfiles = (\n"
            f"\t\t\t\t{swift_build} /* {name}.swift in Sources */,\n"
            f"\t\t\t);\n"
            f"\t\t\trunOnlyForDeploymentPostprocessing = 0;\n"
            f"\t\t}};"
        )
        frameworks_phases.append(
            f"\t\t{frameworks_phase} /* Frameworks */ = {{\n"
            f"\t\t\tisa = PBXFrameworksBuildPhase;\n"
            f"\t\t\tbuildActionMask = 2147483647;\n"
            f"\t\t\tfiles = (\n"
            f"\t\t\t\t{frameworks_build} /* WebMediaDLCore in Frameworks */,\n"
            f"\t\t\t);\n"
            f"\t\t\trunOnlyForDeploymentPostprocessing = 0;\n"
            f"\t\t}};"
        )
        resource_phases.append(
            f"\t\t{resources_phase} /* Resources */ = {{\n"
            f"\t\t\tisa = PBXResourcesBuildPhase;\n"
            f"\t\t\tbuildActionMask = 2147483647;\n"
            f"\t\t\tfiles = (\n"
            f"\t\t\t\t{privacy_build} /* PrivacyInfo.xcprivacy in Resources */,\n"
            f"\t\t\t);\n"
            f"\t\t\trunOnlyForDeploymentPostprocessing = 0;\n"
            f"\t\t}};"
        )
        product_deps.append(
            f"\t\t{product_dep} /* WebMediaDLCore */ = {{\n"
            f"\t\t\tisa = XCSwiftPackageProductDependency;\n"
            f"\t\t\tpackage = {package_id} /* XCLocalSwiftPackageReference "
            f'"WebMediaDLCore" */;\n'
            f"\t\t\tproductName = WebMediaDLCore;\n"
            f"\t\t}};"
        )
        native_targets.append(
            f"\t\t{target_id} /* {name} */ = {{\n"
            f"\t\t\tisa = PBXNativeTarget;\n"
            f"\t\t\tbuildConfigurationList = {cfg_list} /* Build configuration list "
            f'for PBXNativeTarget "{name}" */;\n'
            f"\t\t\tbuildPhases = (\n"
            f"\t\t\t\t{sources_phase} /* Sources */,\n"
            f"\t\t\t\t{frameworks_phase} /* Frameworks */,\n"
            f"\t\t\t\t{resources_phase} /* Resources */,\n"
            f"\t\t\t);\n"
            f"\t\t\tbuildRules = (\n"
            f"\t\t\t);\n"
            f"\t\t\tdependencies = (\n"
            f"\t\t\t);\n"
            f"\t\t\tname = {name};\n"
            f"\t\t\tpackageProductDependencies = (\n"
            f"\t\t\t\t{product_dep} /* WebMediaDLCore */,\n"
            f"\t\t\t);\n"
            f"\t\t\tproductName = {name};\n"
            f"\t\t\tproductReference = {product_ref} /* {name}.appex */;\n"
            f'\t\t\tproductType = "com.apple.product-type.app-extension";\n'
            f"\t\t}};"
        )
        target_settings = {
            "APPLICATION_EXTENSION_API_ONLY": "NO",
            "CODE_SIGNING_ALLOWED": "NO",
            "CODE_SIGNING_REQUIRED": "NO",
            "CODE_SIGN_ENTITLEMENTS": row["entitlements"],
            "CODE_SIGN_IDENTITY": "",
            "CODE_SIGN_STYLE": "Manual",
            "CURRENT_PROJECT_VERSION": "1",
            "GENERATE_INFOPLIST_FILE": "NO",
            "INFOPLIST_FILE": row["info"],
            "LD_RUNPATH_SEARCH_PATHS": row["runpath"],
            "MARKETING_VERSION": "0.1.0",
            "PRODUCT_BUNDLE_IDENTIFIER": row["bundle_id"],
            "PRODUCT_NAME": name,
            "SDKROOT": row["sdkroot"],
            "SKIP_INSTALL": "YES",
            "SUPPORTED_PLATFORMS": row["supported_platforms"],
            "SWIFT_EMIT_LOC_STRINGS": "YES",
            "SWIFT_VERSION": "6.0",
            "WRAPPER_EXTENSION": "appex",
            row["deployment_key"]: row["deployment_value"],
        }
        if row["device_family"]:
            target_settings["TARGETED_DEVICE_FAMILY"] = row["device_family"]
        target_cfgs.append(
            f"\t\t{cfg_debug} /* Debug */ = {{\n"
            f"\t\t\tisa = XCBuildConfiguration;\n"
            f"\t\t\tbuildSettings = {{\n"
            f"{pbx_settings(target_settings)}\n"
            f"\t\t\t}};\n"
            f"\t\t\tname = Debug;\n"
            f"\t\t}};"
        )
        target_cfgs.append(
            f"\t\t{cfg_release} /* Release */ = {{\n"
            f"\t\t\tisa = XCBuildConfiguration;\n"
            f"\t\t\tbuildSettings = {{\n"
            f"{pbx_settings(target_settings)}\n"
            f"\t\t\t}};\n"
            f"\t\t\tname = Release;\n"
            f"\t\t}};"
        )
        target_cfg_lists.append(
            f'\t\t{cfg_list} /* Build configuration list for PBXNativeTarget "{name}" */ = {{\n'
            f"\t\t\tisa = XCConfigurationList;\n"
            f"\t\t\tbuildConfigurations = (\n"
            f"\t\t\t\t{cfg_debug} /* Debug */,\n"
            f"\t\t\t\t{cfg_release} /* Release */,\n"
            f"\t\t\t);\n"
            f"\t\t\tdefaultConfigurationIsVisible = 0;\n"
            f"\t\t\tdefaultConfigurationName = Debug;\n"
            f"\t\t}};"
        )

    target_list = ",\n".join(
        f"\t\t\t\t{tid} /* {row['name']} */" for tid, row in zip(target_ids, rows, strict=True)
    )
    product_list = ",\n".join(
        f"\t\t\t\t{pid} /* {row['name']}.appex */"
        for pid, row in zip(product_ids, rows, strict=True)
    )
    source_list = ",\n".join(f"\t\t\t\t{fid}" for fid in source_file_ids)

    project_object = (
        f"\t\t{project_id} /* Project object */ = {{\n"
        f"\t\t\tisa = PBXProject;\n"
        f"\t\t\tattributes = {{\n"
        f"\t\t\t\tBuildIndependentTargetsInParallel = 1;\n"
        f"\t\t\t\tLastSwiftUpdateCheck = 1600;\n"
        f"\t\t\t\tLastUpgradeCheck = 1600;\n"
        f"\t\t\t}};\n"
        f"\t\t\tbuildConfigurationList = {project_cfg_list} /* Build configuration list "
        f'for PBXProject "WebMediaDLShareExtensions" */;\n'
        f'\t\t\tcompatibilityVersion = "Xcode 15.0";\n'
        f"\t\t\tdevelopmentRegion = en;\n"
        f"\t\t\thasScannedForEncodings = 0;\n"
        f"\t\t\tknownRegions = (\n"
        f"\t\t\t\ten,\n"
        f"\t\t\t\tBase,\n"
        f"\t\t\t);\n"
        f"\t\t\tmainGroup = {sources_id};\n"
        f"\t\t\tpackageReferences = (\n"
        f'\t\t\t\t{package_id} /* XCLocalSwiftPackageReference "WebMediaDLCore" */,\n'
        f"\t\t\t);\n"
        f"\t\t\tproductRefGroup = {products_id} /* Products */;\n"
        f'\t\t\tprojectDirPath = "";\n'
        f'\t\t\tprojectRoot = "";\n'
        f"\t\t\ttargets = (\n"
        f"{target_list},\n"
        f"\t\t\t);\n"
        f"\t\t}};"
    )
    groups = [
        (
            f"\t\t{sources_id} = {{\n"
            f"\t\t\tisa = PBXGroup;\n"
            f"\t\t\tchildren = (\n"
            f"{source_list},\n"
            f"\t\t\t\t{products_id} /* Products */,\n"
            f"\t\t\t);\n"
            f'\t\t\tsourceTree = "<group>";\n'
            f"\t\t}};"
        ),
        (
            f"\t\t{products_id} /* Products */ = {{\n"
            f"\t\t\tisa = PBXGroup;\n"
            f"\t\t\tchildren = (\n"
            f"{product_list},\n"
            f"\t\t\t);\n"
            f"\t\t\tname = Products;\n"
            f'\t\t\tsourceTree = "<group>";\n'
            f"\t\t}};"
        ),
    ]
    project_cfg_list_block = (
        f"\t\t{project_cfg_list} /* Build configuration list for PBXProject "
        f'"WebMediaDLShareExtensions" */ = {{\n'
        f"\t\t\tisa = XCConfigurationList;\n"
        f"\t\t\tbuildConfigurations = (\n"
        f"\t\t\t\t{project_debug} /* Debug */,\n"
        f"\t\t\t\t{project_release} /* Release */,\n"
        f"\t\t\t);\n"
        f"\t\t\tdefaultConfigurationIsVisible = 0;\n"
        f"\t\t\tdefaultConfigurationName = Debug;\n"
        f"\t\t}};"
    )
    project_cfgs = [
        (
            f"\t\t{project_debug} /* Debug */ = {{\n"
            f"\t\t\tisa = XCBuildConfiguration;\n"
            f"\t\t\tbuildSettings = {{\n"
            f"{pbx_settings(debug_project)}\n"
            f"\t\t\t}};\n"
            f"\t\t\tname = Debug;\n"
            f"\t\t}};"
        ),
        (
            f"\t\t{project_release} /* Release */ = {{\n"
            f"\t\t\tisa = XCBuildConfiguration;\n"
            f"\t\t\tbuildSettings = {{\n"
            f"{pbx_settings(release_project)}\n"
            f"\t\t\t}};\n"
            f"\t\t\tname = Release;\n"
            f"\t\t}};"
        ),
    ]
    package_block = (
        f'\t\t{package_id} /* XCLocalSwiftPackageReference "WebMediaDLCore" */ = {{\n'
        f"\t\t\tisa = XCLocalSwiftPackageReference;\n"
        f'\t\t\trelativePath = "../WebMediaDLCore";\n'
        f"\t\t}};"
    )
    sections = [
        ("PBXBuildFile", build_files),
        ("PBXFileReference", file_refs),
        ("PBXFrameworksBuildPhase", frameworks_phases),
        ("PBXGroup", groups),
        ("PBXNativeTarget", native_targets),
        ("PBXProject", [project_object]),
        ("PBXResourcesBuildPhase", resource_phases),
        ("PBXSourcesBuildPhase", source_phases),
        ("XCBuildConfiguration", [*project_cfgs, *target_cfgs]),
        ("XCConfigurationList", [project_cfg_list_block, *target_cfg_lists]),
        ("XCLocalSwiftPackageReference", [package_block]),
        ("XCSwiftPackageProductDependency", product_deps),
    ]
    chunks = [
        "// !$*UTF8*$!\n{\n\tarchiveVersion = 1;\n\tclasses = {\n\t};\n\tobjectVersion = 60;\n\tobjects = {\n"
    ]
    for title, objects in sections:
        chunks.append(f"\n/* Begin {title} section */\n")
        chunks.append("\n".join(objects))
        chunks.append(f"\n/* End {title} section */\n")
    chunks.append(f"\t}};\n\trootObject = {project_id} /* Project object */;\n}}\n")
    return "".join(chunks)


def render_scheme(name: str, target_id: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Scheme\n"
        '   LastUpgradeVersion = "1600"\n'
        '   version = "1.7">\n'
        "   <BuildAction\n"
        '      parallelizeBuildables = "YES"\n'
        '      buildImplicitDependencies = "YES">\n'
        "      <BuildActionEntries>\n"
        "         <BuildActionEntry\n"
        '            buildForTesting = "YES"\n'
        '            buildForRunning = "YES"\n'
        '            buildForProfiling = "YES"\n'
        '            buildForArchiving = "YES"\n'
        '            buildForAnalyzing = "YES">\n'
        "            <BuildableReference\n"
        '               BuildableIdentifier = "primary"\n'
        f'               BlueprintIdentifier = "{target_id}"\n'
        f'               BuildableName = "{name}.appex"\n'
        f'               BlueprintName = "{name}"\n'
        '               ReferencedContainer = "container:WebMediaDLShareExtensions.xcodeproj">\n'
        "            </BuildableReference>\n"
        "         </BuildActionEntry>\n"
        "      </BuildActionEntries>\n"
        "   </BuildAction>\n"
        "   <LaunchAction\n"
        '      buildConfiguration = "Debug"\n'
        '      selectedDebuggerIdentifier = ""\n'
        '      selectedLauncherIdentifier = "Xcode.IDEFoundation.Launcher.PosixSpawn"\n'
        '      launchStyle = "0"\n'
        '      useCustomWorkingDirectory = "NO"\n'
        '      ignoresPersistentStateOnLaunch = "NO"\n'
        '      debugDocumentVersioning = "YES"\n'
        '      debugServiceExtension = "internal"\n'
        '      allowLocationSimulation = "YES">\n'
        "   </LaunchAction>\n"
        "</Scheme>\n"
    )


def generated_files(root: Path) -> dict[str, str]:
    contents: dict[str, str] = {"project.pbxproj": render_pbxproj(root)}
    for _, name, _ in load_share_extensions():
        target_id = oid("target", name)
        contents[f"xcshareddata/xcschemes/{name}.xcscheme"] = render_scheme(name, target_id)
    return contents


def write_xcodeproj(root: Path, dest: Path | None = None) -> Path:
    project = dest or (root / DEFAULT_PROJECT.relative_to(ROOT))
    project.mkdir(parents=True, exist_ok=True)
    written = generated_files(root)
    for relative, text in written.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return project / "project.pbxproj"


def check_xcodeproj(root: Path, dest: Path | None = None) -> None:
    project = dest or (root / DEFAULT_PROJECT.relative_to(ROOT))
    expected = generated_files(root)
    for relative, text in expected.items():
        path = project / relative
        if not path.is_file():
            msg = f"missing generated Xcode file: {path}"
            raise FileNotFoundError(msg)
        actual = path.read_text(encoding="utf-8")
        if actual != text:
            msg = f"generated Xcode file is stale: {path}"
            raise ValueError(msg)


def macho_kind(path: Path) -> str | None:
    if not path.is_file():
        return None
    magic = path.read_bytes()[:4]
    if magic not in MACHO_MAGICS:
        return None
    if magic in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
        return "fat"
    if magic in {b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"}:
        return "64"
    return "32"


def appex_executable(bundle: Path, name: str) -> Path | None:
    candidates = (
        bundle / name,
        bundle / "Contents" / "MacOS" / name,
        bundle / "MacOS" / name,
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def inspect_bundle(bundle: Path, require_macho: bool = False) -> dict[str, Any]:
    if bundle.suffix != ".appex" or not bundle.is_dir():
        msg = f"not an .appex bundle: {bundle}"
        raise ValueError(msg)
    info_path = bundle / "Info.plist"
    if not info_path.is_file():
        nested = bundle / "Contents" / "Info.plist"
        info_path = nested if nested.is_file() else info_path
    if not info_path.is_file():
        msg = f"missing Info.plist in {bundle}"
        raise FileNotFoundError(msg)
    payload = plistlib.loads(info_path.read_bytes())
    name = bundle.name.removesuffix(".appex")
    expected = {item[1]: item[2] for item in load_share_extensions()}
    principal = expected.get(name)
    if principal is None:
        msg = f"unexpected share-extension bundle {bundle.name}"
        raise ValueError(msg)
    if payload.get("CFBundlePackageType") != "XPC!":
        msg = f"{bundle.name} package type is {payload.get('CFBundlePackageType')!r}"
        raise ValueError(msg)
    if payload.get("CFBundleExecutable") != name:
        msg = f"{bundle.name} executable is {payload.get('CFBundleExecutable')!r}"
        raise ValueError(msg)
    extension = payload.get("NSExtension")
    if not isinstance(extension, dict):
        msg = f"{info_path} is missing NSExtension"
        raise ValueError(msg)
    if extension.get("NSExtensionPointIdentifier") != "com.apple.share-services":
        msg = f"{bundle.name} is not a share-services extension"
        raise ValueError(msg)
    if extension.get("NSExtensionPrincipalClass") != principal:
        msg = f"{bundle.name} principal is {extension.get('NSExtensionPrincipalClass')!r}"
        raise ValueError(msg)
    privacy_path = bundle / "PrivacyInfo.xcprivacy"
    if not privacy_path.is_file():
        privacy_path = bundle / "Contents" / "Resources" / "PrivacyInfo.xcprivacy"
    if not privacy_path.is_file():
        msg = f"missing PrivacyInfo.xcprivacy in {bundle}"
        raise FileNotFoundError(msg)
    executable = appex_executable(bundle, name)
    kind = macho_kind(executable) if executable is not None else None
    if require_macho and kind is None:
        msg = f"{bundle.name} is missing a Mach-O executable"
        raise FileNotFoundError(msg)
    return {
        "bundle": bundle,
        "name": name,
        "principal": principal,
        "executable": executable,
        "macho": kind,
    }


def iter_appex_bundles(derived: Path) -> list[Path]:
    found: list[Path] = []
    for info in derived.rglob("Info.plist"):
        bundle = info.parent
        if bundle.name == "Contents":
            bundle = bundle.parent
        if bundle.suffix == ".appex" and bundle.is_dir():
            found.append(bundle)
    products = [path for path in found if "Build" in path.parts and "Products" in path.parts]
    unique = sorted({path.resolve() for path in (products or found)})
    return unique


def inspect_derived(derived: Path, require_macho: bool = False) -> list[dict[str, Any]]:
    bundles = iter_appex_bundles(derived)
    reports = [inspect_bundle(bundle, require_macho=require_macho) for bundle in bundles]
    names = {report["name"] for report in reports}
    expected = {item[1] for item in load_share_extensions()}
    if names != expected:
        msg = f"unsigned .appex products {sorted(names)} != {sorted(expected)}"
        raise FileNotFoundError(msg)
    return reports


def destinations() -> list[tuple[str, str]]:
    rows = []
    for _, name, _ in load_share_extensions():
        rows.append((name, PLATFORM[name]["destination"]))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dest", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--inspect-derived", type=Path, default=None)
    parser.add_argument("--inspect-bundle", type=Path, default=None)
    parser.add_argument("--require-macho", action="store_true")
    args = parser.parse_args(argv)
    dest = args.dest
    if dest is None:
        dest = args.root / DEFAULT_PROJECT.relative_to(ROOT)
    if args.inspect_bundle is not None:
        report = inspect_bundle(args.inspect_bundle, require_macho=args.require_macho)
        print(f"{report['bundle']} macho={report['macho']}")
        return 0
    if args.inspect_derived is not None:
        for report in inspect_derived(args.inspect_derived, require_macho=args.require_macho):
            print(f"{report['bundle']} macho={report['macho']}")
        return 0
    if args.check:
        check_xcodeproj(args.root, dest)
        print(dest / "project.pbxproj")
        return 0
    print(write_xcodeproj(args.root, dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
