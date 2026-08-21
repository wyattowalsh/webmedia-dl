"""Typer CLI. Canonical command is `webmedia-dl`; `wmdl` is a personal alias only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from loguru import logger

from webmedia_dl.compat import migrate_legacy, scan_legacy
from webmedia_dl.destinations import extract_clipboard_locator
from webmedia_dl.diagnostics import doctor
from webmedia_dl.domain.enums import DestinationKind, IntakeKind, Surface
from webmedia_dl.domain.models import ExportIntent
from webmedia_dl.errors import CancelledError, IntakeError, WebMediaError
from webmedia_dl.export import load_presets
from webmedia_dl.names import CLI_NAME, DISPLAY_NAME, PERSONAL_ALIAS
from webmedia_dl.packaging import write_extension_zips
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import builtin_profiles
from webmedia_dl.settings import Settings
from webmedia_dl.support import write_support_bundle

app = typer.Typer(
    name=CLI_NAME,
    help=f"{DISPLAY_NAME}: local-first media acquisition and export.",
    no_args_is_help=True,
    add_completion=False,
)


def _pipeline(data_dir: Path | None) -> Pipeline:
    settings = Settings(data_dir=data_dir)
    return Pipeline(data_dir=settings.resolved_data_dir())


def _reject_unknown_preset(preset: str) -> None:
    if preset not in load_presets():
        typer.echo(f"Unknown export preset {preset!r}.")
        raise typer.Exit(code=1)


@app.callback()
def _root() -> None:
    """WebMedia DL command surface."""


@app.command()
def version() -> None:
    """Print the package version."""
    from webmedia_dl import __version__

    typer.echo(f"{DISPLAY_NAME} {__version__} ({CLI_NAME})")


@app.command("doctor")
def doctor_cmd(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """Executed evidence for toolchain, providers, and blocked Apple/store gates."""
    typer.echo(json.dumps(doctor(data_dir=data_dir), indent=2))


@app.command("support-bundle")
def support_bundle_cmd(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Write a local diagnostics zip. Does not upload telemetry or provider consoles."""
    settings = Settings(data_dir=data_dir)
    root = settings.resolved_data_dir()
    dest = out or (root / "support" / "webmedia-dl-support.zip")
    payload = write_support_bundle(data_dir=root, dest=dest)
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def submit(
    locator: Annotated[str, typer.Argument(help="https URL or existing local file")],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    dest: Annotated[
        Path | None, typer.Option("--dest", help="User-approved destination directory")
    ] = None,
    allow_lossy: Annotated[bool, typer.Option("--allow-lossy")] = False,
    container: Annotated[
        str | None, typer.Option("--container", help="Preferred output container, e.g. mkv")
    ] = None,
    html: Annotated[
        Path | None, typer.Option("--html", help="Local HTML fixture instead of fetching")
    ] = None,
    cookies: Annotated[
        Path | None, typer.Option("--cookies", help="User-owned Netscape cookie file")
    ] = None,
    preset: Annotated[str, typer.Option("--preset")] = "original-sacred",
    surface: Annotated[Surface, typer.Option("--surface")] = Surface.CLI,
    pairing_id: Annotated[
        UUID | None, typer.Option("--pairing-id", help="Confirmed Mac pairing id")
    ] = None,
    session_key: Annotated[
        str | None, typer.Option("--session-key", help="Confirmed pairing session key")
    ] = None,
    wait: Annotated[bool, typer.Option("--wait/--no-wait")] = True,
    kind: Annotated[
        IntakeKind | None,
        typer.Option("--kind", help="Override intake kind: url, file, paste, drop, speak, intent"),
    ] = None,
) -> None:
    """Share, paste, or select a source. Runs the typed job pipeline."""
    _reject_unknown_preset(preset)
    intent = ExportIntent(preset_id=preset)
    if dest is not None:
        intent = ExportIntent(
            preset_id=preset,
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest.resolve()),
            approved_roots=[str(dest.resolve())],
            allow_lossy=allow_lossy,
            container_preference=container,
        )
    elif container or allow_lossy:
        intent = ExportIntent(
            preset_id=preset,
            allow_lossy=allow_lossy,
            container_preference=container,
        )
    pipeline = _pipeline(data_dir)
    html_text = html.read_text(encoding="utf-8") if html else None
    cookie_path = str(cookies.expanduser().resolve()) if cookies else None
    job = pipeline.submit(
        locator,
        surface=surface,
        intent=intent,
        html=html_text,
        cookies=cookie_path,
        pairing_id=pairing_id,
        session_key=session_key,
        local_user_confirmed=True,
        wait=wait,
        intake_kind=kind,
    )
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job.job_id)]
    typer.echo(
        json.dumps({"job": job.model_dump(mode="json"), "events": events}, indent=2, default=str)
    )
    if job.error:
        raise typer.Exit(code=1)


