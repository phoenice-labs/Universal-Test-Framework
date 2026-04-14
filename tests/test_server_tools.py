"""Tests for MCP server tool functions called directly."""
import pytest
import sys
sys.path.insert(0, '.')

# Guard against missing FastMCP dependency
try:
    import mcp_server.server as srv
    _SERVER_AVAILABLE = True
except SystemExit:
    _SERVER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _SERVER_AVAILABLE,
    reason="FastMCP not installed — server tools unavailable",
)


def test_generate_tests_returns_dict():
    result = srv.generate_tests(
        test_type='unit',
        language='python',
        requirements_text='US-001: foo must bar',
    )
    assert isinstance(result, dict)
    # Result should contain tests under one of these keys
    has_tests = 'tests' in result or 'generated_tests' in result or 'suite_code' in result
    assert has_tests, f"No tests key found in result keys: {list(result.keys())}"


def test_validate_contract_with_markdown_string():
    """G2 fix: server tool must handle string input without AttributeError."""
    md = """## Test ID
TC-REQ-001
## Why Generated
Covers happy-path login per US-001 AC-1.1 to prevent unauthorized access regression into the system
## Requirement Mapping
US-001: login, AC-1.1: email required validation on authentication
## How It Exercises
GIVEN a valid user credentials WHEN login is called with email and password THEN the system returns 200 and a session token that is not null
## Coverage Contribution
Branch coverage for authentication module happy path; equivalence partitioning for valid credentials input
## Expected Outcome
Returns HTTP 200 with non-null session token. assert token is not None. assert status_code == 200 exactly.
## Gaps
Does not test brute force lockout, concurrent login, or session expiry scenarios.
## Meaningfulness
Meaningful: directly validates business rule US-001 AC-1.1. No hallucination detected as all steps align with spec."""
    try:
        result = srv.validate_test_contract(test_content=md)
        assert isinstance(result, dict)
        has_score = 'score' in result or 'validation_score' in result or 'is_valid' in result
        assert has_score, f"No score/validity key in result: {list(result.keys())}"
    except AttributeError as e:
        pytest.fail(f"G2 FAIL: AttributeError on string input: {e}")


def test_validate_contract_with_dict():
    result = srv.validate_test_contract(test_dict={
        'test_id': 'TC-REQ-001',
        'why_generated': 'Covers login per AC-1.1 to prevent unauthorized access to the system',
        'requirement_mapping': 'US-001: login, AC-1.1: email required',
        'how_it_exercises': 'GIVEN valid credentials WHEN login called THEN returns 200 and session token',
        'coverage_contribution': 'Branch coverage happy path; equivalence partitioning for valid inputs',
        'expected_outcome': 'Returns HTTP 200 with non-null token. assert token is not None.',
        'gaps_missing': 'Does not test brute force or concurrent access or session expiry.',
        'meaningfulness_check': 'Meaningful: validates US-001 AC-1.1 directly. No hallucination detected.',
    })
    assert isinstance(result, dict)


def test_health_returns_ok():
    result = srv.health()
    assert result.get('status') == 'ok'
    assert result.get('tools', 0) >= 11


def test_health_returns_version():
    result = srv.health()
    assert 'version' in result
    assert isinstance(result['version'], str)


def test_query_registry_no_crash():
    result = srv.query_registry()
    assert isinstance(result, dict)
    has_results = 'results' in result or 'records' in result or 'coverage_summary' in result
    assert has_results, f"No expected keys in result: {list(result.keys())}"


def test_generate_tests_with_source():
    result = srv.generate_tests(
        test_type='unit',
        source_code='def add(a, b):\n    return a + b\n',
        requirements_text='US-001: add function returns sum of a and b',
        language='python',
    )
    assert isinstance(result, dict)
    assert 'validation_errors' in result or 'tests' in result or 'suite_code' in result
