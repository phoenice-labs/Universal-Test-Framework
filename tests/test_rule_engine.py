"""Tests for the rule_engine: run_engine() and EngineOutput."""
import pytest
import dataclasses
import sys
sys.path.insert(0, '.')
from mcp_server.engine.rule_engine import run_engine, EngineOutput


def test_zero_args_returns_engine_output():
    r = run_engine()
    assert isinstance(r, EngineOutput)
    assert isinstance(r.tests, list)


def test_requirements_only_generates_passing_tests(sample_requirements):
    r = run_engine(requirements_text=sample_requirements, language='python')
    assert len(r.tests) > 0
    for t in r.tests:
        fields = {f.name: getattr(t, f.name) for f in dataclasses.fields(t)}
        assert fields['validation_score'] >= 0.85, (
            f"Test {fields['test_id']} score {fields['validation_score']} < 0.85"
        )


def test_source_and_requirements(sample_python_source, sample_requirements):
    r = run_engine(
        source_code=sample_python_source,
        requirements_text=sample_requirements,
        test_type='unit',
        language='python',
        framework='pytest',
    )
    assert len(r.tests) >= 1
    assert r.detected_language == 'python'


def test_typescript_generation():
    r = run_engine(
        source_code='class UserSvc { getUser(id: string): User { return db.find(id); } }',
        requirements_text='US-002: UserSvc.getUser returns user by ID',
        test_type='unit',
        language='typescript',
    )
    assert r.detected_language == 'typescript'
    assert len(r.tests) > 0


def test_java_api_generation():
    r = run_engine(
        source_code='@GetMapping("/users/{id}") public User getUser(@PathVariable Long id) {}',
        requirements_text='US-003: GET /users/{id} returns 200',
        test_type='api',
        language='java',
    )
    assert len(r.tests) > 0


def test_engine_output_fields():
    r = run_engine()
    expected = [
        'tests', 'blocked_tests', 'traceability_matrix', 'detected_language',
        'detected_framework', 'detection_confidence', 'validation_errors',
        'mutation_score', 'mutation_blocked',
    ]
    actual = {f.name for f in dataclasses.fields(r)}
    for field in expected:
        assert field in actual, f"EngineOutput missing field: {field}"


def test_all_tests_have_8_sections(sample_requirements):
    r = run_engine(requirements_text=sample_requirements, language='python')
    for t in r.tests:
        fields = {f.name: getattr(t, f.name) for f in dataclasses.fields(t)}
        for section in [
            'test_id', 'why_generated', 'requirement_mapping', 'how_it_exercises',
            'coverage_contribution', 'expected_outcome', 'gaps_missing', 'meaningfulness_check',
        ]:
            assert fields.get(section), f"Test missing section: {section}"


def test_no_blocked_tests_on_valid_input(sample_python_source, sample_requirements):
    r = run_engine(
        source_code=sample_python_source,
        requirements_text=sample_requirements,
        language='python',
    )
    assert len(r.blocked_tests) == 0


def test_validation_errors_is_list():
    r = run_engine()
    assert isinstance(r.validation_errors, list)


def test_detection_confidence_type():
    r = run_engine()
    assert isinstance(r.detection_confidence, (float, int, type(None)))


def test_mutation_score_field_present():
    r = run_engine()
    assert hasattr(r, 'mutation_score')
    # mutation_score may be None when mutation testing is disabled
    assert r.mutation_score is None or isinstance(r.mutation_score, float)


def test_blocked_tests_is_list():
    r = run_engine()
    assert isinstance(r.blocked_tests, list)


def test_traceability_matrix_is_list(sample_requirements):
    r = run_engine(requirements_text=sample_requirements, language='python')
    assert isinstance(r.traceability_matrix, list)