@app.command()
def paste(
    locator: Annotated[
        str | None,
        typer.Argument(help="Pasted https URL. Reads stdin when omitted."),
    ] = None,
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    dest: Annotated[Path | None, typer.Option("--dest")] = None,
    wait: Annotated[bool, typer.Option("--wait/--no-wait")] = True,
) -> None:
    """Paste-intake a URL. Does not treat the locator as a filesystem path."""
    try:
        text = extract_clipboard_locator((locator or sys.stdin.read()).strip())
    except IntakeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    intent = ExportIntent()
    if dest is not None:
        intent = ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest.resolve()),
            approved_roots=[str(dest.resolve())],
        )
    pipeline = _pipeline(data_dir)
    job = pipeline.submit(
        text,
        surface=Surface.CLI,
        intent=intent,
        local_user_confirmed=True,
        wait=wait,
        intake_kind=IntakeKind.PASTE,
    )
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job.job_id)]
    typer.echo(
        json.dumps({"job": job.model_dump(mode="json"), "events": events}, indent=2, default=str)
    )
    if job.error:
        raise typer.Exit(code=1)


@app.command()
def speak(
    locator: Annotated[
        str | None,
        typer.Argument(help="Spoken or dictated https URL. Reads stdin when omitted."),
    ] = None,
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    dest: Annotated[Path | None, typer.Option("--dest")] = None,
    wait: Annotated[bool, typer.Option("--wait/--no-wait")] = True,
) -> None:
    """Voice/Siri intake. The locator is a URL, never a filesystem path."""
    text = (locator or sys.stdin.read()).strip()
    if not text:
        typer.echo("Speak intake requires a URL argument or stdin.")
        raise typer.Exit(code=1)
    intent = ExportIntent()
    if dest is not None:
        intent = ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest.resolve()),
            approved_roots=[str(dest.resolve())],
        )
    pipeline = _pipeline(data_dir)
    job = pipeline.submit(
        text,
        surface=Surface.CLI,
        intent=intent,
        local_user_confirmed=True,
        wait=wait,
        intake_kind=IntakeKind.SPEAK,
    )
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job.job_id)]
    typer.echo(
        json.dumps({"job": job.model_dump(mode="json"), "events": events}, indent=2, default=str)
    )
    if job.error:
        raise typer.Exit(code=1)


@app.command()
def drop(
    path: Annotated[Path, typer.Argument(help="Existing local file dropped onto the worker")],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    dest: Annotated[Path | None, typer.Option("--dest")] = None,
    wait: Annotated[bool, typer.Option("--wait/--no-wait")] = True,
) -> None:
    """File-drop intake. Same pipeline as submit; kind is `drop`, not a URL path."""
    intent = ExportIntent()
    if dest is not None:
        intent = ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest.resolve()),
            approved_roots=[str(dest.resolve())],
        )
    pipeline = _pipeline(data_dir)
    job = pipeline.submit(
        str(path.expanduser().resolve()),
        surface=Surface.CLI,
        intent=intent,
        local_user_confirmed=True,
        wait=wait,
        intake_kind=IntakeKind.DROP,
    )
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job.job_id)]
    typer.echo(
        json.dumps({"job": job.model_dump(mode="json"), "events": events}, indent=2, default=str)
    )
    if job.error:
        raise typer.Exit(code=1)


