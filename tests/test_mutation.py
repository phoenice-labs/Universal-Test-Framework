"""Tests for mutation module: MutationResult dataclass and runner."""
import pytest
import sys
sys.path.insert(0, '.')
from mcp_server.mutation.base import MutationResult
from mcp_server.mutation.mutation_runner import get_mutation_adapter, run_mutation_tests


def test_mutation_result_threshold_pass():
    r = MutationResult('mutmut', 0.75, 15, 5, 20, 0, 0, 12.3, '', None, True, False)
    assert r.passed_threshold == True
    assert r.blocked == False


def test_mutation_result_threshold_fail():
    r = MutationResult('mutmut', 0.40, 4, 6, 10, 0, 0, 5.0, '', None, False, True)
    assert r.passed_threshold == False
    assert r.blocked == True


def test_mutation_score_range():
    r = MutationResult('mutmut', 0.85, 17, 3, 20, 0, 0, 10.0, '', None, True, False)
    assert 0.0 <= r.mutation_score <= 1.0


def test_mutation_result_zero_score():
    r = MutationResult('mutmut', 0.0, 0, 10, 10, 0, 0, 1.0, '', None, False, True)
    assert r.mutation_score == 0.0
    assert r.blocked == True


def test_mutation_result_perfect_score():
    r = MutationResult('mutmut', 1.0, 20, 0, 20, 0, 0, 10.0, '', None, True, False)
    assert r.mutation_score == 1.0
    assert r.passed_threshold == True


def test_mutation_result_fields():
    r = MutationResult('stryker', 0.70, 14, 6, 20, 1, 2, 30.0, 'output', '/path/report', True, False)
    assert r.adapter == 'stryker'
    assert r.killed == 14
    assert r.survived == 6
    assert r.total == 20
    assert r.timeout_mutants == 1
    assert r.error_mutants == 2
    assert r.duration_seconds == 30.0
    assert r.report_path == '/path/report'


def test_surviving_mutants_default_empty():
    r = MutationResult('mutmut', 0.80, 16, 4, 20, 0, 0, 5.0, '', None, True, False)
    assert r.surviving_mutants == []


def test_surviving_mutants_explicit():
    r = MutationResult(
        'mutmut', 0.80, 16, 4, 20, 0, 0, 5.0, '', None, True, False,
        surviving_mutants=['mutant_1', 'mutant_2'],
    )
    assert len(r.surviving_mutants) == 2


def test_get_adapter_no_crash(tmp_path):
    adapter = get_mutation_adapter('python', str(tmp_path))
    assert adapter is None or hasattr(adapter, 'run')


def test_get_adapter_unknown_language_no_crash(tmp_path):
    adapter = get_mutation_adapter('cobol', str(tmp_path))
    assert adapter is None


def test_run_mutation_bad_file():
    result = run_mutation_tests('/nonexistent/src.py', '/nonexistent/test.py', 'python')
    assert isinstance(result, MutationResult)
    assert result.mutation_score == 0.0
