"""Tests for UTFConfig loading and YAML merging."""
import pytest
import sys
import os
from pathlib import Path
sys.path.insert(0, '.')
from mcp_server.config.utf_config import load_utf_config, get_utf_config, UTFConfig


def test_defaults_no_yaml_file():
    cfg = load_utf_config(Path('C:/nonexistent/xyz123'))
    assert cfg.registry.backend == 'sqlite'
    assert cfg.execution.enabled == True
    assert cfg.mutation.enabled == False
    assert cfg.template_completion.enabled == True


def test_yaml_override_merges(tmp_path):
    utf_dir = tmp_path / '.utf'
    utf_dir.mkdir()
    (utf_dir / 'utf-config.yaml').write_text(
        'registry:\n  backend: rest\n  rest_url: https://example.com\n'
    )
    cfg = load_utf_config(tmp_path)
    assert cfg.registry.backend == 'rest'
    assert cfg.registry.rest_url == 'https://example.com'
    assert cfg.registry.sqlite_path == '.utf/utf.db'  # default preserved


def test_malformed_yaml_raises(tmp_path):
    utf_dir = tmp_path / '.utf'
    utf_dir.mkdir()
    (utf_dir / 'utf-config.yaml').write_text('registry: [\n  broken: yaml:\n')
    with pytest.raises((ValueError, Exception)):
        load_utf_config(tmp_path)


def test_api_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv('UTF_REGISTRY_API_KEY', 'secret-key-123')
    cfg = load_utf_config(tmp_path)
    assert cfg.registry.rest_api_key == 'secret-key-123'


def test_returns_utf_config_instance():
    cfg = load_utf_config(Path('C:/nonexistent/xyz123'))
    assert isinstance(cfg, UTFConfig)


def test_registry_config_defaults():
    cfg = load_utf_config(Path('C:/nonexistent/xyz123'))
    assert cfg.registry.sqlite_path == '.utf/utf.db'
    assert cfg.registry.rest_url is None


def test_execution_config_defaults():
    cfg = load_utf_config(Path('C:/nonexistent/xyz123'))
    assert isinstance(cfg.execution.timeout_seconds, int)
    assert cfg.execution.timeout_seconds > 0


def test_mutation_config_defaults():
    cfg = load_utf_config(Path('C:/nonexistent/xyz123'))
    assert isinstance(cfg.mutation.minimum_score, float)
    assert isinstance(cfg.mutation.block_below, float)
    assert cfg.mutation.minimum_score > cfg.mutation.block_below


def test_get_utf_config_returns_config():
    cfg = get_utf_config(Path('C:/nonexistent/xyz123'))
    assert isinstance(cfg, UTFConfig)


def test_template_completion_config():
    cfg = load_utf_config(Path('C:/nonexistent/xyz123'))
    assert cfg.template_completion.fill_assertions == True
    assert cfg.template_completion.fill_fixtures == True
