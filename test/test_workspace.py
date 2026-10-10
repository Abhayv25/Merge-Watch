"""
Regression tests for the fresh-clone bug: in GitHub Actions (and Lambda) a
PR's branch is never a local branch, so checks by branch name failed and the
failure was read as "no conflict".
"""

import subprocess

from src.checker import run_check
from src.state import FileStateStore
from src.workspace import BASE_REF, ensure_repository, sync_refs


def test_conflict_is_found_in_a_fresh_repository(tmp_path, github_like_remote):
    remote, branches = github_like_remote
    local = str(tmp_path / "work.git")
    ensure_repository(local)

    base_ref, synced = sync_refs(local, remote, "", "main", branches)

    sent = []
    summary = run_check(
        local, base_ref, synced, FileStateStore(str(tmp_path / "state.json")), notify=sent.append
    )
    assert summary.conflicts_found == 1
    assert summary.errors == 0
    assert len(sent) == 1 and "src/auth.js" in sent[0]


def test_sync_uses_the_commit_actually_fetched(tmp_path, github_like_remote):
    remote, branches = github_like_remote
    # A push lands on PR 1 after the API call reported its head SHA.
    new_head = subprocess.run(
        ["git", "commit-tree", "-p", branches[0].head_sha, "-m", "late push",
         f"{branches[0].head_sha}^{{tree}}"],
        cwd=remote, capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(["git", "update-ref", "refs/pull/1/head", new_head], cwd=remote, check=True)

    local = str(tmp_path / "work.git")
    ensure_repository(local)
    _, synced = sync_refs(local, remote, "", "main", branches)
    assert synced[0].head_sha == new_head


def test_sync_removes_refs_for_closed_pull_requests(tmp_path, github_like_remote):
    remote, branches = github_like_remote
    local = str(tmp_path / "work.git")
    ensure_repository(local)
    sync_refs(local, remote, "", "main", branches)
    sync_refs(local, remote, "", "main", branches[:1])  # PRs 2 and 3 closed

    refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/mergewatch/pr/"],
        cwd=local, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert refs == ["refs/mergewatch/pr/1"]


def test_base_ref_points_at_base_branch(tmp_path, github_like_remote):
    remote, branches = github_like_remote
    local = str(tmp_path / "work.git")
    ensure_repository(local)
    base_ref, _ = sync_refs(local, remote, "", "main", branches)
    assert base_ref == BASE_REF
