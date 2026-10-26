from __future__ import annotations

import builtins

from code_review_agent.config import Limits
from code_review_agent.context import build_review_context
from code_review_agent.models import ChangedFile, PullRequestMetadata, PullRequestSnapshot
from code_review_agent.static_analysis import run_static_checks


def make_context(content: str | None, path: str = "src/example.py"):
    metadata = PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url="https://github.com/acme/widgets/pull/7",
        title="Static checks",
        author="octocat",
        base_branch="main",
        head_branch="checks",
        head_sha="a" * 40,
    )
    file = ChangedFile(
        path=path,
        status="modified",
        additions=1,
        deletions=0,
        changes=1,
        patch="@@ -0,0 +1 @@\n+value = eval(user_input)",
        content=content,
    )
    return build_review_context(
        PullRequestSnapshot(metadata=metadata, files=(file,)),
        Limits(max_total_context_chars=10_000),
    )


def test_static_checks_inspect_ast_without_executing_repository_code(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("repository code must not execute")

    monkeypatch.setattr(builtins, "exec", forbidden)
    context = make_context("result = eval(user_input)\n")

    result = run_static_checks(context)

    assert result.available is True
    assert [(signal.rule, signal.path, signal.line) for signal in result.signals] == [
        ("dangerous-eval", "src/example.py", 1)
    ]
    assert any(tool.name == "python-ast" and tool.available for tool in result.tools)
    assert any(tool.name == "external-scanners" and not tool.available for tool in result.tools)


def test_static_checks_disclose_absence_when_no_parseable_python_is_available() -> None:
    result = run_static_checks(make_context(None, path="assets/logo.bin"))

    assert result.available is False
    assert result.signals == ()
    assert "No parseable Python file content" in result.summary


def test_syntax_error_is_reported_as_unavailable_not_fabricated_signal() -> None:
    result = run_static_checks(make_context("def broken(:\n"))

    assert result.available is False
    assert result.signals == ()
    assert any(tool.name == "python-ast" and "parse" in tool.detail for tool in result.tools)
