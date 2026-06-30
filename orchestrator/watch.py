"""Run loops for the Tier 6 hot-reload watcher.

`ManifestWatcher.poll()` is the change signal. These helpers drive it:

  * serve()              — dependency-free interval polling. Always available.
  * serve_with_watchdog() — push-based via the optional `watchdog` package;
                            re-polls on each filesystem event under the store
                            directory. Falls back to serve() if watchdog isn't
                            installed.

`poll()` is idempotent (it diffs a directory fingerprint), so calling it on
every raw filesystem event is safe — redundant events are no-ops.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .runtime import ChangeSet, ManifestWatcher

logger = logging.getLogger(__name__)

OnChange = Callable[[ChangeSet], None]


def _apply(watcher: ManifestWatcher, on_change: OnChange | None) -> None:
    change = watcher.poll()
    if change is not None and not change.is_empty() and on_change is not None:
        on_change(change)


def serve(
    watcher: ManifestWatcher,
    interval: float = 1.0,
    on_change: OnChange | None = None,
    iterations: int | None = None,
) -> None:
    """Poll the store on an interval and apply changes. No dependencies.

    `iterations` bounds the loop (used in tests); None runs forever. The first
    poll happens immediately, so existing manifests load at startup.
    """
    count = 0
    while True:
        _apply(watcher, on_change)
        count += 1
        if iterations is not None and count >= iterations:
            return
        time.sleep(interval)


def serve_with_watchdog(
    watcher: ManifestWatcher,
    on_change: OnChange | None = None,
    fallback_interval: float = 1.0,
) -> None:
    """Push-based reload via `watchdog`. Falls back to interval polling.

    Blocks until interrupted (KeyboardInterrupt). Loads existing manifests once
    before watching.
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        logger.warning("watchdog not installed; falling back to interval polling")
        serve(watcher, interval=fallback_interval, on_change=on_change)
        return

    # Initial sync so the roster reflects what's already on disk.
    _apply(watcher, on_change)

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event) -> None:
            _apply(watcher, on_change)

    observer = Observer()
    observer.schedule(_Handler(), str(watcher.store.dir), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
