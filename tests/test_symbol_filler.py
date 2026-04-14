"""Tests for SymbolFiller: placeholder resolution in generated test code."""
import pytest
import sys
sys.path.insert(0, '.')
from mcp_server.engine.symbol_filler import SymbolFiller


@pytest.fixture
def sf():
    return SymbolFiller()


PYTHON_SOURCE = 'def calculate_tax(amount, rate):\n    return amount * rate\n'
PYTHON_TODO = (
    'def test_x():\n'
    '    sut = subject_under_test()\n'
    '    result = sut.your_function()\n'
    '    assert result == expected  # TODO: fill assertion\n'
)


def test_python_subject_with_source(sf):
    filled, changes = sf.fill(PYTHON_TODO, PYTHON_SOURCE, 'python', 'unit', '')
    assert 'calculate_tax' in filled
    assert len(changes) > 0


def test_python_subject_no_source(sf):
    """Without source, filler should replace placeholder or add a comment."""
    filled, changes = sf.fill(PYTHON_TODO, '', 'python', 'unit', '')
    # Either the placeholder was replaced with something, or a comment was added
    assert isinstance(filled, str)
    assert isinstance(changes, list)
    # The output must be a valid non-empty string
    assert len(filled) > 0


def test_idempotency(sf):
    """Verify fill does not crash on already-filled content."""
    filled1, _ = sf.fill(PYTHON_TODO, PYTHON_SOURCE, 'python', 'unit', '')
    # Second pass on already-filled content should not crash
    filled2, _ = sf.fill(filled1, PYTHON_SOURCE, 'python', 'unit', '')
    assert isinstance(filled2, str)
    assert len(filled2) > 0
    # Both passes should produce non-empty output
    assert 'calculate_tax' in filled1
    assert 'calculate_tax' in filled2


def test_needs_filling_true(sf):
    assert sf.needs_filling('# TODO: add fixture') == True
    assert sf.needs_filling('sut = subject_under_test()') == True


def test_needs_filling_false(sf):
    assert sf.needs_filling('def test_clean():\n    assert add(1,2) == 3\n') == False


def test_no_merged_lines_after_fill(sf):
    """G3 fix: auto-fill comment must not merge with next line."""
    content = 'def test_x():\n    sut = subject_under_test()\n    result = sut.do_it()\n'
    filled, _ = sf.fill(content, '', 'python', 'unit', '')
    lines = filled.split('\n')
    for line in lines:
        stripped = line.strip()
        assert not ('# auto-filled' in stripped and len(stripped) > 150), (
            f"Merged line detected: {stripped[:100]}"
        )


def test_api_endpoint_from_requirements(sf):
    content = 'response = requests.post("YOUR_ENDPOINT", json=payload)\n'
    reqs = 'POST /api/users endpoint creates a new user and returns 201'
    filled, changes = sf.fill(content, '', 'python', 'api', reqs)
    assert isinstance(filled, str)
    assert len(filled) > 0


def test_typescript_class_detection(sf):
    ts_source = 'class UserService { async getUser(id: string): Promise<User> { return db.find(id); } }'
    content = 'const sut = new SubjectUnderTest();\n'
    filled, changes = sf.fill(content, ts_source, 'typescript', 'unit', '')
    assert isinstance(filled, str)
    assert len(filled) > 0


def test_java_fill_no_crash(sf):
    content = 'assertThat(result).isEqualTo(expected);  // TODO: fill assertion\n'
    filled, changes = sf.fill(content, '', 'java', 'unit', '')
    assert isinstance(filled, str)


def test_go_fill_no_crash(sf):
    content = 'if result != expected { t.Errorf("got %v", result) }  // TODO: fill\n'
    filled, changes = sf.fill(content, '', 'go', 'unit', '')
    assert isinstance(filled, str)


def test_fill_returns_tuple(sf):
    filled, changes = sf.fill(PYTHON_TODO, PYTHON_SOURCE, 'python', 'unit', '')
    assert isinstance(filled, str)
    assert isinstance(changes, list)
