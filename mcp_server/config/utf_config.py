"""
UTF Phase 2 — unified configuration schema.

Reads .utf/utf-config.yaml from the project root and returns a typed UTFConfig
dataclass with sensible defaults. All Phase 2 modules import from here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML is required for utf_config. Install it with: pip install pyyaml"
    ) from exc


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RegistryConfig:
    backend: str = "sqlite"          # sqlite | rest
    sqlite_path: str = ".utf/utf.db"
    rest_url: Optional[str] = None
    rest_api_key: Optional[str] = None  # also reads UTF_REGISTRY_API_KEY env var


@dataclass
class ExecutionConfig:
    enabled: bool = True
    timeout_seconds: int = 120
    auto_run_after_generate: bool = False


@dataclass
class MutationConfig:
    enabled: bool = False
    minimum_score: float = 0.70
    block_below: float = 0.50
    timeout_seconds: int = 300


@dataclass
class FeedbackConfig:
    watcher_enabled: bool = False
    ci_listener_port: int = 9876
    delta_generation: bool = True


@dataclass
class TemplateCompletionConfig:
    enabled: bool = True
    fill_assertions: bool = True
    fill_fixtures: bool = True
    fill_http_paths: bool = True


@dataclass
class ReportingConfig:
    auto_report: bool = True                          # Write report on every run_engine() call
    report_dir: str = ".utf/reports"                  # Where reports land (relative to project root)
    formats: list = field(default_factory=lambda: ["html", "junit", "json"])
    open_html: bool = False                           # Auto-open browser after writing (dev mode)
    report_filename_prefix: str = "contract"         # contract_YYYYMMDD_HHMMSS.*
    keep_last_n: int = 20                             # Rotate old reports beyond this count


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

@dataclass
class UTFConfig:
    registry: RegistryConfig = field(default_factory=RegistryConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    mutation: MutationConfig = field(default_factory=MutationConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    template_completion: TemplateCompletionConfig = field(
        default_factory=TemplateCompletionConfig
    )
    reporting: ReportingConfig = field(default_factory=ReportingConfig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge(section_cls, defaults_instance, overrides: dict):
    """Return a new dataclass instance with *overrides* applied over defaults."""
    merged = {
        k: overrides.get(k, getattr(defaults_instance, k))
        for k in defaults_instance.__dataclass_fields__
    }
    return section_cls(**merged)


def _build_config(raw: dict) -> UTFConfig:
    """Build a UTFConfig from a parsed YAML dict, merging over defaults."""
    registry_defaults = RegistryConfig()
    execution_defaults = ExecutionConfig()
    mutation_defaults = MutationConfig()
    feedback_defaults = FeedbackConfig()
    tc_defaults = TemplateCompletionConfig()
    reporting_defaults = ReportingConfig()

    registry = _merge(RegistryConfig, registry_defaults, raw.get("registry", {}))
    execution = _merge(ExecutionConfig, execution_defaults, raw.get("execution", {}))
    mutation = _merge(MutationConfig, mutation_defaults, raw.get("mutation", {}))
    feedback = _merge(FeedbackConfig, feedback_defaults, raw.get("feedback", {}))
    template_completion = _merge(
        TemplateCompletionConfig, tc_defaults, raw.get("template_completion", {})
    )
    reporting = _merge(ReportingConfig, reporting_defaults, raw.get("reporting", {}))

    # Env-var fallback for registry API key
    if registry.rest_api_key is None:
        env_key = os.environ.get("UTF_REGISTRY_API_KEY")
        if env_key:
            registry.rest_api_key = env_key

    return UTFConfig(
        registry=registry,
        execution=execution,
        mutation=mutation,
        feedback=feedback,
        template_completion=template_completion,
        reporting=reporting,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_utf_config(cwd: Optional[Path] = None) -> UTFConfig:
    """Load .utf/utf-config.yaml from *cwd* and return a UTFConfig.

    - If *cwd* is None, defaults to Path.cwd().
    - If the config file does not exist, silently returns defaults.
    - Raises ValueError (with a clear message) on malformed YAML.
    """
    root = cwd if cwd is not None else Path.cwd()
    config_path = root / ".utf" / "utf-config.yaml"

    if not config_path.exists():
        return _build_config({})

    try:
        text = config_path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Malformed YAML in {config_path}: {exc}"
        ) from exc

    return _build_config(raw)


# ---------------------------------------------------------------------------
# Cached accessor (per-cwd, module-level dict cache)
# ---------------------------------------------------------------------------

_config_cache: dict[str, UTFConfig] = {}


def get_utf_config(cwd: Optional[Path] = None) -> UTFConfig:
    """Cached version of load_utf_config.  Caches per resolved cwd path."""
    root = (cwd if cwd is not None else Path.cwd()).resolve()
    key = str(root)
    if key not in _config_cache:
        _config_cache[key] = load_utf_config(root)
    return _config_cache[key]
