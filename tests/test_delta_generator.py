"""Tests for delta_generator: requirement hashing and delta detection."""
import pytest
import sys
sys.path.insert(0, '.')
from mcp_server.feedback.delta_generator import (
    compute_requirement_hash,
    get_delta_requirements,
    filter_to_delta,
)


def test_same_text_same_hash():
    h1 = compute_requirement_hash('US-001: user login')
    h2 = compute_requirement_hash('US-001: user login')
    assert h1 == h2


def test_different_text_different_hash():
    h1 = compute_requirement_hash('US-001: user login')
    h2 = compute_requirement_hash('US-002: user logout')
    assert h1 != h2


def test_whitespace_normalization():
    h1 = compute_requirement_hash('US-001: user  login')
    h2 = compute_requirement_hash('US-001: user login')
    assert h1 == h2


def test_case_normalization():
    h1 = compute_requirement_hash('US-001: User Login')
    h2 = compute_requirement_hash('US-001: user login')
    assert h1 == h2


def test_hash_is_string():
    h = compute_requirement_hash('US-001: something')
    assert isinstance(h, str)
    assert len(h) > 0


def test_all_new_on_empty_registry(tmp_project):
    dr = get_delta_requirements(
        'US-001: login. US-002: logout.',
        project_id='delta-proj',
        cwd=tmp_project,
    )
    assert dr['total_requirements'] >= 1
    assert dr['delta_required'] == True
    assert isinstance(dr['new_requirements'], list)


def test_free_form_treated_as_one_requirement(tmp_project):
    dr = get_delta_requirements(
        'The system should handle edge cases gracefully.',
        project_id='delta-proj2',
        cwd=tmp_project,
    )
    assert dr['total_requirements'] == 1


def test_get_delta_returns_expected_keys(tmp_project):
    dr = get_delta_requirements(
        'US-001: login.',
        project_id='delta-proj3',
        cwd=tmp_project,
    )
    expected_keys = [
        'new_requirements', 'changed_requirements', 'unchanged_requirements',
        'total_requirements', 'delta_required', 'delta_summary',
    ]
    for key in expected_keys:
        assert key in dr, f"Missing key: {key}"


def test_filter_to_delta_returns_string(tmp_project):
    result = filter_to_delta(
        'US-001: login. US-002: logout.',
        project_id='filt-proj',
        cwd=tmp_project,
    )
    assert isinstance(result, str)


def test_delta_summary_is_string(tmp_project):
    dr = get_delta_requirements(
        'US-001: login.',
        project_id='delta-proj4',
        cwd=tmp_project,
    )
    assert isinstance(dr['delta_summary'], str)
