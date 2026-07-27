"""Multi-language static analysis integration.

Runs available linters on changed files and converts their output into
InlineFinding objects that merge seamlessly with AI-generated findings.

Supported linters (auto-detected by file extension when available in PATH):
  - ruff        (Python)
  - eslint      (JavaScript / TypeScript)
  - shellcheck  (Shell scripts)
  - golangci-lint (Go)
  - rubocop     (Ruby)
  - clippy      (Rust via cargo)

Each linter is only invoked if:
  1. The tool binary is found in PATH (shutil.which)
  2. At least one changed file matches the linter's file extensions
  3. The linter is enabled by the 'linters' config ('auto' or explicitly listed)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from criticai.inline import InlineFinding


# ---------------------------------------------------------------------------
# Linter registry
# ---------------------------------------------------------------------------

@dataclass
class LinterDef:
    """Definition of a supported linter."""
    name: str
    extensions: tuple[str, ...]
    binary: str  # what to look for in PATH
    build_command: Callable[[list[str]], list[str]]
    parse_output: Callable[[str, list[str]], list["LinterResult"]]


@dataclass
class LinterResult:
    """Raw finding from a linter before conversion to InlineFinding."""
    path: str
    line: int
    col: int
    code: str       # rule ID, e.g. "E501", "no-unused-vars"
    message: str
    severity_raw: str  # "error", "warning", "info", "convention", etc.


# ---------------------------------------------------------------------------
# Severity mapping
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, str] = {
    "error": "🟠 Major",
    "fatal": "🟠 Major",
    "e": "🟠 Major",
    "warning": "🟡 Minor",
    "w": "🟡 Minor",
    "info": "🔵 Nit",
    "information": "🔵 Nit",
    "style": "🔵 Nit",
    "convention": "🔵 Nit",
    "refactor": "🔵 Nit",
    "c": "🔵 Nit",
    "r": "🔵 Nit",
    "n": "🔵 Nit",
}


def _map_severity(raw: str) -> str:
    """Map a linter's severity string to our emoji-tagged severity."""
    return _SEVERITY_MAP.get(raw.lower().strip(), "🟡 Minor")


# ---------------------------------------------------------------------------
# Ruff (Python)
# ---------------------------------------------------------------------------

def _ruff_command(files: list[str]) -> list[str]:
    return ["ruff", "check", "--output-format=json", "--no-fix", *files]


def _ruff_parse(output: str, files: list[str]) -> list[LinterResult]:
    results: list[LinterResult] = []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return results

    for item in data:
        path = item.get("filename", "")
        loc = item.get("location", {})
        results.append(LinterResult(
            path=path,
            line=loc.get("row", 0),
            col=loc.get("column", 0),
            code=item.get("code", ""),
            message=item.get("message", ""),
            severity_raw="warning",  # ruff doesn't distinguish error/warning in JSON
        ))
    return results


# ---------------------------------------------------------------------------
# ESLint (JavaScript / TypeScript)
# ---------------------------------------------------------------------------

def _eslint_command(files: list[str]) -> list[str]:
    return ["eslint", "-f", "json", "--no-error-on-unmatched-pattern", *files]


def _eslint_parse(output: str, files: list[str]) -> list[LinterResult]:
    results: list[LinterResult] = []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return results

    for file_result in data:
        path = file_result.get("filePath", "")
        for msg in file_result.get("messages", []):
            sev_num = msg.get("severity", 1)
            severity_raw = "error" if sev_num == 2 else "warning"
            results.append(LinterResult(
                path=path,
                line=msg.get("line", 0),
                col=msg.get("column", 0),
                code=msg.get("ruleId", "") or "",
                message=msg.get("message", ""),
                severity_raw=severity_raw,
            ))
    return results


# ---------------------------------------------------------------------------
# ShellCheck (Shell scripts)
# ---------------------------------------------------------------------------

def _shellcheck_command(files: list[str]) -> list[str]:
    return ["shellcheck", "-f", "json", *files]


