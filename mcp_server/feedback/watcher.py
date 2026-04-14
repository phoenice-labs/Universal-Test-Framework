"""
feedback/watcher.py — Background file watcher for UTF test files.

Uses os.stat polling (no watchdog dependency) for cross-platform compatibility.
Marks deleted/modified test files in the registry as 'gap' or updates timestamps.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Optional


_TEST_FILE_PATTERN = re.compile(r'test[_s].*\.py$|\.test\.[jt]sx?$|Test\.java$|_test\.go$', re.IGNORECASE)
_TEST_ID_PATTERN = re.compile(r'\b(?:TC|TEST)-[\w\d.]+\b', re.IGNORECASE)


class TestFileWatcher:
    """Polls test files for changes, deletions, and status updates.

    Uses polling (not inotify/FSEvents) so it works cross-platform without extra deps.
    Registry updates are best-effort — wrapped in try/except so watcher never crashes.
    """

    def __init__(
        self,
        project_dir: str,
        registry_cwd: Optional[Path] = None,
        poll_interval: float = 5.0,
    ) -> None:
        self._project_dir = Path(project_dir)
        self._registry_cwd = registry_cwd
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Maps file_path -> (mtime, size) for change detection
        self._file_stats: dict[str, tuple[float, int]] = {}

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start background polling thread (daemon=True)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll,
            name="utf-file-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._poll_interval + 2)

    # ------------------------------------------------------------------
    def _poll(self) -> None:
        """Main polling loop — checks for deleted/modified test files."""
        # Build initial snapshot
        self._file_stats = self._scan_test_files()

        while not self._stop_event.is_set():
            # Use wait() so stop() wakes us up immediately instead of sleeping full interval
            self._stop_event.wait(timeout=self._poll_interval)
            if self._stop_event.is_set():
                break

            current = self._scan_test_files()

            # Detect deletions
            for path in list(self._file_stats):
                if path not in current:
                    self._handle_deleted(path)

            # Detect modifications
            for path, (mtime, size) in current.items():
                prev = self._file_stats.get(path)
                if prev is None:
                    # New file — record it
                    pass
                elif (mtime, size) != prev:
                    self._handle_modified(path)

            self._file_stats = current

    def _scan_test_files(self) -> dict[str, tuple[float, int]]:
        """Walk project_dir and return {path: (mtime, size)} for test files."""
        result: dict[str, tuple[float, int]] = {}
        try:
            for root, _dirs, files in os.walk(str(self._project_dir)):
                for fname in files:
                    if _TEST_FILE_PATTERN.search(fname):
                        full = os.path.join(root, fname)
                        try:
                            st = os.stat(full)
                            result[full] = (st.st_mtime, st.st_size)
                        except OSError:
                            pass
        except OSError:
            pass
        return result

    # ------------------------------------------------------------------
    def _handle_deleted(self, file_path: str) -> None:
        """Mark all tests from this file as 'gap' in the registry."""
        try:
            from mcp_server.registry.registry_engine import get_registry
            registry = get_registry(self._registry_cwd)
            short_name = Path(file_path).name
            records = registry.query(
                project_id=None,
                test_type=None,
                language=None,
                status=None,
                requirement_id=None,
            )
            for record in records:
                if short_name in (record.content or ""):
                    registry.mark_status(record.test_id, record.project_id, "gap")
        except Exception:
            pass  # Best-effort

    def _handle_modified(self, file_path: str) -> None:
        """Re-scan file for test IDs and update registry updated_at."""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
            test_ids = _TEST_ID_PATTERN.findall(content)

            from mcp_server.registry.registry_engine import get_registry
            registry = get_registry(self._registry_cwd)

            records = registry.query(
                project_id=None,
                test_type=None,
                language=None,
                status=None,
                requirement_id=None,
            )
            record_map = {r.test_id.upper(): r for r in records}

            for test_id in test_ids:
                record = record_map.get(test_id.upper())
                if record:
                    # Touch the record — keep status, refresh updated_at via mark_status
                    registry.mark_status(record.test_id, record.project_id, record.status)
        except Exception:
            pass  # Best-effort
