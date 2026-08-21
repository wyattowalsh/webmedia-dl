"""Background queue runner for the loopback worker. Does not choose policy."""

from __future__ import annotations

import threading

from loguru import logger

from webmedia_dl.pipeline import Pipeline


class QueueDispatcher:
    def __init__(self, pipeline: Pipeline, *, interval: float = 0.25) -> None:
        self.pipeline = pipeline
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="webmedia-dl-queue",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self.pipeline.run_next()
            except Exception:
                logger.exception("queue dispatcher failed")
                job = None
            if job is None:
                self._stop.wait(self.interval)
