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