def _shellcheck_parse(output: str, files: list[str]) -> list[LinterResult]:
    results: list[LinterResult] = []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return results

    for item in data:
        level = item.get("level", "warning")
        results.append(LinterResult(
            path=item.get("file", ""),
            line=item.get("line", 0),
            col=item.get("column", 0),
            code=f"SC{item.get('code', '')}",
            message=item.get("message", ""),
            severity_raw=level,
        ))
    return results


# ---------------------------------------------------------------------------
# golangci-lint (Go)
# ---------------------------------------------------------------------------

def _golangci_command(files: list[str]) -> list[str]:
    # golangci-lint doesn't accept individual files well; run on packages
    # containing changed files instead. For simplicity we run on ./...
    # but only if Go files changed (caller already checked).
    return ["golangci-lint", "run", "--out-format=json", "--issues-exit-code=0", "./..."]


def _golangci_parse(output: str, files: list[str]) -> list[LinterResult]:
    results: list[LinterResult] = []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return results

    # Only keep issues in files that actually changed
    changed_set = set(files)
    for issue in data.get("Issues", []) or []:
        pos = issue.get("Pos", {})
        path = pos.get("Filename", "")
        if path not in changed_set:
            continue
        results.append(LinterResult(
            path=path,
            line=pos.get("Line", 0),
            col=pos.get("Column", 0),
            code=issue.get("FromLinter", ""),
            message=issue.get("Text", ""),
            severity_raw=issue.get("Severity", "warning"),
        ))
    return results


# ---------------------------------------------------------------------------
# RuboCop (Ruby)
# ---------------------------------------------------------------------------

def _rubocop_command(files: list[str]) -> list[str]:
    return ["rubocop", "-f", "json", "--force-exclusion", *files]


def _rubocop_parse(output: str, files: list[str]) -> list[LinterResult]:
    results: list[LinterResult] = []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return results

    for file_result in data.get("files", []):
        path = file_result.get("path", "")
        for offense in file_result.get("offenses", []):
            loc = offense.get("location", {})
            results.append(LinterResult(
                path=path,
                line=loc.get("start_line", 0),
                col=loc.get("start_column", 0),
                code=offense.get("cop_name", ""),
                message=offense.get("message", ""),
                severity_raw=offense.get("severity", "convention"),
            ))
    return results


# ---------------------------------------------------------------------------
# Clippy (Rust via cargo)
# ---------------------------------------------------------------------------

def _clippy_command(files: list[str]) -> list[str]:
    # Clippy runs on the whole crate; we filter results to changed files
    return ["cargo", "clippy", "--message-format=json", "--quiet"]


def _clippy_parse(output: str, files: list[str]) -> list[LinterResult]:
    results: list[LinterResult] = []
    changed_set = set(files)

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        if msg.get("reason") != "compiler-message":
            continue

        inner = msg.get("message", {})
        level = inner.get("level", "")
        if level not in ("error", "warning"):
            continue

        for span in inner.get("spans", []):
            if not span.get("is_primary"):
                continue
            path = span.get("file_name", "")
            if path not in changed_set:
                continue
            results.append(LinterResult(
                path=path,
                line=span.get("line_start", 0),
                col=span.get("column_start", 0),
                code=inner.get("code", {}).get("code", "") if inner.get("code") else "",
                message=inner.get("message", ""),
                severity_raw=level,
            ))
    return results


# ---------------------------------------------------------------------------
# Linter registry
# ---------------------------------------------------------------------------

