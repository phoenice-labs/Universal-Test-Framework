from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MutationResult:
    adapter: str               # "mutmut" | "stryker" | "pit" | "gremlins"
    mutation_score: float      # 0.0 – 1.0 (killed/total)
    killed: int
    survived: int
    total: int
    timeout_mutants: int
    error_mutants: int
    duration_seconds: float
    output: str                # raw output (10KB cap)
    report_path: str | None    # path to HTML/JSON report if generated
    passed_threshold: bool     # True if score >= minimum_score
    blocked: bool              # True if score < block_below
    surviving_mutants: list[str] = field(default_factory=list)  # descriptions of survivors


class MutationAdapter(ABC):
    name: str
    supported_languages: list[str]

    @abstractmethod
    def is_available(self, project_dir: str) -> bool: ...

    @abstractmethod
    def run(self, source_file: str, test_file: str, project_dir: str,
            timeout: int = 300, minimum_score: float = 0.70,
            block_below: float = 0.50) -> MutationResult: ...

    def _calc_score(self, killed: int, total: int) -> float:
        return round(killed / total, 3) if total > 0 else 0.0
