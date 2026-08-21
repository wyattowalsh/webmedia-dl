from webmedia_dl.paths import repo_root
from webmedia_dl.schema_export import MODELS, export_schemas


def test_export_schemas_roundtrip(tmp_path) -> None:
    written = export_schemas(tmp_path)
    names = {path.name for path in written}
    for key in MODELS:
        assert f"{key}.schema.json" in names
    assert "index.json" in names
    # Repo schemas directory is populated by the same exporter.
    repo_schemas = repo_root() / "schemas"
    assert repo_schemas.is_dir()
