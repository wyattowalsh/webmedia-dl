from pathlib import Path

import pytest

from webmedia_dl.domain.enums import IntakeKind, Surface
from webmedia_dl.errors import IntakeError, NetworkPolicyError
from webmedia_dl.intake import normalize_source


def test_https_url_stays_a_url() -> None:
    source = normalize_source(
        "https://example.com/photo.png",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    assert source.normalized_url == "https://example.com/photo.png"
    assert source.local_path is None
    assert source.kind is IntakeKind.URL


def test_file_scheme_rejected() -> None:
    with pytest.raises(IntakeError):
        normalize_source(
            "file:///tmp/secret.png",
            surface=Surface.CLI,
            policy_profile_id="personal-full",
        )


def test_javascript_scheme_rejected() -> None:
    with pytest.raises(NetworkPolicyError):
        normalize_source(
            "javascript:alert(1)",
            surface=Surface.CLI,
            policy_profile_id="personal-full",
            kind=IntakeKind.URL,
        )


def test_existing_file_intake(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake")
    source = normalize_source(
        str(path),
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    assert source.kind is IntakeKind.FILE
    assert source.local_path == str(path.resolve())
    assert source.normalized_url is None


def test_paste_kind_stays_a_url() -> None:
    source = normalize_source(
        "https://example.com/photo.png",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
        kind=IntakeKind.PASTE,
    )
    assert source.kind is IntakeKind.PASTE
    assert source.normalized_url == "https://example.com/photo.png"
    assert source.local_path is None
