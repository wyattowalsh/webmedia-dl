"""Integration: real filesystem staging with mocked HTTP."""

from pathlib import Path

from webmedia_dl.domain.enums import DestinationKind, JobState
from webmedia_dl.domain.models import ExportIntent
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRuntime


def test_publish_to_approved_directory(tmp_path: Path, png_bytes: bytes) -> None:
    dest = tmp_path / "library"
    dest.mkdir()
    runtime = ProviderRuntime(http_get=lambda url: (200, {}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_path / "data", runtime=runtime)
    job = pipeline.submit(
        "https://cdn.example.com/hero.png",
        intent=ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest),
            approved_roots=[str(dest)],
        ),
    )
    assert job.state is JobState.COMPLETED
    published = list(dest.glob("*"))
    assert published
    assert published[0].read_bytes() == png_bytes
