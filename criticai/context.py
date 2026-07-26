"""Codebase context gathering for richer reviews.

Analyzes the diff to identify files that the changed code references
(imports, calls, type definitions), fetches their contents from the repo,
and formats them as additional context for the model. This lets CriticAI
catch cross-file issues like broken contracts, deprecated API usage, and
type mismatches — something diff-only reviewers miss entirely.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from criticai.github import GitHubClient

# Maximum number of context files to fetch (to avoid token explosion)
MAX_CONTEXT_FILES = 8

# Maximum size per file (characters) to include as context
MAX_FILE_SIZE = 8000

# Common import patterns across languages
_IMPORT_PATTERNS = [
    # JavaScript/TypeScript: import ... from './path' or '../path'
    re.compile(r"""(?:import|export)\s+.*?from\s+['"](\.[^'"]+)['"]"""),
    # JavaScript/TypeScript: require('./path')
    re.compile(r"""require\s*\(\s*['"](\.[^'"]+)['"]\s*\)"""),
    # Python: from .module import ... or from package.module import ...
    re.compile(r"""from\s+(\.[\w.]+)\s+import"""),
    # Python: import module
    re.compile(r"""^import\s+([\w.]+)""", re.MULTILINE),
    # Go: import "package/path"
    re.compile(r"""import\s+(?:\w+\s+)?["']([^"']+)["']"""),
]

# File extensions we can meaningfully provide as context
_CONTEXTABLE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java",
    ".kt", ".swift", ".rb", ".cs", ".cpp", ".c", ".h", ".hpp",
    ".yaml", ".yml", ".json", ".toml", ".graphql", ".proto",
}


def gather_context(
    diff: str,
    changed_files: list[str],
    github: "GitHubClient",
    head_sha: str | None,
) -> str:
    """Gather relevant file contents from the repo as context for the review.

    Strategy:
    1. Parse the diff for import/require/from statements pointing to
       relative paths within the repo
    2. Resolve those paths relative to the changed files
    3. Fetch each referenced file (skipping ones that are already in the diff)
    4. Format as a context block to prepend to the model input

    Returns a formatted context string, or empty string if no context found.
    """
    # Extract referenced paths from the diff content
    referenced_paths = _extract_references(diff, changed_files)

    # Remove files that are already in the diff (model already sees them)
    referenced_paths = [p for p in referenced_paths if p not in set(changed_files)]

    # Deduplicate and limit
    seen: set[str] = set()
    unique_paths: list[str] = []
    for p in referenced_paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)
    unique_paths = unique_paths[:MAX_CONTEXT_FILES]

    if not unique_paths:
        return ""

    # Fetch file contents
    ref = head_sha if head_sha else None
    context_files: list[tuple[str, str]] = []

    for path in unique_paths:
        content = github.get_file_content(path, ref=ref)
        if content and len(content) <= MAX_FILE_SIZE:
            context_files.append((path, content))
        elif content and len(content) > MAX_FILE_SIZE:
            # Truncate large files to the first MAX_FILE_SIZE chars
            context_files.append((path, content[:MAX_FILE_SIZE] + "\n... (truncated)"))

    if not context_files:
        return ""

    # Format context block
    print(f"Context: fetched {len(context_files)} referenced file(s)")
    for path, _ in context_files:
        print(f"  - {path}")

    parts = ["REFERENCED FILES (for cross-file context — do NOT review these, "
             "only use them to understand how the changed code interacts with "
             "the rest of the codebase):\n"]

    for path, content in context_files:
        parts.append(f"--- {path} ---\n{content}\n")

    parts.append("--- END REFERENCED FILES ---\n")
    return "\n".join(parts)


def _extract_references(diff: str, changed_files: list[str]) -> list[str]:
    """Extract file paths referenced by import/require statements in the diff.

    Only looks at added lines (+) in the diff since those represent the
    code being introduced. Resolves relative paths based on the directory
    of the file being changed.
    """
    references: list[str] = []
    current_file: str | None = None

    for line in diff.splitlines():
        # Track which file we're in
        if line.startswith("diff --git"):
            match = re.search(r"diff --git a/(.*?) b/", line)
            if match:
                current_file = match.group(1)
            continue

        # Only look at added lines
        if not line.startswith("+") or line.startswith("+++"):
            continue

        line_content = line[1:]  # strip the leading +

        # Try each import pattern
        for pattern in _IMPORT_PATTERNS:
            for match in pattern.finditer(line_content):
                raw_path = match.group(1)
                resolved = _resolve_path(raw_path, current_file)
                if resolved:
                    references.append(resolved)

    return references


def _resolve_path(raw_path: str, from_file: str | None) -> str | None:
    """Resolve a relative import path to a repo-relative file path.

    Handles:
    - './foo' and '../foo' relative imports (JS/TS/Python)
    - Extension guessing for JS/TS (.ts, .tsx, .js, /index.ts)
    - Python dotted paths (converted to slash paths)
    """
    if from_file is None:
        return None

    # Python dotted imports starting with '.'
    if raw_path.startswith(".") and "/" not in raw_path and "\\" not in raw_path:
        # Could be Python relative import like '.models' or '..utils'
        # Count leading dots
        dots = len(raw_path) - len(raw_path.lstrip("."))
        module_part = raw_path[dots:]
        if not module_part:
            return None
        # Go up `dots - 1` directories from the current file
        dir_path = os.path.dirname(from_file)
        for _ in range(dots - 1):
            dir_path = os.path.dirname(dir_path)
        # Convert module dots to path separators
        file_path = module_part.replace(".", "/")
        resolved = os.path.join(dir_path, file_path).replace("\\", "/")
        # Try with .py extension
        return resolved + ".py"

    # JS/TS relative imports starting with ./ or ../
    if raw_path.startswith("./") or raw_path.startswith("../"):
        dir_path = os.path.dirname(from_file)
        resolved = os.path.normpath(os.path.join(dir_path, raw_path)).replace("\\", "/")

        # If it already has an extension, use it
        _, ext = os.path.splitext(resolved)
        if ext in _CONTEXTABLE_EXTENSIONS:
            return resolved

        # Try common extensions for JS/TS imports
        for try_ext in (".ts", ".tsx", ".js", ".jsx"):
            candidate = resolved + try_ext
            # We can't check existence here (would need an API call per guess)
            # so use the extension of the importing file as a heuristic
            from_ext = os.path.splitext(from_file)[1]
            if from_ext in (".ts", ".tsx"):
                return resolved + ".ts"  # prefer .ts for TS projects
            elif from_ext in (".js", ".jsx"):
                return resolved + ".js"
            else:
                return resolved + try_ext  # first guess

        return resolved

    # Absolute/package imports — skip (can't resolve without node_modules etc.)
    return None
