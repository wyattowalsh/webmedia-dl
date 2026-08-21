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
from webmedia_dl.names import DISPLAY_NAME
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.settings import Settings
from webmedia_dl.transport import create_challenge

bearer = HTTPBearer(auto_error=False)


class SubmitBody(BaseModel):
    locator: str
    surface: Surface = Surface.CLI
    html: str | None = None
    intent: ExportIntent = Field(default_factory=ExportIntent)


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
    ) -> None:
        presented = credentials.credentials if credentials else x_token
        if presented != token:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": DISPLAY_NAME}

    @app.post("/v1/jobs", dependencies=[Depends(require_auth)])
    def submit_job(body: SubmitBody) -> dict:
        job = pipeline.submit(
            body.locator, surface=body.surface, intent=body.intent, html=body.html
        )
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
        challenge = create_challenge(client_profile_id, pipeline.worker.worker_id)
        return {
            "pairing_id": str(challenge.pairing_id),
            "nonce": challenge.nonce,
            "expires_at": challenge.expires_at.isoformat(),
            "worker_id": challenge.worker_id,
        }

    return app


def serve_worker(*, data_dir: Path | None, host: str, port: int) -> None:
    import uvicorn

    app = create_app(data_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
