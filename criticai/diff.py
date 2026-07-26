"""Diff parsing and filtering.

Handles extracting file lists from unified diffs, filtering to only
include files under the configured home directory prefix, and mapping
file line numbers to diff positions (needed for GitHub's inline review
comment API).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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


@dataclass
class DiffPosition:
    """Maps a file path + line number to the diff position GitHub expects."""
    path: str
    line: int       # the actual line number in the new file
    position: int   # the position in the diff (for GitHub API)


def build_position_map(diff: str) -> dict[str, dict[int, int]]:
    """Build a mapping of {filepath: {new_line_number: diff_position}}.

    GitHub's review comment API requires a `position` which is the number
    of lines from the first @@ hunk header in that file's diff section.
    This function parses the unified diff and builds a lookup table so we
    can go from (file, line_number) -> position.

    Only tracks lines on the RIGHT side of the diff (additions / context
    lines that exist in the new version), since that's where review
    comments should attach.
    """
    position_map: dict[str, dict[int, int]] = {}
    current_file: str | None = None
    position = 0  # position counter resets per file

    for line in diff.splitlines():
        # New file section
        if line.startswith("diff --git"):
            match = re.search(r"diff --git a/(.*?) b/", line)
            if match:
                current_file = match.group(1)
                position_map[current_file] = {}
                position = 0
            continue

        if current_file is None:
            continue

        # Hunk header — extract the starting line number for the new file
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk_match:
            position += 1
            new_line = int(hunk_match.group(1))
            # The hunk header itself occupies a position but isn't a code line
            continue

        # After the first hunk header, count positions
        if position == 0:
            # Still in file header (---, +++, etc.) — don't count
            continue

        position += 1

        if line.startswith("+"):
            # Added line — exists in the new file
            position_map[current_file][new_line] = position
            new_line += 1
        elif line.startswith("-"):
            # Removed line — doesn't exist in new file, skip line counter
            pass
        else:
            # Context line — exists in both old and new
            position_map[current_file][new_line] = position
            new_line += 1

    return position_map


def find_position(position_map: dict[str, dict[int, int]], path: str, line: int) -> int | None:
    """Look up the diff position for a given file path and line number.

    Returns the position integer, or None if the line isn't in the diff
    (meaning it wasn't changed/visible and can't have a review comment).
    """
    file_map = position_map.get(path)
    if not file_map:
        return None
    return file_map.get(line)
