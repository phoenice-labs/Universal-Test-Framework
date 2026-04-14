"""
symbol_filler.py
Phase 2 — Symbol Filler / Template Auto-Completion

Post-processes generated test content replacing TODO placeholders with real
scaffold code derived from source_code, requirements, and language patterns.
The fill() method is idempotent: calling it twice produces identical results.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ─── Language profile ─────────────────────────────────────────────────────────

@dataclass
class LanguageProfile:
    """Per-language patterns and scaffolding templates."""
    name: str
    function_patterns: list[str]
    class_patterns: list[str]
    comment_prefix: str        # "#" for Python, "//" for Java/TS/Go
    assertion_scaffold: str    # auto-filled assertion line
    fixture_scaffold: str      # uses {subject} / {Subject} placeholders
    http_client_scaffold: str  # uses {endpoint} placeholder


_PROFILES: dict[str, LanguageProfile] = {
    "python": LanguageProfile(
        name="python",
        function_patterns=[r"def ([a-zA-Z_]\w+)\("],
        class_patterns=[r"class ([A-Z]\w+)"],
        comment_prefix="#",
        assertion_scaffold=(
            "assert actual is not None  # auto-scaffolded: verify non-null result"
        ),
        fixture_scaffold=(
            "@pytest.fixture\n"
            "def test_subject():\n"
            "    return {subject}()\n"
        ),
        http_client_scaffold='response = requests.get("{endpoint}")',
    ),
    "typescript": LanguageProfile(
        name="typescript",
        function_patterns=[
            r"function ([a-zA-Z_]\w+)",
            r"(?:const|let|var) ([a-zA-Z_]\w+)\s*=\s*(?:async\s*)?\(",
        ],
        class_patterns=[r"class ([A-Z]\w+)"],
        comment_prefix="//",
        assertion_scaffold="expect(actual).toBeDefined();  // auto-scaffolded",
        fixture_scaffold="const test_subject = new {Subject}();\n",
        http_client_scaffold='const res = await request(app).get("{endpoint}");',
    ),
    "javascript": LanguageProfile(
        name="javascript",
        function_patterns=[
            r"function ([a-zA-Z_]\w+)",
            r"(?:const|let|var) ([a-zA-Z_]\w+)\s*=\s*(?:async\s*)?\(",
        ],
        class_patterns=[r"class ([A-Z]\w+)"],
        comment_prefix="//",
        assertion_scaffold="expect(actual).toBeDefined();  // auto-scaffolded",
        fixture_scaffold="const test_subject = new {Subject}();\n",
        http_client_scaffold='const res = await request(app).get("{endpoint}");',
    ),
    "java": LanguageProfile(
        name="java",
        function_patterns=[
            r"(?:public|private|protected)\s+\w+\s+([a-zA-Z_]\w+)\s*\(",
        ],
        class_patterns=[r"class ([A-Z]\w+)"],
        comment_prefix="//",
        assertion_scaffold="assertNotNull(actual);  // auto-scaffolded",
        fixture_scaffold="private {Subject} testSubject = new {Subject}();\n",
        http_client_scaffold='.perform(get("{endpoint}"))',
    ),
    "go": LanguageProfile(
        name="go",
        function_patterns=[
            r"func ([A-Z][a-zA-Z_]\w+)\(",
            r"func Test([A-Z]\w+)",
        ],
        class_patterns=[],
        comment_prefix="//",
        assertion_scaffold=(
            'if actual == nil { t.Fatal("expected non-nil result") }  // auto-scaffolded'
        ),
        fixture_scaffold="var testSubject = &{Subject}{}\n",
        http_client_scaffold=(
            'resp, err := http.Get("http://localhost:8080{endpoint}")'
        ),
    ),
}

_DEFAULT_PROFILE = _PROFILES["python"]

# Patterns that indicate un-filled TODO content
_TODO_PATTERNS = [
    r"subject_under_test",
    r"SubjectUnderTest",
    r"\bsut\b",
    r"your_function",
    r"methodUnderTest",
    r"functionUnderTest",
    r"/TODO/your-endpoint",
    r"YOUR_ENDPOINT",
    r"#\s*TODO[:\s]",
    r"//\s*TODO[:\s]",
    r"#\s*TODO$",
]
_TODO_RE = re.compile("|".join(_TODO_PATTERNS))


# ─── SymbolFiller ─────────────────────────────────────────────────────────────

class SymbolFiller:
    """
    Replace TODO placeholders in generated test content with real scaffold code.

    Usage::

        filler = SymbolFiller()
        filled, changes = filler.fill(content, source_code, language, test_type, requirements)
    """

    # ── public API ────────────────────────────────────────────────────────────

    def needs_filling(self, content: str) -> bool:
        """Return True if *content* contains any recognised TODO placeholder."""
        return bool(_TODO_RE.search(content))

    def fill(
        self,
        content: str,
        source_code: str,
        language: str,
        test_type: str,
        requirements: str,
    ) -> tuple[str, list[str]]:
        """
        Replace TODO placeholders in *content*.

        Returns ``(filled_content, list_of_changes_made)``.
        The method is **idempotent**: calling it twice on the same input
        produces the same output as calling it once.
        """
        if not content:
            return content, []

        profile = _PROFILES.get(language.lower(), _DEFAULT_PROFILE)
        subject, func_name = self._extract_symbols(source_code, profile)
        endpoint = self._extract_endpoint(requirements, test_type)

        result, changes = content, []

        for step in (
            self._fill_subject,
            self._fill_function,
            self._fill_endpoint,
            self._fill_assertions,
            self._fill_fixtures,
            self._fill_http_client,
        ):
            result, c = step(
                result,
                subject=subject,
                func_name=func_name,
                endpoint=endpoint,
                profile=profile,
                test_type=test_type,
            )
            changes.extend(c)

        # Ensure auto-fill comments are always followed by a newline before
        # any non-whitespace content (prevents merged lines after substitution).
        result = re.sub(r'(# auto-filled:[^\n]*)(\S)', r'\1\n\2', result)

        return result, changes

    # ── symbol / endpoint extraction ─────────────────────────────────────────

    def _extract_symbols(
        self, source_code: str, profile: LanguageProfile
    ) -> tuple[str, str]:
        """Return (subject_name, function_name) from source_code."""
        if not source_code:
            return "UnknownSubject", "unknown_function"

        classes: list[str] = []
        for pat in profile.class_patterns:
            classes.extend(re.findall(pat, source_code))

        functions: list[str] = []
        for pat in profile.function_patterns:
            functions.extend(re.findall(pat, source_code))

        # Subject: prefer class name; fall back to first function
        subject = classes[0] if classes else (functions[0] if functions else "UnknownSubject")
        func_name = functions[0] if functions else "unknown_function"
        return subject, func_name

    def _extract_endpoint(self, requirements: str, test_type: str) -> str:
        """Extract a URL path from requirements text; fall back to /api/v1/resource."""
        if not requirements:
            return "/api/v1/resource"

        # HTTP method + explicit path  e.g. "POST /api/users"
        m = re.search(
            r"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s,;.\"']+)",
            requirements,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)

        # Bare /api/… path
        m = re.search(r"(/api/[^\s,;.\"']+)", requirements)
        if m:
            return m.group(1)

        return "/api/v1/resource"

    # ── individual fill steps ─────────────────────────────────────────────────

    def _fill_subject(self, content, *, subject, profile, **_kw):
        """Replace subject_under_test / SubjectUnderTest / sut TODO patterns."""
        changes: list[str] = []
        cmt = profile.comment_prefix
        tag = f"  {cmt} auto-filled: subject={subject}"

        # subject_under_test() call with optional trailing comment
        p = re.compile(r"subject_under_test\s*\(\s*\)\s*(?:#[^\n]*)?")
        if p.search(content):
            content = p.sub(f"{subject}(){tag}", content)
            changes.append(f"subject_under_test() → {subject}()")

        # bare subject_under_test identifier (not followed by open paren)
        p = re.compile(r"\bsubject_under_test\b(?!\s*\()")
        if p.search(content):
            content = p.sub(subject, content)
            changes.append(f"subject_under_test → {subject}")

        # new SubjectUnderTest() — optional ; and optional comment
        p = re.compile(r"new\s+SubjectUnderTest\s*\(\s*\)\s*;?\s*(?://[^\n]*)?")
        if p.search(content):
            content = p.sub(f"new {subject}(){tag}", content)
            changes.append(f"new SubjectUnderTest() → new {subject}()")

        # bare SubjectUnderTest identifier
        p = re.compile(r"\bSubjectUnderTest\b")
        if p.search(content):
            content = p.sub(subject, content)
            changes.append(f"SubjectUnderTest → {subject}")

        # sut = SomeClass()  // TODO: ... (only when a TODO comment is present)
        p = re.compile(
            r"(?<![a-zA-Z_])sut(?![a-zA-Z_0-9])\s*=\s*\w+\(\s*\)\s*;?\s*"
            r"//\s*TODO[^\n]*"
        )
        if p.search(content):
            content = p.sub(f"sut = {subject}(){tag}", content)
            changes.append(f"sut = ...() TODO → sut = {subject}()")

        return content, changes

    def _fill_function(self, content, *, func_name, profile, **_kw):
        """Replace your_function / methodUnderTest / functionUnderTest patterns."""
        changes: list[str] = []
        cmt = profile.comment_prefix
        tag = f"  {cmt} auto-filled: fn={func_name}"

        # receiver.your_function() with optional trailing comment
        p = re.compile(
            r"(subject|sut|obj|instance|service|controller|handler)\s*\.\s*"
            r"your_function\s*\(\s*\)\s*(?:#[^\n]*)?"
        )
        if p.search(content):
            content = p.sub(lambda m: f"{m.group(1)}.{func_name}(){tag}", content)
            changes.append(f".your_function() → .{func_name}()")

        # bare your_function
        p = re.compile(r"\byour_function\b")
        if p.search(content):
            content = p.sub(func_name, content)
            changes.append(f"your_function → {func_name}")

        # receiver.methodUnderTest() / receiver.functionUnderTest()
        for placeholder in ("methodUnderTest", "functionUnderTest"):
            # method call with optional ; and optional comment
            p = re.compile(
                rf"([\w.]+)\s*\.\s*{placeholder}\s*\(\s*\)\s*;?\s*(?://[^\n]*)?"
            )
            if p.search(content):
                content = p.sub(
                    lambda m, fn=func_name, t=tag: f"{m.group(1)}.{fn}(){t}",
                    content,
                )
                changes.append(f".{placeholder}() → .{func_name}()")
                continue  # skip bare replacement if method form already handled

            p_bare = re.compile(rf"\b{placeholder}\b")
            if p_bare.search(content):
                content = p_bare.sub(func_name, content)
                changes.append(f"{placeholder} → {func_name}")

        return content, changes

    def _fill_endpoint(self, content, *, endpoint, **_kw):
        """Replace /TODO/your-endpoint and YOUR_ENDPOINT placeholders."""
        changes: list[str] = []

        p = re.compile(r'"/TODO/your-endpoint"')
        if p.search(content):
            content = p.sub(f'"{endpoint}"', content)
            changes.append(f"/TODO/your-endpoint → {endpoint}")

        p = re.compile(r'"YOUR_ENDPOINT"')
        if p.search(content):
            content = p.sub(f'"{endpoint}"', content)
            changes.append(f'"YOUR_ENDPOINT" → "{endpoint}"')

        p = re.compile(r'\bYOUR_ENDPOINT\b')
        if p.search(content):
            content = p.sub(endpoint, content)
            changes.append(f"YOUR_ENDPOINT (bare) → {endpoint}")

        return content, changes

    def _fill_assertions(self, content, *, profile, **_kw):
        """Replace TODO assertion placeholders with language-appropriate scaffold."""
        changes: list[str] = []
        cmt = profile.comment_prefix

        # Standalone  "# TODO: fill assertion"  line
        p = re.compile(
            rf"^(\s*){re.escape(cmt)}\s*TODO[:\s]+fill\s+assertion\s*$",
            re.MULTILINE | re.IGNORECASE,
        )
        if p.search(content):
            content = p.sub(
                lambda m: f"{m.group(1)}{profile.assertion_scaffold}",
                content,
            )
            changes.append("# TODO: fill assertion → assertion scaffold")

        # assert actual == expected  # TODO … (exact variable names)
        p = re.compile(
            r"assert\s+actual\s*==\s*expected\s*(?:#\s*TODO[^\n]*)?",
        )
        if p.search(content):
            content = p.sub(profile.assertion_scaffold, content)
            changes.append("assert actual == expected TODO → assertion scaffold")

        # Any  assert x == y  # TODO …  line (catches result/expected variants)
        p = re.compile(
            rf"^(\s*)assert\s+\w+\s*==\s*\w+\s*{re.escape(cmt)}\s*TODO[^\n]*$",
            re.MULTILINE | re.IGNORECASE,
        )
        if p.search(content):
            content = p.sub(
                lambda m: f"{m.group(1)}{profile.assertion_scaffold}",
                content,
            )
            changes.append("assert x == y # TODO → assertion scaffold")

        # expect(...).toBeDefined();  // TODO: fill assertion  (TypeScript / JS)
        p = re.compile(
            r"expect\s*\([^)]+\)\s*\.\s*toBeDefined\s*\(\s*\)\s*;?\s*"
            r"(?://\s*TODO[^\n]*)"
        )
        if p.search(content):
            content = p.sub(profile.assertion_scaffold, content)
            changes.append("expect().toBeDefined() TODO → assertion scaffold")

        return content, changes

    def _fill_fixtures(self, content, *, subject, profile, **_kw):
        """Replace # TODO: add fixture with a language-appropriate fixture scaffold."""
        changes: list[str] = []
        cmt = profile.comment_prefix

        p = re.compile(
            rf"^(\s*){re.escape(cmt)}\s*TODO[:\s]+add\s+fixture\s*$",
            re.MULTILINE | re.IGNORECASE,
        )
        if p.search(content):
            Subject = subject[0].upper() + subject[1:] if subject else "UnknownSubject"
            scaffold = profile.fixture_scaffold.format(subject=subject, Subject=Subject)
            content = p.sub(lambda m: f"{m.group(1)}{scaffold}", content)
            changes.append(f"# TODO: add fixture → {subject} fixture scaffold")

        return content, changes

    def _fill_http_client(self, content, *, endpoint, profile, test_type, **_kw):
        """Fill # TODO: add http client — only for api / integration test types."""
        if test_type not in ("api", "integration"):
            return content, []

        changes: list[str] = []
        scaffold = profile.http_client_scaffold.format(endpoint=endpoint)
        cmt = profile.comment_prefix

        p = re.compile(
            rf"^(\s*){re.escape(cmt)}\s*TODO[:\s]+add\s+http\s+client[^\n]*$",
            re.MULTILINE | re.IGNORECASE,
        )
        if p.search(content):
            content = p.sub(lambda m: f"{m.group(1)}{scaffold}", content)
            changes.append(f"# TODO: add http client → {endpoint}")

        return content, changes
