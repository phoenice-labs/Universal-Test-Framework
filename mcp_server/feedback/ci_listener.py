"""
feedback/ci_listener.py — Accepts CI test results via file or HTTP webhook.

File mode:  reads a JSON results file written by CI pipeline.
Webhook mode: runs a lightweight HTTP server that accepts POST /api/results.

Result format:
  {
    "project_id": "my-project",
    "results": [
      {"test_id": "TC-REQ-001", "status": "passed"},
      {"test_id": "TC-REQ-002", "status": "failed"}
    ]
  }
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional


def _apply_results(payload: dict, registry_cwd: Optional[Path]) -> dict:
    """Apply a parsed CI results payload to the registry. Returns a summary."""
    results = payload.get("results", [])
    project_id = payload.get("project_id")

    passed = 0
    failed = 0
    errors = 0

    try:
        from mcp_server.registry.registry_engine import get_registry
        registry = get_registry(registry_cwd)

        # Build a lookup of all existing test records
        all_records = registry.query(
            project_id=project_id,
            test_type=None,
            language=None,
            status=None,
            requirement_id=None,
        )
        record_map = {r.test_id: r for r in all_records}

        for item in results:
            test_id = item.get("test_id", "").strip()
            status = item.get("status", "").strip().lower()
            if not test_id:
                errors += 1
                continue

            # Normalize status to registry values
            reg_status = "executed" if status == "passed" else "failed"

            if test_id in record_map:
                rec = record_map[test_id]
                registry.mark_status(test_id, rec.project_id, reg_status)
            elif project_id:
                # Record might not exist yet — still mark via project_id best-effort
                try:
                    registry.mark_status(test_id, project_id, reg_status)
                except Exception:
                    errors += 1
                    continue
            else:
                errors += 1
                continue

            if status == "passed":
                passed += 1
            else:
                failed += 1

    except Exception as exc:
        return {
            "processed": len(results),
            "passed": passed,
            "failed": failed,
            "errors": errors + max(0, len(results) - passed - failed - errors),
            "error": str(exc),
        }

    return {
        "processed": len(results),
        "passed": passed,
        "failed": failed,
        "errors": errors,
    }


class _ResultsHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for POST /api/results."""

    registry_cwd: Optional[Path] = None  # set on the class before starting server
    _last_summary: dict = {}
    _requests_processed: int = 0

    # ── HMAC signature verification ──────────────────────────────────────────

    def _verify_signature(self, body: bytes) -> bool:
        """Return True if the request passes HMAC-SHA256 verification (or auth disabled)."""
        secret = os.environ.get("UTF_CI_SECRET", "")
        if not secret:
            return True  # auth disabled — backward-compatible default
        provided = self.headers.get("X-UTF-Signature", "")
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(provided, expected)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/results":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # HMAC authentication
        if not self._verify_signature(body):
            msg = json.dumps({"error": "invalid signature"}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        try:
            payload = json.loads(body)
            summary = _apply_results(payload, self.__class__.registry_cwd)
            _ResultsHandler._last_summary = summary
            _ResultsHandler._requests_processed += 1
            response = json.dumps({"ok": True, "summary": summary}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except Exception as exc:
            msg = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            msg = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args) -> None:  # noqa: D102
        pass  # Suppress default HTTP access logging


class CIListener:
    """Accepts CI results via file or HTTP webhook and updates the registry."""

    def __init__(
        self,
        port: int = 9876,
        registry_cwd: Optional[Path] = None,
    ) -> None:
        self._port = port
        self._registry_cwd = registry_cwd
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    def start_webhook_server(self) -> None:
        """Start non-blocking HTTP server in a daemon thread."""
        if self._running:
            return

        _ResultsHandler.registry_cwd = self._registry_cwd
        self._server = HTTPServer(("127.0.0.1", self._port), _ResultsHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="utf-ci-listener",
            daemon=True,
        )
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        """Shut down the webhook server if running."""
        if self._server:
            self._server.shutdown()
            self._running = False

    # ------------------------------------------------------------------
    @staticmethod
    def load_results_file(
        file_path: str,
        registry_cwd: Optional[Path] = None,
    ) -> dict:
        """Process a CI results JSON file and update registry. Returns summary."""
        path = Path(file_path)
        if not path.exists():
            return {
                "processed": 0, "passed": 0, "failed": 0, "errors": 0,
                "error": f"File not found: {file_path}",
            }

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "processed": 0, "passed": 0, "failed": 0, "errors": 0,
                "error": f"Invalid JSON: {exc}",
            }

        return _apply_results(payload, registry_cwd)

    # ------------------------------------------------------------------
    def get_status(self) -> dict:
        """Return current listener status."""
        auth_enabled = bool(os.environ.get("UTF_CI_SECRET", ""))
        return {
            "running": self._running,
            "port": self._port,
            "auth_enabled": auth_enabled,
            "requests_processed": _ResultsHandler._requests_processed,
            "mode": "webhook" if self._running else "idle",
            "last_summary": _ResultsHandler._last_summary,
        }
