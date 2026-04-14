"""Tests for the SQLite registry backend and registry_engine public API."""
import pytest
import sys
import json
from datetime import datetime, timezone
sys.path.insert(0, '.')
from mcp_server.registry.backends.sqlite_backend import SQLiteBackend
from mcp_server.registry.backends.base import TestRecord


@pytest.fixture
def backend(tmp_path):
    return SQLiteBackend(tmp_path / 'test.db')


@pytest.fixture
def sample_record():
    now = datetime.now(timezone.utc).isoformat()
    return TestRecord(
        test_id='TC-REQ-001',
        project_id='proj-a',
        test_type='unit',
        language='python',
        framework='pytest',
        requirement_ids=['US-001', 'AC-1.1'],
        score=0.92,
        content='## Test ID\nTC-REQ-001\n## Why Generated\nCovers login',
        status='generated',
        created_at=now,
        updated_at=now,
    )


def test_upsert_and_query(backend, sample_record):
    backend.upsert(sample_record)
    results = backend.query(
        project_id='proj-a', test_type=None, language=None,
        status=None, requirement_id=None,
    )
    assert len(results) == 1
    assert results[0].test_id == 'TC-REQ-001'


def test_query_by_requirement(backend, sample_record):
    backend.upsert(sample_record)
    results = backend.query(
        project_id='proj-a', test_type=None, language=None,
        status=None, requirement_id='US-001',
    )
    assert len(results) == 1


def test_query_by_status(backend, sample_record):
    backend.upsert(sample_record)
    results = backend.query(
        project_id='proj-a', test_type=None, language=None,
        status='generated', requirement_id=None,
    )
    assert len(results) == 1
    results_other = backend.query(
        project_id='proj-a', test_type=None, language=None,
        status='executed', requirement_id=None,
    )
    assert len(results_other) == 0


def test_mark_status(backend, sample_record):
    backend.upsert(sample_record)
    backend.mark_status('TC-REQ-001', 'proj-a', 'executed')
    r = backend.get_by_id('TC-REQ-001', 'proj-a')
    assert r.status == 'executed'


def test_get_by_id(backend, sample_record):
    backend.upsert(sample_record)
    r = backend.get_by_id('TC-REQ-001', 'proj-a')
    assert r is not None
    assert r.test_id == 'TC-REQ-001'
    assert r.project_id == 'proj-a'


def test_coverage_summary(backend, sample_record):
    backend.upsert(sample_record)
    summary = backend.coverage_summary('proj-a')
    assert summary['total'] == 1
    assert summary['by_type']['unit'] == 1
    assert summary['by_language']['python'] == 1


def test_upsert_overwrites_on_same_id(backend, sample_record):
    backend.upsert(sample_record)
    updated = TestRecord(
        test_id='TC-REQ-001',
        project_id='proj-a',
        test_type='unit',
        language='python',
        framework='pytest',
        requirement_ids=['US-001'],
        score=0.95,
        content='updated',
        status='executed',
        created_at=sample_record.created_at,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    backend.upsert(updated)
    r = backend.get_by_id('TC-REQ-001', 'proj-a')
    assert r.score == 0.95
    assert r.status == 'executed'


def test_get_by_id_missing_returns_none(backend):
    r = backend.get_by_id('TC-DOES-NOT-EXIST', 'proj-x')
    assert r is None


def test_query_empty_registry(backend):
    results = backend.query(
        project_id='proj-empty', test_type=None, language=None,
        status=None, requirement_id=None,
    )
    assert results == []


def test_auto_upsert_from_run_engine(tmp_project):
    from mcp_server.engine.rule_engine import run_engine
    from mcp_server.registry.registry_engine import query_registry

    result = run_engine(
        source_code='def add(a, b): return a + b',
        requirements_text='US-001: add returns sum of a and b',
        test_type='unit',
        language='python',
        cwd=tmp_project,
    )
    qr = query_registry(project_id=tmp_project.name, cwd=tmp_project)
    assert len(qr.get('records', [])) > 0
    assert qr['records'][0]['test_id'] is not None