LINTER_REGISTRY: list[LinterDef] = [
    LinterDef(
        name="ruff",
        extensions=(".py",),
        binary="ruff",
        build_command=_ruff_command,
        parse_output=_ruff_parse,
    ),
    LinterDef(
        name="eslint",
        extensions=(".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
        binary="eslint",
        build_command=_eslint_command,
        parse_output=_eslint_parse,
    ),
    LinterDef(
        name="shellcheck",
        extensions=(".sh", ".bash"),
        binary="shellcheck",
        build_command=_shellcheck_command,
        parse_output=_shellcheck_parse,
    ),
    LinterDef(
        name="golangci-lint",
        extensions=(".go",),
        binary="golangci-lint",
        build_command=_golangci_command,
        parse_output=_golangci_parse,
    ),
    LinterDef(
        name="rubocop",
        extensions=(".rb",),
        binary="rubocop",
        build_command=_rubocop_command,
        parse_output=_rubocop_parse,
    ),
    LinterDef(
        name="clippy",
        extensions=(".rs",),
        binary="cargo",  # clippy is a cargo subcommand
        build_command=_clippy_command,
        parse_output=_clippy_parse,
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_linters(
    changed_files: list[str],
    linters_config: str = "auto",
    workspace: Optional[str] = None,
) -> list[InlineFinding]:
    """Run applicable linters on changed files and return findings.

    Args:
        changed_files: List of file paths from the diff (relative to repo root).
        linters_config: 'auto', 'none', or comma-separated linter names.
        workspace: Working directory for subprocess calls (defaults to cwd).

    Returns:
        List of InlineFinding objects ready to merge with AI findings.
    """
    if linters_config.strip().lower() == "none":
        print("Linters: disabled (linters='none')")
        return []

    # Determine which linters to consider
    if linters_config.strip().lower() == "auto":
        candidates = LINTER_REGISTRY
    else:
        requested = {name.strip().lower() for name in linters_config.split(",")}
        candidates = [ld for ld in LINTER_REGISTRY if ld.name in requested]

    cwd = workspace or os.getcwd()
    all_findings: list[InlineFinding] = []

    for linter_def in candidates:
        # Check if the binary is available
        if not shutil.which(linter_def.binary):
            continue

        # Filter changed files to those matching this linter's extensions
        matching_files = [
            f for f in changed_files
            if any(f.endswith(ext) for ext in linter_def.extensions)
        ]
        if not matching_files:
            continue

        print(f"Linter [{linter_def.name}]: running on {len(matching_files)} file(s)...")

        # Build and execute the command
        cmd = linter_def.build_command(matching_files)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=120,
            )
            # Most linters exit non-zero when findings exist — that's expected
            output = result.stdout or ""
        except subprocess.TimeoutExpired:
            print(f"  Warning: {linter_def.name} timed out after 120s, skipping.")
            continue
        except FileNotFoundError:
            print(f"  Warning: {linter_def.name} binary vanished, skipping.")
            continue
        except Exception as e:
            print(f"  Warning: {linter_def.name} failed: {e}")
            continue

        # Parse results
        raw_results = linter_def.parse_output(output, matching_files)
        print(f"  Found {len(raw_results)} issue(s).")

        # Convert to InlineFinding objects
        for r in raw_results:
            # Normalize path: strip leading ./ or absolute workspace prefix
            path = r.path
            if path.startswith("./"):
                path = path[2:]
            elif workspace and path.startswith(workspace):
                path = path[len(workspace):].lstrip("/\\")

            all_findings.append(InlineFinding(
                path=path,
                line=r.line,
                severity=_map_severity(r.severity_raw),
                category="Lint",
                message=f"`{r.code}` {r.message}" if r.code else r.message,
                suggestion=None,
                confidence="high",
            ))

    if all_findings:
        print(f"Linters: {len(all_findings)} total finding(s) across all tools.")
    else:
        print("Linters: no findings (or no applicable linters found in PATH).")

    return all_findings


def deduplicate_findings(
    ai_findings: list[InlineFinding],
    linter_findings: list[InlineFinding],
) -> list[InlineFinding]:
    """Merge linter findings with AI findings, deduplicating by (path, line).

    If the AI already flagged the same file+line, the AI finding takes
    priority (it has richer context/explanation). Linter findings on lines
    not already flagged by the AI are appended.
    """
    ai_lines: set[tuple[str, int]] = {(f.path, f.line) for f in ai_findings}

    unique_linter = [
        f for f in linter_findings
        if (f.path, f.line) not in ai_lines
    ]

    deduped_count = len(linter_findings) - len(unique_linter)
    if deduped_count > 0:
        print(f"  Deduplication: {deduped_count} linter finding(s) already covered by AI.")

    return ai_findings + unique_linter
