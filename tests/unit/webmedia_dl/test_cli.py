import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from webmedia_dl.cli import app
from webmedia_dl.names import CLI_NAME, PERSONAL_ALIAS

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert CLI_NAME in result.stdout
    assert PERSONAL_ALIAS not in result.stdout.split("Usage")[0]


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
    assert payload["original_planning_pack"]["status"] == "BLOCKED"


def test_submit_with_html_and_data_dir(tmp_path: Path, png_bytes: bytes) -> None:
    html = tmp_path / "page.html"
    html.write_text('<img src="https://cdn.example.com/hero.png">', encoding="utf-8")
    # CLI constructs its own ProviderRuntime without http_get, so use a local file instead.
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    result = runner.invoke(app, ["submit", str(media), "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["job"]["state"] == "completed"
    assert payload["events"]


def test_policy_profiles() -> None:
    result = runner.invoke(app, ["policy"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "personal-full" in payload
    assert payload["personal-full"]["drm_circumvention"] is False
    assert payload["personal-full"]["telemetry_default"] is False


def test_pair_create_and_confirm(tmp_path: Path) -> None:
    data = tmp_path / "data"
    created = runner.invoke(app, ["pair", "create", "--data-dir", str(data)])
    assert created.exit_code == 0
    payload = json.loads(created.stdout)
    assert payload["confirmed"] is False
    confirmed = runner.invoke(
        app, ["pair", "confirm", payload["pairing_id"], "--data-dir", str(data)]
    )
    assert confirmed.exit_code == 0
    body = json.loads(confirmed.stdout)
    assert body["confirmed"] is True
    assert body["session_key"]


def test_alias_note() -> None:
    result = runner.invoke(app, ["alias-note"])
    assert result.exit_code == 0
    assert PERSONAL_ALIAS in result.stdout
    assert CLI_NAME in result.stdout


def test_support_bundle_is_local_and_strips_console(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    data = tmp_path / "data"
    submitted = runner.invoke(app, ["submit", str(media), "--data-dir", str(data)])
    assert submitted.exit_code == 0
    dest = tmp_path / "bundle.zip"
    result = runner.invoke(app, ["support-bundle", "--data-dir", str(data), "--out", str(dest)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["telemetry"] is False
    assert dest.is_file()
    with zipfile.ZipFile(dest) as archive:
        names = set(archive.namelist())
        assert "doctor.json" in names
        assert "jobs.json" in names
        assert "events.json" in names
        events = json.loads(archive.read("events.json"))
        for records in events.values():
            for event in records:
                keys = event.get("payload", {})
                assert "stdout" not in keys
                assert "stderr" not in keys
                assert "argv" not in keys


def test_plan_command_local_file(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    result = runner.invoke(app, ["plan", str(media), "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["acquired"] is False
    assert payload["preferred"]["kind"] == "image"
    assert payload["preferred_by_kind"]
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-mp4")
    planned = runner.invoke(
        app,
        ["plan", str(video), "--container", "mkv", "--data-dir", str(tmp_path / "data2")],
    )
    assert planned.exit_code == 0
    body = json.loads(planned.stdout)
    assert body["acquired"] is False
    ids = [item["operation_id"] for item in body["export_operations"]]
    assert "keep-original" in ids
    assert "remux" in ids


def test_cancel_command(tmp_path: Path, png_bytes: bytes) -> None:
    from webmedia_dl.domain.enums import Surface
    from webmedia_dl.domain.models import Job
    from webmedia_dl.intake import normalize_source
    from webmedia_dl.pipeline import Pipeline

    data = tmp_path / "data"
    pipeline = Pipeline(data_dir=data)
    media = tmp_path / "queued.png"
    media.write_bytes(png_bytes)
    source = normalize_source(str(media), surface=Surface.CLI, policy_profile_id="personal-full")
    job = Job(source=source, policy_profile_id="personal-full", worker_id="local-macos")
    pipeline.queue.put_job(job)
    result = runner.invoke(app, ["cancel", str(job.job_id), "--data-dir", str(data)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "cancelled"


def test_migrate_scan(tmp_path: Path) -> None:
    (tmp_path / "archive.txt").write_text("id\n", encoding="utf-8")
    result = runner.invoke(app, ["migrate-scan", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "archive.txt" in payload["markers"]
    assert payload["destructive"] is False


def test_paste_command_and_unknown_preset(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    unknown = runner.invoke(app, ["plan", str(media), "--preset", "nope"])
    assert unknown.exit_code == 1
    assert "Unknown export preset" in unknown.stdout
    pasted = runner.invoke(
        app,
        [
            "paste",
            "https://cdn.example.com/hero.png",
            "--data-dir",
            str(tmp_path / "data"),
            "--no-wait",
        ],
    )
    assert pasted.exit_code == 0
    payload = json.loads(pasted.stdout)
    assert payload["job"]["source"]["kind"] == "paste"
    assert payload["job"]["source"]["local_path"] is None


def test_drop_command(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "dropped.png"
    media.write_bytes(png_bytes)
    result = runner.invoke(app, ["drop", str(media), "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["job"]["state"] == "completed"
    assert payload["job"]["source"]["kind"] == "drop"


def test_companion_cli_status(tmp_path: Path) -> None:
    result = runner.invoke(app, ["companion", "status", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "status"
    assert payload["paused"] is False


def test_companion_cli_positional_locator(tmp_path: Path) -> None:
    positional = runner.invoke(
        app,
        ["companion", "capture", "https://example.com/a.mp4", "--data-dir", str(tmp_path)],
    )
    assert positional.exit_code == 0
    body = json.loads(positional.stdout)
    assert body["kind"] == "capture"
    assert body["job"]["source"]["locator"] == "https://example.com/a.mp4"
    flagged = runner.invoke(
        app,
        [
            "companion",
            "capture",
            "--locator",
            "https://example.com/b.mp4",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert flagged.exit_code == 0
    assert json.loads(flagged.stdout)["job"]["source"]["locator"] == "https://example.com/b.mp4"


def test_updates_never_auto_installs() -> None:
    result = runner.invoke(app, ["updates"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["auto_install"] is False
    assert payload["providers_auto_install"] is False
    assert payload["app_store"] == "BLOCKED"


def test_package_extensions_writes_fixed_zips(tmp_path: Path) -> None:
    dest = tmp_path / "ext"
    result = runner.invoke(app, ["package-extensions", "--dest", str(dest)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["store_submission"] == "BLOCKED"
    assert len(payload["archives"]) == 6
    for item in payload["archives"]:
        assert Path(item["path"]).is_file()
        assert item["sha256"]


def test_speak_history_artifacts_provenance_and_queue(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    data = tmp_path / "data"
    spoken = runner.invoke(
        app,
        ["speak", "https://cdn.example.com/hero.png", "--data-dir", str(data), "--no-wait"],
    )
    assert spoken.exit_code == 0
    assert json.loads(spoken.stdout)["job"]["source"]["kind"] == "speak"
    submitted = runner.invoke(app, ["submit", str(media), "--data-dir", str(data)])
    assert submitted.exit_code == 0
    job_id = json.loads(submitted.stdout)["job"]["job_id"]
    shown = runner.invoke(app, ["job", job_id, "--data-dir", str(data)])
    assert shown.exit_code == 0
    history = runner.invoke(app, ["history", "--data-dir", str(data)])
    assert history.exit_code == 0
    listed = runner.invoke(app, ["artifacts", "--data-dir", str(data)])
    assert listed.exit_code == 0
    artifacts = json.loads(listed.stdout)
    assert artifacts
    proven = runner.invoke(
        app, ["provenance", artifacts[0]["artifact_id"], "--data-dir", str(data)]
    )
    assert proven.exit_code == 0
    missing = runner.invoke(app, ["provenance", "sha256:dead", "--data-dir", str(data)])
    assert missing.exit_code == 1
    paused = runner.invoke(app, ["pause", "--queue", "--data-dir", str(data)])
    assert json.loads(paused.stdout)["paused"] is True
    resumed = runner.invoke(app, ["resume", "--queue", "--data-dir", str(data)])
    assert json.loads(resumed.stdout)["paused"] is False
    empty = runner.invoke(app, ["run-next", "--data-dir", str(tmp_path / "empty-queue")])
    assert json.loads(empty.stdout)["job"] is None
    (tmp_path / "yt-dlp-archive.txt").write_text("id\n", encoding="utf-8")
    original = (tmp_path / "yt-dlp-archive.txt").read_bytes()
    applied = runner.invoke(app, ["migrate-apply", str(tmp_path)])
    assert applied.exit_code == 0
    assert (tmp_path / "yt-dlp-archive.txt").read_bytes() == original
    empty_paste = runner.invoke(app, ["paste", "--data-dir", str(data)], input="\n")
    assert empty_paste.exit_code == 1
    empty_speak = runner.invoke(app, ["speak", "--data-dir", str(data)], input="\n")
    assert empty_speak.exit_code == 1
    cancel_done = runner.invoke(app, ["cancel", job_id, "--data-dir", str(data)])
    assert cancel_done.exit_code == 1
    held = tmp_path / "queued.png"
    held.write_bytes(png_bytes)
    queued = runner.invoke(app, ["submit", str(held), "--data-dir", str(data), "--no-wait"])
    queued_id = json.loads(queued.stdout)["job"]["job_id"]
    job_paused = runner.invoke(app, ["pause", "--job", queued_id, "--data-dir", str(data)])
    assert job_paused.exit_code == 0
    job_resumed = runner.invoke(app, ["resume", "--job", queued_id, "--data-dir", str(data)])
    assert job_resumed.exit_code == 0
