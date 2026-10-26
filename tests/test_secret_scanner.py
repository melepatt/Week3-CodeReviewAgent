from __future__ import annotations

from pathlib import Path

from code_review_agent import secret_scanner
from code_review_agent.secret_scanner import scan_files, tracked_files


def test_scanner_flags_likely_real_credentials(tmp_path: Path) -> None:
    leaked = tmp_path / "leak.txt"
    leaked.write_text("token=ghp_" + "abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")

    findings = scan_files((leaked,))

    assert len(findings) == 1
    assert findings[0].path == str(leaked)
    assert findings[0].line == 1
    assert findings[0].kind == "github-token"


def test_scanner_allows_documented_placeholders(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text(
        "LLM_API_KEY=replace-with-local-secret\nGITHUB_WRITE_TOKEN=placeholder-token\n",
        encoding="utf-8",
    )

    assert scan_files((example,)) == ()


def test_scanner_never_includes_secret_value_in_finding(tmp_path: Path) -> None:
    secret = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    leaked = tmp_path / "leak.txt"
    leaked.write_text(secret, encoding="utf-8")

    finding = scan_files((leaked,))[0]

    assert secret not in repr(finding)


def test_scanner_honors_explicit_fixture_allowlist_marker(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.py"
    fixture.write_text(
        "token = 'ghp_abcdefghijklmnopqrstuvwxyz123456'  # pragma: allowlist secret\n",
        encoding="utf-8",
    )

    assert scan_files((fixture,)) == ()


def test_scanner_skips_unreadable_or_binary_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"\xff\xfe\xfd")

    assert scan_files((missing, binary)) == ()


def test_tracked_files_resolves_relative_and_absolute_paths(tmp_path: Path, monkeypatch) -> None:
    relative = tmp_path / "relative.txt"
    absolute = tmp_path / "absolute.txt"
    relative.write_text("safe", encoding="utf-8")
    absolute.write_text("safe", encoding="utf-8")

    class Result:
        stdout = f"relative.txt\n{absolute}\nmissing.txt\n"

    monkeypatch.setattr(secret_scanner.subprocess, "run", lambda *args, **kwargs: Result())

    assert tracked_files(tmp_path) == (relative, absolute)


def test_scanner_main_reports_findings_and_exit_status(tmp_path: Path, monkeypatch, capsys) -> None:
    leaked = tmp_path / "leak.txt"
    leaked.write_text("token=ghp_" + "abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(secret_scanner, "tracked_files", lambda root: (leaked,))

    assert secret_scanner.main() == 1
    output = capsys.readouterr().out
    assert "possible github-token" in output
    assert "1 finding(s)" in output
