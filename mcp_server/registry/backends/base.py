"""
registry/backends/base.py — Abstract base class for registry backends.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TestRecord:
    """Represents a single stored test entry in the registry."""
    test_id: str
    test_type: str
    language: str
    framework: str
    requirement_ids: list[str]
    score: float
    content: str
    project_id: str
    status: str          # "generated" | "executed" | "failed" | "gap"
    created_at: str      # ISO timestamp
    updated_at: str      # ISO timestamp


class RegistryBackend(ABC):
    @abstractmethod
    def upsert(self, record: TestRecord) -> None: ...

    @abstractmethod
    def query(
        self,
        project_id: str | None,
        test_type: str | None,
        language: str | None,
        status: str | None,
        requirement_id: str | None,
    ) -> list[TestRecord]: ...

    @abstractmethod
    def get_by_id(self, test_id: str, project_id: str) -> Optional[TestRecord]: ...

    @abstractmethod
    def mark_status(self, test_id: str, project_id: str, status: str) -> None: ...

    @abstractmethod
    def coverage_summary(self, project_id: str) -> dict: ...

    @abstractmethod
    def gap_analysis(self, project_id: str) -> list[str]: ...
