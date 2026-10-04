"""
The ground-truth check. Runs git's own three-way merge simulation between
two branches and reports whether merging them right now would conflict.
Nothing here is a guess -- git does the actual merge, in memory, and we
just read the result.
"""

import subprocess
from dataclasses import dataclass, field
from typing import List

from .poller import ActiveBranch


@dataclass
class ConflictResult:
    has_conflict: bool
    conflicting_files: List[str] = field(default_factory=list)


def check_merge_conflict(
    repo_path: str, branch_a: ActiveBranch, branch_b: ActiveBranch
) -> ConflictResult:
    result = subprocess.run(
        ["git", "merge-tree", "--write-tree", branch_a.branch_name, branch_b.branch_name],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    conflicting_files = [
        line.split(" in ", 1)[1].strip()
        for line in result.stdout.splitlines()
        if line.startswith("CONFLICT") and " in " in line
    ]

    return ConflictResult(
        has_conflict=len(conflicting_files) > 0,
        conflicting_files=conflicting_files,
    )
