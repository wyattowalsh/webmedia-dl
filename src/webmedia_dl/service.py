"""Authenticated loopback worker API. Clients never talk to a hosted backend."""

from __future__ import annotations

import secrets
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from webmedia_dl import __version__
from webmedia_dl.domain.enums import Surface
from webmedia_dl.domain.models import ExportIntent
from webmedia_dl.errors import DelegationDenied, WebMediaError
from webmedia_dl.names import DISPLAY_NAME
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.settings import Settings

bearer = HTTPBearer(auto_error=False)


class SubmitBody(BaseModel):
    locator: str
    surface: Surface = Surface.CLI
    html: str | None = None
    intent: ExportIntent = Field(default_factory=ExportIntent)
    cookies: str | None = None
    local_user_confirmed: bool = False
    pairing_id: UUID | None = None
    session_key: str | None = None


class PairConfirmBody(BaseModel):
    pairing_id: UUID


def _token_file(data_dir: Path) -> Path:
    return data_dir / "worker.token"


def load_or_create_token(data_dir: Path) -> str:
    path = _token_file(data_dir)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)
    return token


def create_app(data_dir: Path | None = None) -> FastAPI:
    settings = Settings(data_dir=data_dir)
    root = settings.resolved_data_dir()
    token = load_or_create_token(root)
    pipeline = Pipeline(data_dir=root)
    app = FastAPI(title=DISPLAY_NAME, version=__version__)

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
            return {"actor": "paired", "pairing_id": x_pairing}
        raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": DISPLAY_NAME}

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
                session_key=body.session_key or None,
            )
        except WebMediaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_auth)])
    def get_job(job_id: UUID) -> dict:
        try:
            job = pipeline.job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc
        events = [event.model_dump(mode="json") for event in pipeline.queue.events_for(job_id)]
        return {"job": job.model_dump(mode="json"), "events": events}

    @app.get("/v1/jobs", dependencies=[Depends(require_auth)])
    def list_jobs() -> list[dict]:
        return [item.model_dump(mode="json") for item in pipeline.history()]

    @app.post("/v1/pair", dependencies=[Depends(require_auth)])
    def pair(client_profile_id: str = "personal-restricted") -> dict:
        challenge = pipeline.pairing.create(client_profile_id, pipeline.host_worker.worker_id)
        return {
            "pairing_id": str(challenge.pairing_id),
            "nonce": challenge.nonce,
            "expires_at": challenge.expires_at.isoformat(),
            "worker_id": challenge.worker_id,
            "confirmed": False,
        }

    @app.post("/v1/pair/confirm", dependencies=[Depends(require_auth)])
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

    return app


def serve_worker(*, data_dir: Path | None, host: str, port: int) -> None:
    import uvicorn

    app = create_app(data_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
