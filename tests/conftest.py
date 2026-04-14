"""Shared fixtures for UTF test suite."""
import pytest
from pathlib import Path


@pytest.fixture
def tmp_project(tmp_path):
    """A temporary project directory with .utf/utf-config.yaml using SQLite."""
    utf_dir = tmp_path / '.utf'
    utf_dir.mkdir()
    (utf_dir / 'utf-config.yaml').write_text(
        'registry:\n  backend: sqlite\n  sqlite_path: .utf/utf.db\n'
    )
    return tmp_path


@pytest.fixture
def sample_python_source():
    return 'def calculate_tax(amount: float, rate: float) -> float:\n    return amount * rate\n'


@pytest.fixture
def sample_requirements():
    return 'US-001: Tax calc returns amount * rate. AC-1.1: Positive amounts only. AC-1.2: Rate between 0 and 1.'


@pytest.fixture
def full_test_dict():
    return {
        'test_id': 'TC-REQ-001',
        'why_generated': 'Covers happy-path tax calculation per US-001 AC-1.1 to prevent regression in billing',
        'requirement_mapping': 'US-001: Tax calculation, AC-1.1: Positive amounts, AC-1.2: Rate range',
        'how_it_exercises': 'GIVEN valid amount=100.0 and rate=0.2 WHEN calculate_tax(100.0, 0.2) is called THEN result 20.0 is returned and no exception is raised',
        'coverage_contribution': 'Branch coverage for calculate_tax happy path; equivalence partitioning for valid inputs; 15% of billing module',
        'expected_outcome': 'Returns 20.0 exactly. assert result == 20.0. assert isinstance(result, float). No exceptions.',
        'gaps_missing': 'Does not test negative amounts, zero rate, overflow, or concurrent access scenarios.',
        'meaningfulness_check': 'Meaningful: directly validates business rule US-001. No hallucination detected as steps align with spec.',
    }
