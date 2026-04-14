"""Tests for the 8-section test contract validator."""
import pytest
import sys
sys.path.insert(0, '.')
from mcp_server.engine.contract_validator import (
    validate_test_contract,
    validate_test_suite,
    ContractValidationResult,
)


def test_empty_dict_invalid():
    r = validate_test_contract({})
    assert r.is_valid == False
    assert r.score < 0.5


def test_full_valid_dict_passes(full_test_dict):
    r = validate_test_contract(full_test_dict)
    assert r.is_valid == True
    assert r.score >= 0.85


def test_missing_test_id_violation():
    d = {'why_generated': 'x' * 60}
    r = validate_test_contract(d)
    assert r.is_valid == False
    all_msgs = ' '.join(r.violation_messages).lower()
    assert 'test id' in all_msgs or 'tc-' in all_msgs or 'identifier' in all_msgs or 'test_id' in all_msgs


def test_wrong_test_id_format():
    r = validate_test_contract({'test_id': 'WRONG-FORMAT'})
    assert r.is_valid == False


def test_how_it_exercises_too_short():
    r = validate_test_contract({'test_id': 'TC-REQ-001', 'how_it_exercises': 'too short'})
    assert r.is_valid == False


def test_score_is_float_0_to_1():
    r = validate_test_contract({'test_id': 'TC-REQ-001'})
    assert 0.0 <= r.score <= 1.0


def test_contract_result_is_dataclass(full_test_dict):
    r = validate_test_contract(full_test_dict)
    assert isinstance(r, ContractValidationResult)
    assert hasattr(r, 'is_valid')
    assert hasattr(r, 'score')
    assert hasattr(r, 'violation_messages')
    assert hasattr(r, 'missing_sections')


def test_violation_messages_is_list():
    r = validate_test_contract({})
    assert isinstance(r.violation_messages, list)


def test_validate_suite_returns_dict(full_test_dict):
    """validate_test_suite returns a summary dict, not a list."""
    result = validate_test_suite([full_test_dict, full_test_dict])
    assert isinstance(result, dict)
    assert result['total_tests'] == 2
    assert 'passed_tests' in result
    assert 'failed_tests' in result
    assert 'average_score' in result


def test_validate_suite_all_pass(full_test_dict):
    result = validate_test_suite([full_test_dict])
    assert result['passed_tests'] >= 1


def test_validate_suite_fail_on_empty():
    result = validate_test_suite([{}])
    assert result['failed_tests'] == 1
    assert result['passed_tests'] == 0


def test_blocked_property_matches_is_valid(full_test_dict):
    r = validate_test_contract(full_test_dict)
    assert r.blocked == (not r.is_valid)


def test_minimum_score_field_present(full_test_dict):
    r = validate_test_contract(full_test_dict)
    assert hasattr(r, 'minimum_score')
    assert r.minimum_score > 0.0
