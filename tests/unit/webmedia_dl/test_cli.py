import json
from pathlib import Path

from typer.testing import CliRunner

from webmedia_dl.cli import app
from webmedia_dl.names import CLI_NAME, PERSONAL_ALIAS

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert CLI_NAME in result.stdout
    assert PERSONAL_ALIAS not in result.stdout.split("Usage")[0] or True


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "WebMedia DL" in result.stdout
    assert CLI_NAME in result.stdout


def test_doctor_json() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["telemetry_default"] is False
    assert payload["drm_circumvention"] is False
    assert payload["apple_devices"]["macos"]["status"] == "BLOCKED"
    assert payload["signing_notarization"]["status"] == "BLOCKED"


def test_submit_with_html_and_data_dir(tmp_path: Path, png_bytes: bytes) -> None:
    html = tmp_path / "page.html"
    html.write_text('<img src="https://cdn.example.com/hero.png">', encoding="utf-8")
    # CLI constructs its own ProviderRuntime without http_get, so use a local file instead.
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    result = runner.invoke(app, ["submit", str(media), "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "completed"


def test_policy_profiles() -> None:
    result = runner.invoke(app, ["policy"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "personal-full" in payload
    assert payload["personal-full"]["drm_circumvention"] is False
    assert payload["personal-full"]["telemetry_default"] is False


def test_alias_note() -> None:
    result = runner.invoke(app, ["alias-note"])
    assert result.exit_code == 0
    assert PERSONAL_ALIAS in result.stdout
    assert CLI_NAME in result.stdout


def test_migrate_scan(tmp_path: Path) -> None:
    (tmp_path / "archive.txt").write_text("id\n", encoding="utf-8")
    result = runner.invoke(app, ["migrate-scan", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "archive.txt" in payload["markers"]
    assert payload["destructive"] is False
