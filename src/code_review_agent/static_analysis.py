"""Non-executing, optional static inspection of supplied Python text."""

from __future__ import annotations

import ast

from code_review_agent.models import (
    ReviewContext,
    StaticAnalysisResult,
    StaticSignal,
    StaticToolStatus,
)


class _SafetyVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.signals: list[StaticSignal] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            self.signals.append(
                StaticSignal(
                    rule=f"dangerous-{node.func.id}",
                    path=self.path,
                    line=node.lineno,
                    message=f"Direct {node.func.id} call found by Python AST inspection",
                )
            )
        self.generic_visit(node)


def run_static_checks(context: ReviewContext) -> StaticAnalysisResult:
    """Parse Python source as data; never import, execute, or shell out to repository code."""

    signals: list[StaticSignal] = []
    parsed = 0
    parse_errors = 0
    for file in context.files:
        if not file.path.endswith(".py") or not file.content:
            continue
        try:
            tree = ast.parse(file.content, filename=file.path)
        except SyntaxError:
            parse_errors += 1
            continue
        parsed += 1
        visitor = _SafetyVisitor(file.path)
        visitor.visit(tree)
        signals.extend(visitor.signals)

    if parsed:
        ast_status = StaticToolStatus(
            name="python-ast",
            available=True,
            detail=f"Parsed {parsed} Python file(s) without executing them",
        )
        summary = f"Python AST inspection produced {len(signals)} signal(s)."
    elif parse_errors:
        ast_status = StaticToolStatus(
            name="python-ast",
            available=False,
            detail=f"Unable to parse {parse_errors} supplied Python file(s)",
        )
        summary = "No parseable Python file content was available for static inspection."
    else:
        ast_status = StaticToolStatus(
            name="python-ast",
            available=False,
            detail="No supplied Python file content",
        )
        summary = "No parseable Python file content was available for static inspection."

    external_status = StaticToolStatus(
        name="external-scanners",
        available=False,
        detail="External repository scanners were not run; repository code is never executed",
    )
    return StaticAnalysisResult(
        available=bool(parsed),
        tools=(ast_status, external_status),
        signals=tuple(sorted(signals, key=lambda item: (item.path, item.line, item.rule))),
        summary=summary,
    )
