from pathlib import Path
from uuid import uuid4

import pytest

from webmedia_dl.discovery import discover
from webmedia_dl.domain.enums import IntakeKind, JobState, MediaKind, Surface
from webmedia_dl.domain.models import BrowserEvidence, ExportIntent, MediaSource
from webmedia_dl.envelope import open_payload, seal_payload
from webmedia_dl.errors import DelegationDenied
from webmedia_dl.export import plan_export
from webmedia_dl.ledger import NonceLedger
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.providers import ProviderRequest, ProviderRuntime


def _page_source() -> MediaSource:
    return MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )


def test_javascript_urls_are_ignored() -> None:
    html = '<img src="javascript:alert(1)"><img src="https://cdn.example.com/ok.png">'
    candidates = discover(_page_source(), get_profile("personal-full"), html=html)
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    assert all(not item.startswith("javascript:") for item in urls)
    assert any(item.endswith("ok.png") for item in urls)


def test_srcset_poster_and_browser_evidence() -> None:
    html = """
    <video poster="/poster.jpg" srcset="https://cdn.example.com/clip.mp4 1x"></video>
    <meta name="twitter:image" content="https://cdn.example.com/tw.png">
    """
    evidence = [
        BrowserEvidence(url="https://cdn.example.com/captured.mp4", kind=MediaKind.VIDEO),
        BrowserEvidence(url="javascript:void(0)", kind=MediaKind.IMAGE),
    ]
    candidates = discover(
        _page_source(),
        get_profile("personal-full"),
        html=html,
        evidence=evidence,
    )
    urls = {item.retrieval_urls[0] for item in candidates if item.retrieval_urls}
    assert "https://cdn.example.com/captured.mp4" in urls
    assert "https://cdn.example.com/clip.mp4" in urls
    assert any(item.endswith("poster.jpg") for item in urls)
    assert "https://cdn.example.com/tw.png" in urls
    assert not any(item.startswith("javascript:") for item in urls)


def test_gallery_candidate_when_three_images() -> None:
    html = """
    <img src="https://cdn.example.com/a.jpg">
    <img src="https://cdn.example.com/b.jpg">
    <img src="https://cdn.example.com/c.jpg">
    """
    candidates = discover(_page_source(), get_profile("personal-full"), html=html)
    assert any(item.media_kind is MediaKind.GALLERY for item in candidates)


def test_explain_does_not_acquire(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_path / "data")
    payload = pipeline.explain(str(media))
    assert payload["acquired"] is False
    assert payload["preferred"]["kind"] == "image"
    assert pipeline.history() == []


def test_nonce_ledger_rejects_replay(tmp_path: Path) -> None:
    ledger = NonceLedger(tmp_path / "nonces.sqlite")
    key = "ab" * 32
    sealed = seal_payload(key, {"locator": "https://example.com/a.png"})
    opened = open_payload(key, sealed, ledger=ledger)
    assert opened["locator"] == "https://example.com/a.png"
    with pytest.raises(DelegationDenied):
        open_payload(key, sealed, ledger=ledger)


def test_optional_image_orient_does_not_fail_job(tmp_data: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime(
        which=lambda name: None,
        http_get=lambda url: (200, {"content-type": "image/png"}, png_bytes),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/hero.png")
    assert job.state is JobState.COMPLETED
    types = [event.type.value for event in pipeline.queue.events_for(job.job_id)]
    assert "intake.normalized" in types
    assert "discovery.completed" in types
    assert "acquisition.started" in types


def test_gallery_dl_picks_created_file(tmp_path: Path) -> None:
    def run(argv: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
        created = cwd / "album" / "01.jpg"
        created.parent.mkdir(parents=True, exist_ok=True)
        created.write_bytes(b"img")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/gallery-dl", run=run)
    result = runtime.execute(
        ProviderRequest(
            provider_id="gallery-dl",
            capability_id="acquire.gallery_dl",
            typed_inputs={
                "url": "https://example.com/album",
                "output": str(tmp_path / "missing.bin"),
            },
        ),
        tmp_path,
    )
    assert result.exit_code == 0
    assert result.output_path is not None
    assert result.output_path.name == "01.jpg"


def test_image_convert_plan() -> None:
    from webmedia_dl.domain.models import Artifact

    artifact = Artifact(
        artifact_id="sha256:ab",
        role="source",
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.IMAGE,
        storage_relpath="a.jpg",
        container="jpg",
    )
    plan = plan_export(uuid4(), artifact, ExportIntent(container_preference="png"))
    assert any(op.operation_id == "image-convert" for op in plan.operations)
