from __future__ import annotations

from pathlib import Path

from mcp_server.mutation.base import MutationAdapter, MutationResult
from mcp_server.mutation.mutmut_adapter import MutmutAdapter
from mcp_server.mutation.stryker_adapter import StrykerAdapter
from mcp_server.mutation.pit_adapter import PITAdapter
from mcp_server.mutation.gremlins_adapter import GremlinsAdapter

_ADAPTERS: list[MutationAdapter] = [
    MutmutAdapter(),
    StrykerAdapter(),
    PITAdapter(),
    GremlinsAdapter(),
]

# Map language → preferred adapter names (in priority order)
_LANGUAGE_ADAPTERS: dict[str, list[str]] = {
    "python": ["mutmut"],
    "javascript": ["stryker"],
    "typescript": ["stryker"],
    "java": ["pit"],
    "go": ["gremlins"],
}


def get_mutation_adapter(language: str, project_dir: str) -> MutationAdapter | None:
    """Return the first available adapter for the given language."""
    preferred = _LANGUAGE_ADAPTERS.get(language.lower(), [])
    # Try preferred adapters first
    for adapter in _ADAPTERS:
        if adapter.name in preferred and adapter.is_available(project_dir):
            return adapter
    # Fall back: any adapter that supports the language and is available
    for adapter in _ADAPTERS:
        if language.lower() in adapter.supported_languages and adapter.is_available(project_dir):
            return adapter
    return None


def run_mutation_tests(
    source_file: str,
    test_file: str,
    language: str,
    project_dir: str | None = None,
    timeout: int = 300,
    minimum_score: float = 0.70,
    block_below: float = 0.50,
) -> MutationResult:
    """Find the appropriate adapter and run mutation testing.

    Returns a structured MutationResult. If no adapter is found for the
    language/environment, returns an error result rather than raising.
    """
    resolved_dir = project_dir or str(Path.cwd())

    adapter = get_mutation_adapter(language, resolved_dir)

    if adapter is None:
        return MutationResult(
            adapter="none",
            mutation_score=0.0,
            killed=0,
            survived=0,
            total=0,
            timeout_mutants=0,
            error_mutants=0,
            duration_seconds=0.0,
            output=f"No mutation adapter available for language '{language}'",
            report_path=None,
            passed_threshold=False,
            blocked=False,
        )

    try:
        return adapter.run(
            source_file=source_file,
            test_file=test_file,
            project_dir=resolved_dir,
            timeout=timeout,
            minimum_score=minimum_score,
            block_below=block_below,
        )
    except Exception as exc:
        return MutationResult(
            adapter=adapter.name,
            mutation_score=0.0,
            killed=0,
            survived=0,
            total=0,
            timeout_mutants=0,
            error_mutants=0,
            duration_seconds=0.0,
            output=f"Adapter error: {exc}",
            report_path=None,
            passed_threshold=False,
            blocked=False,
        )
