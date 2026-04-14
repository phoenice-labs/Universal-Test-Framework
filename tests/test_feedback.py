"""Tests for the feedback loop: watcher, CI listener, gap analysis, trends."""
import pytest
import sys
import json
import time
from pathlib import Path
sys.path.insert(0, '.')
from mcp_server.feedback.watcher import TestFileWatcher
from mcp_server.feedback.ci_listener import CIListener
from mcp_server.feedback.gap_reopener import compute_coverage_health
from mcp_server.feedback.trend_reporter import save_daily_snapshot, get_coverage_trend


def test_watcher_starts_stops(tmp_path):
    w = TestFileWatcher(str(tmp_path), poll_interval=60.0)
    w.start()
    time.sleep(0.3)
    w.stop()


def test_watcher_start_stop_idempotent(tmp_path):
    """Stopping an already-stopped watcher should not crash."""
    w = TestFileWatcher(str(tmp_path), poll_interval=60.0)
    w.start()
    time.sleep(0.1)
    w.stop()
    w.stop()  # second stop should be safe


def test_ci_listener_file_mode(tmp_project):
    results_file = tmp_project / 'ci.json'
    results_file.write_text(json.dumps({
        'project_id': 'test-proj',
        'results': [
            {'test_id': 'TC-REQ-001', 'status': 'passed'},
            {'test_id': 'TC-REQ-002', 'status': 'failed'},
        ],
    }))
    summary = CIListener.load_results_file(str(results_file), registry_cwd=tmp_project)
    assert summary['processed'] == 2
    assert 'passed' in summary
    assert 'failed' in summary
    # Total passed + failed + errors should equal processed
    assert summary['passed'] + summary['failed'] + summary.get('errors', 0) == 2


def test_ci_listener_missing_file(tmp_project):
    summary = CIListener.load_results_file('/nonexistent/results.json', registry_cwd=tmp_project)
    assert summary['processed'] == 0
    assert 'error' in summary


def test_ci_listener_invalid_json(tmp_project):
    bad_file = tmp_project / 'bad.json'
    bad_file.write_text('{ not valid json }')
    summary = CIListener.load_results_file(str(bad_file), registry_cwd=tmp_project)
    assert summary['processed'] == 0
    assert 'error' in summary


def test_coverage_health_empty_registry_g4(tmp_project):
    """G4 fix: empty registry should report 0.0 health, not 1.0."""
    health = compute_coverage_health(project_id='empty-proj', cwd=tmp_project)
    assert health['has_tests'] == False
    assert health['health_score'] == 0.0
    assert health['status'] == 'no_tests'
    assert health['initialized'] == False


def test_coverage_health_returns_expected_keys(tmp_project):
    health = compute_coverage_health(project_id='health-proj', cwd=tmp_project)
    expected_keys = [
        'total_tests', 'passing', 'failing', 'gap_tests',
        'health_score', 'has_tests', 'initialized', 'status',
    ]
    for key in expected_keys:
        assert key in health, f"Missing key: {key}"


def test_trend_reporter_empty_registry(tmp_project):
    save_daily_snapshot(project_id='trend-proj', cwd=tmp_project)
    trend = get_coverage_trend(project_id='trend-proj', days=30, cwd=tmp_project)
    assert 'trend' in trend
    assert 'snapshots' in trend
    assert isinstance(trend['snapshots'], list)


def test_trend_reporter_trend_field(tmp_project):
    trend = get_coverage_trend(project_id='trend-proj2', days=30, cwd=tmp_project)
    assert trend['trend'] in ('improving', 'stable', 'degrading')


def test_trend_reporter_current_score_float(tmp_project):
    trend = get_coverage_trend(project_id='trend-proj3', days=30, cwd=tmp_project)
    assert isinstance(trend['current_score'], float)
    assert 0.0 <= trend['current_score'] <= 1.0
