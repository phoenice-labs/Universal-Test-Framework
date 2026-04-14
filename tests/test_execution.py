"""Tests for execution module: TestRunResult, adapters, CI reporter."""
import pytest
import sys
sys.path.insert(0, '.')
from mcp_server.execution.base import TestRunResult
from mcp_server.execution.ci_reporter import format_ci_report, format_junit_xml
from mcp_server.execution.runner import get_adapter, run_tests


def test_success_true_when_passing():
    r = TestRunResult('pytest', 0, 5, 0, 0, 0, 1.0, '5 passed', 'test_foo.py')
    assert r.success == True


def test_success_false_when_failed():
    r = TestRunResult('pytest', 1, 3, 2, 0, 0, 1.0, '2 failed', 'test_foo.py')
    assert r.success == False


def test_success_false_when_errors():
    r = TestRunResult('pytest', 0, 3, 0, 1, 0, 1.0, '1 error', 'test_foo.py')
    assert r.success == False


def test_success_false_nonzero_exit_even_no_failures():
    r = TestRunResult('pytest', 2, 5, 0, 0, 0, 1.0, 'exit 2', 'test_foo.py')
    assert r.success == False


def test_test_run_result_fields():
    r = TestRunResult('pytest', 0, 5, 0, 0, 1, 2.5, 'output text', 'test_foo.py')
    assert r.adapter == 'pytest'
    assert r.passed == 5
    assert r.skipped == 1
    assert r.duration_seconds == 2.5
    assert r.test_file == 'test_foo.py'


def test_error_details_default_empty():
    r = TestRunResult('pytest', 0, 1, 0, 0, 0, 0.1, '', 'test.py')
    assert r.error_details == []


def test_ci_report_structure():
    r = TestRunResult('pytest', 0, 5, 0, 0, 0, 1.0, '5 passed', 'test_foo.py')
    report = format_ci_report([r], 'my-project')
    assert 'summary' in report
    assert report['summary']['total_files'] == 1
    assert report['summary']['passed'] == 1
    assert report['summary']['success_rate'] == 100.0


def test_ci_report_with_failures():
    r = TestRunResult('pytest', 1, 3, 2, 0, 0, 1.0, '2 failed', 'test_foo.py')
    report = format_ci_report([r], 'my-project')
    assert report['summary']['failed'] == 1
    assert report['summary']['passed'] == 0
    assert report['summary']['success_rate'] == 0.0


def test_junit_xml_valid():
    r = TestRunResult('pytest', 0, 5, 0, 0, 0, 1.0, '5 passed', 'test_foo.py')
    xml = format_junit_xml([r], 'my-project')
    assert '<?xml' in xml
    assert 'testsuites' in xml or 'testsuite' in xml


def test_junit_xml_is_string():
    r = TestRunResult('pytest', 0, 1, 0, 0, 0, 0.1, '', 'test.py')
    xml = format_junit_xml([r], 'proj')
    assert isinstance(xml, str)
    assert len(xml) > 0


def test_get_adapter_no_crash(tmp_path):
    adapter = get_adapter('python', 'pytest', str(tmp_path))
    # May return None or PytestAdapter — neither should crash
    assert adapter is None or hasattr(adapter, 'run')


def test_get_adapter_unknown_language(tmp_path):
    # get_adapter falls back to any available adapter, not necessarily None
    # Just verify it doesn't crash and returns an adapter or None
    adapter = get_adapter('cobol', 'some-framework', str(tmp_path))
    assert adapter is None or hasattr(adapter, 'run')


def test_run_tests_nonexistent_returns_error():
    result = run_tests('/nonexistent/file.py', 'python', 'pytest')
    assert isinstance(result, TestRunResult)
    assert result.success == False
