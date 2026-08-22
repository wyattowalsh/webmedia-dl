# WebMedia DL developer tasks

python := "uv run"

default:
    @just --list

sync:
    uv sync --locked --group dev

test:
    {{python}} pytest

lint:
    {{python}} ruff check
    {{python}} ruff format --check
    {{python}} ty check

doctor:
    {{python}} webmedia-dl doctor

bundle:
    {{python}} python scripts/validate_bundle.py

extensions:
    node --test tests/unit/extensions/*.mjs

schemas:
    {{python}} python -m webmedia_dl.schema_export

sync-extensions:
    {{python}} python scripts/sync_browser_extensions.py

package-extensions:
    {{python}} python scripts/package_extensions.py

pack:
    {{python}} python scripts/package_bundle.py

apple:
    bash scripts/build_apple_packages.sh

cov:
    {{python}} pytest --cov
