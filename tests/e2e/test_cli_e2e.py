"""E2E CLI journeys with local files (no live network)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from webmedia_dl.cli import app

runner = CliRunner()


def test_submit_history_job_roundtrip(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "clip.png"
    media.write_bytes(png_bytes)
    data_dir = tmp_path / "data"
    submitted = runner.invoke(app, ["submit", str(media), "--data-dir", str(data_dir)])
    assert submitted.exit_code == 0
    job = json.loads(submitted.stdout)
    assert job["events"]
    assert job["job"]["state"] == "completed"
    listed = runner.invoke(app, ["history", "--data-dir", str(data_dir)])
    assert listed.exit_code == 0
    history = json.loads(listed.stdout)
    assert any(item["job_id"] == job["job"]["job_id"] for item in history)
    shown = runner.invoke(app, ["job", job["job"]["job_id"], "--data-dir", str(data_dir)])
    assert shown.exit_code == 0
    detail = json.loads(shown.stdout)
    assert detail["job"]["state"] == "completed"
    assert detail["events"]
