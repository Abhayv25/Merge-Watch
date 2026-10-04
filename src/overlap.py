"""
Cheap first-pass filter: finds which files are touched by more than one
active branch, so merge_check.py only has to run its real (more expensive)
simulation on pairs that could plausibly conflict.
"""

import subprocess
from dataclasses import dataclass
from typing import Dict, List

from .poller import ActiveBranch


@dataclass
class FileOverlap:
    file: str
    branches: List[ActiveBranch]


def get_changed_files(repo_path: str, base_branch: str, branch_name: str) -> List[str]:
    result = subprocess.run(
        ["git", "diff", f"{base_branch}...{branch_name}", "--name-only"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def find_overlapping_files(
    repo_path: str, base_branch: str, branches: List[ActiveBranch]
) -> List[FileOverlap]:
    touched_by: Dict[str, List[ActiveBranch]] = {}

    for branch in branches:
        for file in get_changed_files(repo_path, base_branch, branch.branch_name):
            touched_by.setdefault(file, []).append(branch)

    return [
        FileOverlap(file=file, branches=touchers)
        for file, touchers in touched_by.items()
        if len(touchers) >= 2
    ]
