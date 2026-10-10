"""
The ground-truth check. Runs git's own three-way merge simulation between
two branches and reports whether merging them right now would conflict.
Nothing here is a guess -- git does the actual merge, in memory, and we
just read the result.
"""

from dataclasses import dataclass, field
from typing import List

from .gitcmd import run_git
from .poller import ActiveBranch

# git merge-tree --write-tree exits 0 for a clean merge and 1 for a merge
# with conflicts. Anything else is a real error (bad ref, missing objects).
_CLEAN = 0
_CONFLICTED = 1


@dataclass
class ConflictResult:
    has_conflict: bool
    conflicting_files: List[str] = field(default_factory=list)


def check_merge_conflict(
    repo_path: str, branch_a: ActiveBranch, branch_b: ActiveBranch
) -> ConflictResult:
    # Compare commit SHAs, not branch names: in a fresh clone (GitHub Actions,
    # Lambda) a PR's branch only exists as origin/<name> or a fetched pull
    # ref, never as a local branch, and PRs from forks have no branch in this
    # repository at all. Branch names here made every check fail silently.
    #
    # merge-tree exits 1 both for "conflict" and for "no such commit", so
    # confirm both commits exist first; otherwise a bad ref reads as a conflict.
    for sha in (branch_a.head_sha, branch_b.head_sha):
        run_git(repo_path, ["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"])

    result = run_git(
        repo_path,
        ["merge-tree", "--write-tree", "--name-only", branch_a.head_sha, branch_b.head_sha],
        ok_codes=(_CLEAN, _CONFLICTED),
    )

    if result.returncode == _CLEAN:
        return ConflictResult(has_conflict=False)

    # Output: the merged tree's OID, then one conflicted path per line, then
    # a blank line, then informational messages.
    conflicting_files = []
    for line in result.stdout.splitlines()[1:]:
        if not line.strip():
            break
        conflicting_files.append(line.strip())

    return ConflictResult(
        has_conflict=True,
        conflicting_files=sorted(set(conflicting_files)),
    )
