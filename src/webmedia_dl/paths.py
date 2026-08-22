"""Repository and worker filesystem layout."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir

from webmedia_dl.names import CLI_NAME


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "webmedia_dl").is_dir():
            return parent
    msg = "Unable to locate the webmedia-dl repository root."
    raise FileNotFoundError(msg)


def runtime_root() -> Path:
    """Packaged runtime assets. Works from a wheel without a source checkout."""
    packaged = Path(__file__).resolve().parent / "runtime"
    if packaged.is_dir():
        return packaged
    return repo_root() / "resources"


def runtime_file(*parts: str) -> Path:
    path = runtime_root().joinpath(*parts)
    if path.exists():
        return path
    fallback = repo_root() / "resources" / Path(*parts)
    if fallback.exists():
        return fallback
    return path


def worker_data_dir(override: Path | None = None) -> Path:
    if override is not None:
        override.mkdir(parents=True, exist_ok=True)
        override.chmod(0o700)
        return override
    path = Path(user_data_dir(CLI_NAME, "WebMediaDL"))
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def staging_dir(root: Path) -> Path:
    path = root / "staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_dir(root: Path) -> Path:
    path = root / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def quarantine_dir(root: Path) -> Path:
    path = root / "quarantine"
    path.mkdir(parents=True, exist_ok=True)
    return path
