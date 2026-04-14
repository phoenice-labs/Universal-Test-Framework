"""
feedback/delta_generator.py — Delta requirement detection for UTF feedback loop.

Computes stable hashes for requirements text and compares against the registry
so only new or changed requirements get new tests generated.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional


def compute_requirement_hash(requirements: str) -> str:
    """Stable hash of requirements text (normalises whitespace, lowercases)."""
    normalized = ' '.join(requirements.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _split_into_requirements(requirements_text: str) -> list[str]:
    """Split a block of requirements text into individual requirement chunks."""
    chunks = re.split(
        r'(?=\b(?:US|AC|TC|REQ|JIRA|STORY|FEAT|BUG|FIX)-[\w\d.]+\b)',
        requirements_text,
        flags=re.IGNORECASE,
    )
    chunks = [c.strip() for c in chunks if c.strip()]
    if not chunks:
        # Treat the whole text as one requirement
        chunks = [requirements_text.strip()] if requirements_text.strip() else []
    return chunks


def _extract_req_id_from_chunk(chunk: str) -> str:
    """Extract the leading requirement ID from a chunk, or derive one from its hash."""
    m = re.match(
        r'\b((?:US|AC|TC|REQ|JIRA|STORY|FEAT|BUG|FIX)-[\w\d.]+)\b',
        chunk.strip(),
        re.IGNORECASE,
    )
    if m:
        return m.group(1).upper()
    return f"REQ-{compute_requirement_hash(chunk)}"


def get_delta_requirements(
    requirements: str,
    project_id: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> dict:
    """
    Compare current requirements against what's already in the registry.

    Returns:
    {
        "new_requirements": [...],       # req IDs not yet in registry
        "changed_requirements": [...],   # req IDs with different hash
        "unchanged_requirements": [...], # req IDs already covered
        "total_requirements": N,
        "delta_required": bool,          # True if any new or changed
        "delta_summary": "3 new, 1 changed, 5 unchanged"
    }
    """
    from mcp_server.registry.registry_engine import get_registry

    registry = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    existing_records = registry.query(
        project_id=proj,
        test_type=None,
        language=None,
        status=None,
        requirement_id=None,
    )

    # Build set of covered requirement IDs
    covered_req_ids: set[str] = set()
    for record in existing_records:
        for req_id in record.requirement_ids:
            covered_req_ids.add(req_id.upper())

    # Extract stored hashes embedded in record content as "# req_hash: <hash>"
    stored_hashes: dict[str, str] = {}
    for record in existing_records:
        for req_id in record.requirement_ids:
            m = re.search(r'#\s*req_hash:\s*([a-f0-9]{16})', record.content or '')
            if m:
                stored_hashes[req_id.upper()] = m.group(1)

    chunks = _split_into_requirements(requirements)
    new_reqs: list[str] = []
    changed_reqs: list[str] = []
    unchanged_reqs: list[str] = []

    for chunk in chunks:
        req_id = _extract_req_id_from_chunk(chunk)
        current_hash = compute_requirement_hash(chunk)

        if req_id not in covered_req_ids:
            new_reqs.append(req_id)
        elif req_id in stored_hashes and stored_hashes[req_id] != current_hash:
            changed_reqs.append(req_id)
        else:
            unchanged_reqs.append(req_id)

    total = len(chunks)
    delta_required = bool(new_reqs or changed_reqs)

    parts = []
    if new_reqs:
        parts.append(f"{len(new_reqs)} new")
    if changed_reqs:
        parts.append(f"{len(changed_reqs)} changed")
    if unchanged_reqs:
        parts.append(f"{len(unchanged_reqs)} unchanged")
    delta_summary = ", ".join(parts) if parts else "no requirements found"

    return {
        "new_requirements": new_reqs,
        "changed_requirements": changed_reqs,
        "unchanged_requirements": unchanged_reqs,
        "total_requirements": total,
        "delta_required": delta_required,
        "delta_summary": delta_summary,
    }


def filter_to_delta(
    requirements: str,
    project_id: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> str:
    """Return only the new/changed requirements as a filtered string."""
    delta = get_delta_requirements(requirements, project_id=project_id, cwd=cwd)
    need_ids = set(delta["new_requirements"]) | set(delta["changed_requirements"])

    if not need_ids:
        return ""

    chunks = _split_into_requirements(requirements)
    selected: list[str] = []
    for chunk in chunks:
        req_id = _extract_req_id_from_chunk(chunk)
        if req_id in need_ids:
            selected.append(chunk)

    return "\n\n".join(selected)
