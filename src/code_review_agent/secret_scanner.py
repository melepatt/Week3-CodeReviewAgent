"""Minimal tracked-file credential scanner with source-free findings."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SecretFinding:
    path: str
    line: int
    kind: str


_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai-token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
_PLACEHOLDERS = ("placeholder", "replace-with", "example", "dummy", "test-token")


def scan_files(paths: tuple[Path, ...]) -> tuple[SecretFinding, ...]:
    findings: list[SecretFinding] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            lowered = line.casefold()
            if "pragma: allowlist secret" in lowered:
                continue
            if any(marker in lowered for marker in _PLACEHOLDERS):
                continue
            for kind, pattern in _PATTERNS:
                if pattern.search(line):
                    findings.append(SecretFinding(path=str(path), line=line_number, kind=kind))
                    break
    return tuple(findings)


def tracked_files(root: Path) -> tuple[Path, ...]:
    command = [
        "git",
        "-C",
        str(root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        ".",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    paths: list[Path] = []
    for item in result.stdout.splitlines():
        candidate = Path(item)
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.is_file():
            paths.append(candidate)
    return tuple(paths)


def main() -> int:
    root = Path.cwd()
    findings = scan_files(tracked_files(root))
    for finding in findings:
        print(f"{finding.path}:{finding.line}: possible {finding.kind}")
    print(f"Scanned tracked/project files: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
