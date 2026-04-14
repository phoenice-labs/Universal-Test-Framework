"""
registry/backends/rest_backend.py — REST HTTP implementation of RegistryBackend.

Uses only urllib.request (stdlib) — no additional dependencies.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .base import RegistryBackend, TestRecord


def _record_to_dict(record: TestRecord) -> dict:
    return {
        "test_id": record.test_id,
        "project_id": record.project_id,
        "test_type": record.test_type,
        "language": record.language,
        "framework": record.framework,
        "requirement_ids": record.requirement_ids,
        "score": record.score,
        "content": record.content,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _dict_to_record(data: dict) -> TestRecord:
    return TestRecord(
        test_id=data.get("test_id", ""),
        project_id=data.get("project_id", ""),
        test_type=data.get("test_type", ""),
        language=data.get("language", ""),
        framework=data.get("framework", ""),
        requirement_ids=data.get("requirement_ids", []),
        score=data.get("score", 0.0),
        content=data.get("content", ""),
        status=data.get("status", "generated"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


class RESTBackend(RegistryBackend):
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _request(self, method: str, path: str, body: dict | None = None) -> dict | list:
        url = self._base_url + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise RuntimeError(f"Registry REST error {exc.code}: {body_text}") from exc

    # ------------------------------------------------------------------
    def upsert(self, record: TestRecord) -> None:
        self._request("POST", "/api/tests", _record_to_dict(record))

    def query(
        self,
        project_id: str | None,
        test_type: str | None,
        language: str | None,
        status: str | None,
        requirement_id: str | None,
    ) -> list[TestRecord]:
        params: dict[str, str] = {}
        if project_id is not None:
            params["project_id"] = project_id
        if test_type is not None:
            params["test_type"] = test_type
        if language is not None:
            params["language"] = language
        if status is not None:
            params["status"] = status
        if requirement_id is not None:
            params["requirement_id"] = requirement_id

        qs = ("?" + urllib.parse.urlencode(params)) if params else ""
        result = self._request("GET", f"/api/tests{qs}")
        records = result if isinstance(result, list) else result.get("records", [])
        return [_dict_to_record(r) for r in records]

    def get_by_id(self, test_id: str, project_id: str) -> Optional[TestRecord]:
        qs = "?" + urllib.parse.urlencode({"project_id": project_id})
        try:
            data = self._request("GET", f"/api/tests/{test_id}{qs}")
            return _dict_to_record(data) if data else None
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise

    def mark_status(self, test_id: str, project_id: str, status: str) -> None:
        self._request("PATCH", f"/api/tests/{test_id}/status", {
            "project_id": project_id,
            "status": status,
        })

    def coverage_summary(self, project_id: str) -> dict:
        result = self._request("GET", f"/api/projects/{project_id}/coverage")
        return result if isinstance(result, dict) else {}

    def gap_analysis(self, project_id: str) -> list[str]:
        result = self._request("GET", f"/api/projects/{project_id}/gaps")
        if isinstance(result, list):
            return result
        return result.get("gaps", [])