@app.command()
def companion(
    kind: Annotated[str, typer.Argument(help="capture, pause, resume, history, status, cancel")],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    locator: Annotated[str | None, typer.Option("--locator")] = None,
    job_id: Annotated[UUID | None, typer.Option("--job")] = None,
    surface: Annotated[Surface, typer.Option("--surface")] = Surface.WATCHOS,
) -> None:
    """Forward a watchOS/tvOS companion message on the Mac worker."""
    pipeline = _pipeline(data_dir)
    payload: dict[str, object] = {"kind": kind, "nativeCommand": None, "subprocessWorker": False}
    if locator:
        payload["locator"] = locator
    if job_id is not None:
        payload["job_id"] = str(job_id)
    payload["surface"] = surface.value
    try:
        result = pipeline.handle_companion(payload)
    except WebMediaError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("plan")
def plan_cmd(
    locator: Annotated[str, typer.Argument(help="https URL or existing local file")],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    html: Annotated[Path | None, typer.Option("--html")] = None,
    surface: Annotated[Surface, typer.Option("--surface")] = Surface.CLI,
    preset: Annotated[str, typer.Option("--preset")] = "original-sacred",
) -> None:
    """Explain the ranked acquisition and export plan without acquiring media."""
    _reject_unknown_preset(preset)
    pipeline = _pipeline(data_dir)
    html_text = html.read_text(encoding="utf-8") if html else None
    payload = pipeline.explain(
        locator,
        surface=surface,
        html=html_text,
        intent=ExportIntent(preset_id=preset),
    )
    typer.echo(json.dumps(payload, indent=2, default=str))


@app.command()
def job(
    job_id: Annotated[UUID, typer.Argument()],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """Show one job and its events."""
    pipeline = _pipeline(data_dir)
    record = pipeline.job(job_id)
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job_id)]
    typer.echo(
        json.dumps({"job": record.model_dump(mode="json"), "events": events}, indent=2, default=str)
    )


