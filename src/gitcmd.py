"""
Thin wrapper around the git CLI. Every git call in the project goes through
run_git so that a failing command raises instead of quietly returning empty
output -- an empty diff from a bad ref used to look exactly like "no
conflicts", which is the worst possible failure mode for this tool.
"""

import subprocess
from typing import Iterable, Optional, Sequence


class GitError(RuntimeError):
    pass


def run_git(
    repo_path: str,
    args: Sequence[str],
    ok_codes: Iterable[int] = (0,),
    extra_config: Optional[Sequence[str]] = None,
) -> subprocess.CompletedProcess:
    command = ["git"]
    for setting in extra_config or []:
        command += ["-c", setting]
    command += list(args)

    result = subprocess.run(command, cwd=repo_path, capture_output=True, text=True)
    if result.returncode not in tuple(ok_codes):
        raise GitError(
            f"`git {' '.join(args)}` failed with exit code {result.returncode}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result
