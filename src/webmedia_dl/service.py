"""Authenticated loopback worker API. Clients never talk to a hosted backend."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

from webmedia_dl import __version__
from webmedia_dl.continuity import validate_companion_message
from webmedia_dl.diagnostics import doctor
from webmedia_dl.dispatcher import QueueDispatcher
from webmedia_dl.domain.enums import IntakeKind, Surface
from webmedia_dl.domain.models import BrowserEvidence, ExportIntent
from webmedia_dl.envelope import open_payload, seal_payload
from webmedia_dl.errors import (
    CancelledError,
    DelegationDenied,
    IntakeError,
    NetworkPolicyError,
    PauseRequested,
    WebMediaError,
)
from webmedia_dl.names import DISPLAY_NAME
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.settings import Settings
from webmedia_dl.staging import assert_staging_size, declared_content_length, ingest_staged_upload
from webmedia_dl.support import write_support_bundle

bearer = HTTPBearer(auto_error=False)


def job_detail_payload(pipeline: Pipeline, job_id: UUID) -> dict[str, Any]:
    job = pipeline.job(job_id)
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job_id)]
    artifact_ids: list[str] = []
    for item in pipeline.history_entries():
        if item["job_id"] == str(job_id):
            artifact_ids = list(item.get("artifact_ids") or [])
            break
    return {"job": job.model_dump(mode="json"), "events": events, "artifact_ids": artifact_ids}


def run_next_payload(pipeline: Pipeline) -> dict[str, Any]:
    job = pipeline.run_next()
    if job is None:
        return {"job": None, "events": []}
    events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job.job_id)]
    return {"job": job.model_dump(mode="json"), "events": events}


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locator: str
    surface: Surface = Surface.CLI
    html: str | None = None
    intent: ExportIntent = Field(default_factory=ExportIntent)
    cookies: str | None = None
    local_user_confirmed: bool = False
    pairing_id: UUID | None = None
    session_key: str | None = None
    evidence: list[BrowserEvidence] = Field(default_factory=list)
    wait: bool = True
    intake_kind: IntakeKind | None = None


class PlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locator: str
    surface: Surface = Surface.CLI
    html: str | None = None
    intent: ExportIntent = Field(default_factory=ExportIntent)
    evidence: list[BrowserEvidence] = Field(default_factory=list)
    local_user_confirmed: bool = False
    pairing_id: UUID | None = None
    session_key: str | None = None


class PairStartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_profile_id: str = "personal-restricted"


class PairConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_id: UUID


class EnvelopeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_id: UUID
    session_key: str
    payload: dict = Field(default_factory=dict)


class OpenEnvelopeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_id: UUID
    session_key: str
    nonce: str
    ciphertext: str
    mac: str


class ControlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nativeCommand: str | None = None
    subprocessWorker: bool | None = None

    @model_validator(mode="after")
    def reject_native_runner(self) -> ControlBody:
        if self.nativeCommand not in (None, ""):
            raise ValueError("nativeCommand is not allowed.")
        if self.subprocessWorker is True:
            raise ValueError("subprocessWorker cannot be true.")
        return self


class CompanionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    locator: str | None = None
    job_id: UUID | None = None
    jobId: UUID | None = None
    surface: Surface | None = None
    nativeCommand: str | None = None
    subprocessWorker: bool = False
    pairing_id: UUID | None = None
    session_key: str | None = None
    nonce: str | None = None
    ciphertext: str | None = None
    mac: str | None = None


def _token_file(data_dir: Path) -> Path:
    return data_dir / "worker.token"


def load_or_create_token(data_dir: Path) -> str:
    path = _token_file(data_dir)
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if not token:
            msg = "Worker token file is empty."
            raise WebMediaError(msg)
        path.chmod(0o600)
        return token
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)
    return token


def create_app(data_dir: Path | None = None, *, enable_dispatcher: bool = False) -> FastAPI:
    settings = Settings(data_dir=data_dir)
    root = settings.resolved_data_dir()
    token = load_or_create_token(root)
    pipeline = Pipeline(data_dir=root)
    dispatcher = QueueDispatcher(pipeline)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if enable_dispatcher:
            dispatcher.start()
        yield
        dispatcher.stop()

    app = FastAPI(title=DISPLAY_NAME, version=__version__, lifespan=lifespan)

    def require_auth(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        x_token: str | None = Header(default=None, alias="X-WebMedia-Token"),
        x_pairing: str | None = Header(default=None, alias="X-WebMedia-Pairing"),
        x_session: str | None = Header(default=None, alias="X-WebMedia-Session"),
    ) -> dict[str, str]:
        presented = credentials.credentials if credentials else x_token
        if presented == token:
            return {"actor": "mac"}
        if x_pairing and x_session:
            try:
                pipeline.pairing.require_confirmed(UUID(x_pairing), x_session)
            except (DelegationDenied, ValueError) as exc:
                raise HTTPException(status_code=401, detail="Unauthorized pairing") from exc
            return {"actor": "paired", "pairing_id": x_pairing, "session_key": x_session}
        raise HTTPException(status_code=401, detail="Unauthorized")

    def require_mac(auth: dict[str, str] = Depends(require_auth)) -> dict[str, str]:
        if auth.get("actor") != "mac":
            raise HTTPException(
                status_code=403,
                detail="Only the Mac worker can confirm pairing.",
            )
        return auth

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": DISPLAY_NAME}

    @app.post("/v1/staging")
    async def stage_upload(
        request: Request,
        auth: dict[str, str] = Depends(require_auth),
        x_webmedia_digest: str | None = Header(default=None, alias="X-WebMedia-Digest"),
        x_webmedia_filename: str | None = Header(default=None, alias="X-WebMedia-Filename"),
    ) -> dict:
        if not x_webmedia_digest:
            raise HTTPException(status_code=400, detail="X-WebMedia-Digest is required.")
        max_bytes = pipeline.host_profile.max_download_bytes
        try:
            declared = declared_content_length(request.headers.get("content-length"))
            body = await request.body()
            assert_staging_size(declared=declared, actual=len(body), max_bytes=max_bytes)
            return ingest_staged_upload(
                data_dir=root,
                owner=auth.get("pairing_id") or "mac",
                expected_digest=x_webmedia_digest,
                filename=x_webmedia_filename,
                chunks=iter([body]),
                max_bytes=max_bytes,
            )
        except IntakeError as exc:
            detail = str(exc)
            status = 413 if "byte bound" in detail else 400
            raise HTTPException(status_code=status, detail=detail) from exc

    @app.post("/v1/jobs")
    def submit_job(body: SubmitBody, auth: dict[str, str] = Depends(require_auth)) -> dict:
        pairing_id = body.pairing_id
        if pairing_id is None and auth.get("pairing_id"):
            pairing_id = UUID(auth["pairing_id"])
        try:
            job = pipeline.submit(
                body.locator,
                surface=body.surface,
                intent=body.intent,
                html=body.html,
                cookies=body.cookies,
                local_user_confirmed=body.local_user_confirmed,
                pairing_id=pairing_id,
                session_key=body.session_key or auth.get("session_key"),
                evidence=body.evidence or None,
                wait=body.wait,
                intake_kind=body.intake_kind,
            )
        except WebMediaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job.job_id)]
        return {"job": job.model_dump(mode="json"), "events": events}

    @app.post("/v1/plan")
    def plan_job(body: PlanBody, auth: dict[str, str] = Depends(require_auth)) -> dict:
        pairing_id = body.pairing_id
        if pairing_id is None and auth.get("pairing_id"):
            pairing_id = UUID(auth["pairing_id"])
        try:
            return pipeline.explain(
                body.locator,
                surface=body.surface,
                html=body.html,
                intent=body.intent,
                evidence=body.evidence or None,
                local_user_confirmed=body.local_user_confirmed,
                pairing_id=pairing_id,
                session_key=body.session_key or auth.get("session_key"),
            )
        except WebMediaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/doctor", dependencies=[Depends(require_auth)])
    def doctor_endpoint() -> dict:
        return doctor(data_dir=root)

    @app.get("/v1/support-bundle", dependencies=[Depends(require_auth)])
    def support_bundle() -> dict:
        dest = root / "support" / "webmedia-dl-support.zip"
        return write_support_bundle(data_dir=root, dest=dest)

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_auth)])
    def get_job(job_id: UUID) -> dict:
        try:
            return job_detail_payload(pipeline, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc

    @app.get("/v1/jobs", dependencies=[Depends(require_auth)])
    def list_jobs() -> list[dict]:
        return pipeline.history_entries()

    @app.get("/v1/artifacts", dependencies=[Depends(require_auth)])
    def list_artifacts() -> list[dict]:
        return [item.model_dump(mode="json") for item in pipeline.store.list_artifacts()]

    @app.get("/v1/artifacts/{artifact_id}/provenance", dependencies=[Depends(require_auth)])
    def artifact_provenance(artifact_id: str) -> list[dict]:
        try:
            return [item.model_dump(mode="json") for item in pipeline.store.lineage(artifact_id)]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown artifact") from exc

    @app.post("/v1/pair")
    def pair(body: Annotated[PairStartBody | None, Body()] = None) -> dict:
        profile_id = body.client_profile_id if body is not None else "personal-restricted"
        try:
            challenge = pipeline.pairing.create(profile_id, pipeline.host_worker.worker_id)
        except DelegationDenied as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "pairing_id": str(challenge.pairing_id),
            "nonce": challenge.nonce,
            "expires_at": challenge.expires_at.isoformat(),
            "worker_id": challenge.worker_id,
            "confirmed": False,
        }

    @app.post("/v1/pair/confirm", dependencies=[Depends(require_mac)])
    def confirm_pair(body: PairConfirmBody) -> dict:
        try:
            record = pipeline.pairing.confirm(body.pairing_id)
        except DelegationDenied as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "pairing_id": str(record.pairing_id),
            "confirmed": record.confirmed,
            "session_key": record.session_key,
            "expires_at": record.expires_at.isoformat(),
        }

    @app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(require_auth)])
    def cancel_job(job_id: UUID, body: Annotated[ControlBody | None, Body()] = None) -> dict:
        _ = body
        try:
            job = pipeline.cancel(job_id)
        except (CancelledError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @app.get("/v1/queue", dependencies=[Depends(require_auth)])
    def queue_status() -> dict:
        return {"paused": pipeline.queue.is_paused()}

    @app.post("/v1/queue/pause", dependencies=[Depends(require_auth)])
    def pause_queue(body: Annotated[ControlBody | None, Body()] = None) -> dict:
        _ = body
        return pipeline.pause_queue()

    @app.post("/v1/queue/resume", dependencies=[Depends(require_auth)])
    def resume_queue(body: Annotated[ControlBody | None, Body()] = None) -> dict:
        _ = body
        return pipeline.resume_queue()

    @app.post("/v1/queue/run-next", dependencies=[Depends(require_auth)])
    def run_next(body: Annotated[ControlBody | None, Body()] = None) -> dict:
        _ = body
        return run_next_payload(pipeline)

    @app.post("/v1/jobs/{job_id}/pause", dependencies=[Depends(require_auth)])
    def pause_job(job_id: UUID, body: Annotated[ControlBody | None, Body()] = None) -> dict:
        _ = body
        try:
            job = pipeline.pause_job(job_id)
        except (PauseRequested, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @app.post("/v1/jobs/{job_id}/resume", dependencies=[Depends(require_auth)])
    def resume_job(job_id: UUID, body: Annotated[ControlBody | None, Body()] = None) -> dict:
        _ = body
        try:
            job = pipeline.resume_job(job_id)
        except (PauseRequested, WebMediaError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @app.post("/v1/pair/envelope", dependencies=[Depends(require_auth)])
    def wrap_envelope(body: EnvelopeBody) -> dict:
        try:
            pipeline.pairing.require_confirmed(body.pairing_id, body.session_key)
        except DelegationDenied as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return seal_payload(body.session_key, body.payload)

    @app.post("/v1/pair/envelope/open", dependencies=[Depends(require_auth)])
    def unwrap_envelope(body: OpenEnvelopeBody) -> dict:
        try:
            pipeline.pairing.require_confirmed(body.pairing_id, body.session_key)
            opened = open_payload(
                body.session_key,
                {"nonce": body.nonce, "ciphertext": body.ciphertext, "mac": body.mac},
                ledger=pipeline.pairing.ledger,
            )
        except DelegationDenied as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if not isinstance(opened, dict):
            raise HTTPException(
                status_code=400, detail="Pairing envelope payload must be an object."
            )
        return opened

    @app.post("/v1/companion")
    def companion(body: CompanionBody, auth: dict[str, str] = Depends(require_auth)) -> dict:
        if auth.get("actor") != "mac":
            raise HTTPException(
                status_code=403,
                detail="Companion messages are forwarded by the Mac worker only.",
            )
        sealed = bool(body.nonce and body.ciphertext and body.mac)
        try:
            if sealed:
                if body.pairing_id is None or not body.session_key:
                    raise HTTPException(
                        status_code=400,
                        detail="Sealed companion messages require a confirmed pairing.",
                    )
                pipeline.pairing.require_confirmed(body.pairing_id, body.session_key)
                opened = open_payload(
                    body.session_key,
                    {
                        "nonce": body.nonce or "",
                        "ciphertext": body.ciphertext or "",
                        "mac": body.mac or "",
                    },
                    ledger=pipeline.pairing.ledger,
                )
                if not isinstance(opened, dict):
                    raise HTTPException(
                        status_code=400, detail="Companion envelope payload is invalid."
                    )
                payload = opened
            else:
                if not body.kind:
                    raise HTTPException(status_code=400, detail="Companion kind is required.")
                payload = {
                    "kind": body.kind,
                    "locator": body.locator,
                    "job_id": str(body.job_id or body.jobId) if body.job_id or body.jobId else None,
                    "nativeCommand": body.nativeCommand,
                    "subprocessWorker": body.subprocessWorker,
                }
                if body.surface is not None:
                    payload["surface"] = body.surface.value
            validate_companion_message(payload)
            return pipeline.handle_companion(payload)
        except DelegationDenied as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except WebMediaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc

    return app


def serve_worker(*, data_dir: Path | None, host: str, port: int) -> None:
    import uvicorn

    if host not in {"127.0.0.1", "localhost", "::1"}:
        msg = "Worker API binds loopback only."
        raise NetworkPolicyError(msg)
    app = create_app(data_dir, enable_dispatcher=True)
    uvicorn.run(app, host=host, port=port, log_level="info")
