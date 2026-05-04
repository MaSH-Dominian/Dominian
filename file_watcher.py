"""
AgentGraph Intelligence - File Watcher
Watches the filesystem and updates the graph in real-time.
Debounced to avoid thrashing on bulk saves. Target: <100ms update latency.
"""

import time
import threading
from pathlib import Path
from typing import Callable, Set, Dict, Optional, Any

try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        FileCreatedEvent,
        FileModifiedEvent,
        FileDeletedEvent,
        FileMovedEvent,
    )
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    # Stub classes for graceful degradation
    class Observer:  # type: ignore
        def __init__(self): pass
        def schedule(self, *args, **kwargs): pass
        def start(self): pass
        def stop(self): pass
        def join(self, *args, **kwargs): pass
        @property
        def is_alive(self): return False
        @property
        def daemon(self): return True
        @daemon.setter
        def daemon(self, v): pass
    class FileSystemEventHandler:  # type: ignore
        pass
    class FileCreatedEvent:  # type: ignore
        def __init__(self, src): self.src_path = src; self.is_directory = False
    class FileModifiedEvent:  # type: ignore
        def __init__(self, src): self.src_path = src; self.is_directory = False
    class FileDeletedEvent:  # type: ignore
        def __init__(self, src): self.src_path = src; self.is_directory = False
    class FileMovedEvent:  # type: ignore
        def __init__(self, src, dest): self.src_path = src; self.dest_path = dest; self.is_directory = False

try:
    from __init__ import ParserRegistry
except ImportError:
    from . import ParserRegistry


class GraphFileHandler(FileSystemEventHandler):
    """
    Watchdog event handler that debounces file events
    and triggers graph updates via callbacks.
    """

    DEBOUNCE_SECONDS = 0.15  # 150ms debounce window

    def __init__(
        self,
        registry:       ParserRegistry,
        on_file_change: Callable[[str, str], None],
        on_file_delete: Callable[[str], None],
    ):
        super().__init__()
        self.registry       = registry
        self.on_file_change = on_file_change   # (path, event_type)
        self.on_file_delete = on_file_delete   # (path,)
        self._pending:  Dict[str, float] = {}  # path -> scheduled time
        self._lock      = threading.Lock()
        self._timer:    Optional[threading.Timer]  = None

    def on_created(self, event):
        if not event.is_directory and self.registry.is_supported(event.src_path):
            self._schedule(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory and self.registry.is_supported(event.src_path):
            self._schedule(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory and self.registry.is_supported(event.src_path):
            with self._lock:
                self._pending.pop(event.src_path, None)
            self.on_file_delete(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            if self.registry.is_supported(event.src_path):
                self.on_file_delete(event.src_path)
            if hasattr(event, 'dest_path') and self.registry.is_supported(event.dest_path):
                self._schedule(event.dest_path, "created")

    def _schedule(self, path: str, event_type: str):
        """Debounce: reset timer on each new event for same path."""
        with self._lock:
            self._pending[path] = time.time()
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(
            self.DEBOUNCE_SECONDS, self._flush
        )
        self._timer.daemon = True
        self._timer.start()

    def _flush(self):
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()
        for path in pending:
            try:
                self.on_file_change(path, "changed")
            except Exception:
                pass


class FileWatcher:
    """
    Manages the Watchdog observer lifecycle.
    Auto-starts on init, provides clean stop.
    Broadcasts live update events to registered listeners.
    """

    def __init__(self, db, scanner):
        self.db       = db
        self.scanner  = scanner
        self.registry = ParserRegistry()
        self._observer: Optional[Any] = None
        self._watching:   Set[str] = set()
        self._listeners: list = []
        self._lock = threading.Lock()

    def watch(self, path: str):
        """Start watching a directory (idempotent)."""
        if not _WATCHDOG_AVAILABLE:
            return
        abs_path = str(Path(path).resolve())
        if abs_path in self._watching:
            return

        handler = GraphFileHandler(
            registry       = self.registry,
            on_file_change = self._on_change,
            on_file_delete = self._on_delete,
        )

        if self._observer is None:
            self._observer = Observer()
            self._observer.daemon = True

        self._observer.schedule(handler, abs_path, recursive=True)

        if not self._observer.is_alive():
            self._observer.start()

        self._watching.add(abs_path)

    def stop(self):
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._watching.clear()

    def add_listener(self, callback: Callable):
        """Register a callback for live graph update events."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable):
        self._listeners = [l for l in self._listeners if l != callback]

    def _on_change(self, path: str, event_type: str):
        t0 = time.perf_counter()
        result = self.scanner.scan_file(path)
        latency_ms = (time.perf_counter() - t0) * 1000

        event = {
            "type":       "graph_updated",
            "file":       path,
            "event":      event_type,
            "nodes":      len(result.get("nodes", [])),
            "edges":      len(result.get("edges", [])),
            "latency_ms": round(latency_ms, 2),
            "timestamp":  time.time(),
        }
        self._broadcast(event)

    def _on_delete(self, path: str):
        self.db.clear_file(path)
        event = {
            "type":      "file_deleted",
            "file":      path,
            "timestamp": time.time(),
        }
        self._broadcast(event)

    def _broadcast(self, event: Dict):
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass

    @property
    def watching(self) -> Set[str]:
        return set(self._watching)

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