@app.command()
def history(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """List jobs from the local queue."""
    pipeline = _pipeline(data_dir)
    payload = pipeline.history_entries()
    typer.echo(json.dumps(payload, indent=2, default=str))


@app.command()
def artifacts(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """List registered artifacts in the local store."""
    pipeline = _pipeline(data_dir)
    payload = [item.model_dump(mode="json") for item in pipeline.store.list_artifacts()]
    typer.echo(json.dumps(payload, indent=2, default=str))


@app.command()
def provenance(
    artifact_id: Annotated[str, typer.Argument()],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """Show content-addressed lineage for one artifact. Titles are not identity."""
    pipeline = _pipeline(data_dir)
    try:
        payload = [item.model_dump(mode="json") for item in pipeline.store.lineage(artifact_id)]
    except KeyError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(payload, indent=2, default=str))


@app.command()
def policy() -> None:
    """Show built-in policy profiles."""
    payload = {key: value.model_dump(mode="json") for key, value in builtin_profiles().items()}
    typer.echo(json.dumps(payload, indent=2))


@app.command("migrate-scan")
def migrate_scan(
    root: Annotated[Path, typer.Argument()],
) -> None:
    """Scan a legacy command-tool directory without rewriting it."""
    typer.echo(json.dumps(scan_legacy(root), indent=2))


@app.command("migrate-apply")
def migrate_apply(
    root: Annotated[Path, typer.Argument()],
) -> None:
    """Copy a sidecar index for a legacy layout. Never rewrites originals."""
    typer.echo(json.dumps(migrate_legacy(root, apply=True), indent=2))


@app.command()
def serve(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
) -> None:
    """Run the authenticated loopback worker API."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        logger.error("Worker API binds loopback only.")
        raise typer.Exit(code=2)
    from webmedia_dl.service import serve_worker

    serve_worker(data_dir=data_dir, host=host, port=port)


@app.command("run-next")
def run_next_cmd(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """Run the next accepted job if the queue is not paused."""
    pipeline = _pipeline(data_dir)
    record = pipeline.run_next()
    if record is None:
        typer.echo(json.dumps({"job": None}, indent=2))
        return
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(record.job_id)]
    typer.echo(
        json.dumps({"job": record.model_dump(mode="json"), "events": events}, indent=2, default=str)
    )
    if record.error:
        raise typer.Exit(code=1)


@app.command()
def cancel(
    job_id: Annotated[UUID, typer.Argument()],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """Cancel a job that has not finished."""
    pipeline = _pipeline(data_dir)
    try:
        record = pipeline.cancel(job_id)
    except CancelledError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(record.model_dump_json(indent=2))


@app.command("pause")
def pause_cmd(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    job_id: Annotated[UUID | None, typer.Option("--job")] = None,
    queue: Annotated[bool, typer.Option("--queue")] = False,
) -> None:
    """Pause one job or the whole local queue."""
    pipeline = _pipeline(data_dir)
    if queue or job_id is None:
        typer.echo(json.dumps(pipeline.pause_queue(), indent=2))
        return
    record = pipeline.pause_job(job_id)
    typer.echo(record.model_dump_json(indent=2))


@app.command("resume")
def resume_cmd(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    job_id: Annotated[UUID | None, typer.Option("--job")] = None,
    queue: Annotated[bool, typer.Option("--queue")] = False,
) -> None:
    """Resume a paused job or the local queue."""
    pipeline = _pipeline(data_dir)
    if queue or job_id is None:
        typer.echo(json.dumps(pipeline.resume_queue(), indent=2))
        return
    record = pipeline.resume_job(job_id)
    typer.echo(record.model_dump_json(indent=2))


pair_app = typer.Typer(help="Explicit Mac pairing. Transport does not grant capabilities.")
app.add_typer(pair_app, name="pair")


@pair_app.command("create")
def pair_create(
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
    client_profile: Annotated[str, typer.Option("--client-profile")] = "personal-restricted",
) -> None:
    """Create an expiring pairing nonce. The Mac user must confirm it."""
    pipeline = _pipeline(data_dir)
    challenge = pipeline.pairing.create(client_profile, pipeline.host_worker.worker_id)
    typer.echo(
        json.dumps(
            {
                "pairing_id": str(challenge.pairing_id),
                "nonce": challenge.nonce,
                "expires_at": challenge.expires_at.isoformat(),
                "worker_id": challenge.worker_id,
                "confirmed": False,
            },
            indent=2,
        )
    )


@pair_app.command("confirm")
def pair_confirm(
    pairing_id: Annotated[UUID, typer.Argument()],
    data_dir: Annotated[Path | None, typer.Option("--data-dir")] = None,
) -> None:
    """Confirm pairing on the Mac worker. Restricted clients cannot self-confirm."""
    pipeline = _pipeline(data_dir)
    record = pipeline.pairing.confirm(pairing_id)
    typer.echo(
        json.dumps(
            {
                "pairing_id": str(record.pairing_id),
                "confirmed": record.confirmed,
                "session_key": record.session_key,
                "expires_at": record.expires_at.isoformat(),
            },
            indent=2,
        )
    )


@app.command("package-extensions")
def package_extensions_cmd(
    dest: Annotated[Path | None, typer.Option("--dest")] = None,
) -> None:
    """Write reproducible loopback extension zips. Does not submit to browser stores."""
    written = write_extension_zips(dest_root=dest)
    typer.echo(json.dumps({"store_submission": "BLOCKED", "archives": written}, indent=2))


@app.command()
def updates() -> None:
    """Report update policy. Providers and stores are never auto-installed."""
    from webmedia_dl import __version__

    typer.echo(
        json.dumps(
            {
                "product": DISPLAY_NAME,
                "version": __version__,
                "auto_install": False,
                "providers_auto_install": False,
                "telemetry_default": False,
                "app_store": "BLOCKED",
                "browser_stores": "BLOCKED",
                "signing_notarization": "BLOCKED",
            },
            indent=2,
        )
    )


@app.command()
def alias_note() -> None:
    """Remind that wmdl is a personal alias, not the public name."""
    typer.echo(
        f"The public command is `{CLI_NAME}`. `{PERSONAL_ALIAS}` may be aliased locally "
        "but is not the canonical name."
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
