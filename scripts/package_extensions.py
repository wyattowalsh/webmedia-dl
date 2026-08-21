#!/usr/bin/env python3
"""Zip each browser capture tree with a fixed timestamp."""

from __future__ import annotations

from webmedia_dl.packaging import write_extension_zips


def main() -> int:
    for item in write_extension_zips():
        print(f"{item['path']} sha256:{item['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
