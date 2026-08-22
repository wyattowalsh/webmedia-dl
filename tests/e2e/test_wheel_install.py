"""Prove packaged wheel install exposes runtime assets and the canonical CLI."""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from pathlib import Path

from webmedia_dl.paths import repo_root


def test_wheel_contains_runtime_and_cli(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=repo_root(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    wheels = list(dist.glob("*.whl"))
    assert wheels, built.stdout + built.stderr
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert any(name.endswith("webmedia_dl/runtime/export-presets.json") for name in names)
    assert any(name.endswith("webmedia_dl/runtime/policy-profiles.json") for name in names)
    assert any(
        name.endswith("webmedia_dl/runtime/imagemagick-runtime/policy.xml") for name in names
    )
    venv = tmp_path / "venv"
    created = subprocess.run(
        ["uv", "venv", "--python", "3.13", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    python = venv / "bin" / "python"
    installed = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stderr
    probe = subprocess.run(
        [
            str(python),
            "-c",
            "import webmedia_dl, webmedia_dl.paths as paths; "
            "print(paths.runtime_file('export-presets.json').is_file()); "
            "print(webmedia_dl.__file__)",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert probe.returncode == 0, probe.stderr
    lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
    assert lines[0] == "True"
    assert "site-packages" in lines[1]
    assert "/src/webmedia_dl" not in lines[1]
    help_out = subprocess.run(
        [str(venv / "bin" / "webmedia-dl"), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert help_out.returncode == 0, help_out.stderr
    assert "webmedia-dl" in help_out.stdout
    assert "wmdl" not in help_out.stdout.split("Usage")[0]
    assert not (venv / "bin" / "wmdl").exists()
    isolated_env = {
        **os.environ,
        "PYTHONPATH": "",
        "PATH": os.pathsep.join([str(venv / "bin"), "/usr/local/bin", "/usr/bin", "/bin"]),
    }
    doctor = subprocess.run(
        [str(venv / "bin" / "webmedia-dl"), "doctor"],
        check=False,
        capture_output=True,
        text=True,
        env=isolated_env,
    )
    assert doctor.returncode == 0, doctor.stderr
    payload = json.loads(doctor.stdout)
    assert payload["telemetry_default"] is False
    assert payload["drm_circumvention"] is False
    assert payload["apple_devices"]["macos"]["status"] == "BLOCKED"
    assert payload["signing_notarization"]["status"] == "BLOCKED"
    assert payload["providers"]["ytdlp"]["status"] == "BLOCKED"
    assert payload["providers"]["gallery-dl"]["status"] == "BLOCKED"
    assert "not installed" in payload["providers"]["ytdlp"]["reason"]
    assert not (venv / "bin" / "yt-dlp").exists()
    assert not (venv / "bin" / "gallery-dl").exists()
    packaged = tmp_path / "extensions"
    packaged_out = subprocess.run(
        [
            str(venv / "bin" / "webmedia-dl"),
            "package-extensions",
            "--dest",
            str(packaged),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert packaged_out.returncode == 0, packaged_out.stderr
    archives = list(packaged.glob("webmedia-dl-*.zip"))
    assert len(archives) == 6
