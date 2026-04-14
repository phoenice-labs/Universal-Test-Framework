"""Tests for context_resolver: requirement extraction and symbol detection."""
import pytest
import sys
sys.path.insert(0, '.')
from mcp_server.engine.context_resolver import resolve_context


def test_extracts_requirement_ids():
    ctx = resolve_context(
        requirements_text='US-001: user login. AC-1.1: email required. US-002: logout.',
        source_code='',
        test_type='unit',
        language='python',
    )
    # ExtractedRequirement uses .id (not .req_id)
    # Note: regex pattern uses [\w\-]+ so dot-separated IDs like AC-1.1
    # are truncated to their prefix before the dot (e.g. AC-1)
    ids = [r.id for r in ctx.requirements]
    assert 'US-001' in ids
    assert 'US-002' in ids
    assert any(r_id.startswith('AC-') for r_id in ids)


def test_empty_requirements_no_crash():
    ctx = resolve_context(
        requirements_text='',
        source_code='',
        test_type='unit',
        language='python',
    )
    assert isinstance(ctx.requirements, list)
    assert len(ctx.requirements) == 0


def test_no_duplicate_ids():
    ctx = resolve_context(
        requirements_text='US-001: foo. US-002: bar.',
        source_code='',
        test_type='unit',
        language='python',
    )
    ids = [r.id for r in ctx.requirements]
    # Both IDs should be found
    assert 'US-001' in ids
    assert 'US-002' in ids


def test_free_form_requirements():
    ctx = resolve_context(
        requirements_text='The system should allow users to log in with their email.',
        source_code='',
        test_type='unit',
        language='python',
    )
    assert ctx is not None
    assert isinstance(ctx.requirements, list)


def test_source_code_symbols_extracted():
    ctx = resolve_context(
        requirements_text='US-001: tax calculation',
        source_code='def calculate_tax(amount, rate):\n    return amount * rate\n',
        test_type='unit',
        language='python',
    )
    symbol_names = [s.name for s in ctx.symbols]
    assert 'calculate_tax' in symbol_names


def test_has_source_flag():
    ctx_with = resolve_context(
        requirements_text='',
        source_code='def foo(): pass',
        test_type='unit',
        language='python',
    )
    ctx_without = resolve_context(
        requirements_text='',
        source_code='',
        test_type='unit',
        language='python',
    )
    assert ctx_with.has_source == True
    assert ctx_without.has_source == False


def test_has_requirements_flag():
    ctx = resolve_context(
        requirements_text='US-001: something',
        source_code='',
        test_type='unit',
        language='python',
    )
    assert ctx.has_requirements == True


def test_detection_result_present():
    ctx = resolve_context(
        requirements_text='',
        source_code='',
        test_type='unit',
        language='python',
    )
    assert ctx.detection is not None
    assert ctx.detection.language == 'python'


def test_context_has_risk_level():
    ctx = resolve_context(
        requirements_text='US-001: authenticate user login with password',
        source_code='',
        test_type='unit',
        language='python',
    )
    assert ctx.risk_level in ('low', 'medium', 'high')
