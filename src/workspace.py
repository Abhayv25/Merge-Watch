"""
Brings a local git repository up to date with the commits Mergewatch needs:
the base branch and the head commit of every open pull request.

PR heads are fetched from GitHub's refs/pull/<number>/head refs, which exist
for every pull request -- including PRs opened from forks, whose branches do
not exist in the monitored repository at all. Everything lands under
refs/mergewatch/ so it never collides with the user's own branches.
"""

import base64
import os
from dataclasses import replace
from typing import List, Tuple

from .gitcmd import run_git
from .poller import ActiveBranch

BASE_REF = "refs/mergewatch/base"
_PR_REF_PREFIX = "refs/mergewatch/pr/"


def github_clone_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}.git"


def _auth_config(token: str) -> List[str]:
    # The token goes in a per-command header, never in the remote URL, so it
    # is not written to .git/config or shown in error messages.
    if not token:
        return []
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return [f"http.extraHeader=Authorization: Basic {credentials}"]


def ensure_repository(repo_path: str) -> None:
    """Creates a bare repository at repo_path if one does not exist yet."""
    if os.path.isdir(os.path.join(repo_path, "objects")) or os.path.isdir(
        os.path.join(repo_path, ".git")
    ):
        return
    os.makedirs(repo_path, exist_ok=True)
    run_git(repo_path, ["init", "--quiet", "--bare"])


def sync_refs(
    repo_path: str,
    remote_url: str,
    token: str,
    base_branch: str,
    branches: List[ActiveBranch],
) -> Tuple[str, List[ActiveBranch]]:
    """
    Fetches the base branch and every PR head into repo_path. Returns the ref
    to diff against and the branches with head_sha set to the commit that was
    actually fetched (a PR can receive a push between the API call and the
    fetch; the fetched commit is the one we can analyze).
    """
    # Drop refs for PRs that have since closed.
    stale = run_git(repo_path, ["for-each-ref", "--format=%(refname)", _PR_REF_PREFIX])
    for ref in stale.stdout.split():
        run_git(repo_path, ["update-ref", "-d", ref])

    refspecs = [f"+refs/heads/{base_branch}:{BASE_REF}"]
    refspecs += [f"+refs/pull/{b.pr_number}/head:{_PR_REF_PREFIX}{b.pr_number}" for b in branches]

    run_git(
        repo_path,
        ["fetch", "--quiet", "--no-tags", remote_url, *refspecs],
        extra_config=_auth_config(token),
    )

    synced = []
    for branch in branches:
        fetched = run_git(repo_path, ["rev-parse", f"{_PR_REF_PREFIX}{branch.pr_number}"])
        synced.append(replace(branch, head_sha=fetched.stdout.strip()))
    return BASE_REF, synced
