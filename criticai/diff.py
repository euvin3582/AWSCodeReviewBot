"""Diff parsing and filtering.

Handles extracting file lists from unified diffs and filtering to only
include files under the configured home directory prefix.
"""

from __future__ import annotations

import re


def filter_diff(diff: str, home_directory: str) -> str:
    """Filter a unified diff to only include files under home_directory.

    If home_directory is empty, all files pass through unfiltered.
    Returns the filtered diff as a string.
    """
    changed_files = set(re.findall(r"diff --git a/(.*?) b/", diff))
    print("changed_files:")
    for file in sorted(changed_files):
        print(f"  - {file}")

    filtered_files = [
        f for f in changed_files if f.startswith(home_directory)
    ]

    print("Filtered changed files:")
    for file in sorted(filtered_files):
        print(f"  - {file}")

    # Rebuild diff including only hunks for filtered files
    filtered_lines: list[str] = []
    current_file: str | None = None

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            match = re.search(r"diff --git a/(.*?) b/", line)
            if match:
                current_file = match.group(1)

        if current_file in filtered_files:
            filtered_lines.append(line)

    return "\n".join(filtered_lines)


def extract_changed_files(diff: str) -> list[str]:
    """Extract the list of changed file paths from a unified diff."""
    return sorted(set(re.findall(r"diff --git a/(.*?) b/", diff)))
