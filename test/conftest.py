import os
import subprocess

import pytest

from src.poller import ActiveBranch

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
REPO_DIR = os.path.join(FIXTURES_DIR, "conflict-repo")
SETUP_SCRIPT = os.path.join(FIXTURES_DIR, "setup_fixture_repo.sh")

# Branches in the fixture repo, in the order their pull requests are "opened".
FIXTURE_BRANCHES = ["feature/oauth-login", "fix/session-timeout", "chore/add-comment"]


@pytest.fixture(scope="session", autouse=True)
def fixture_repo():
    # The fixture repo isn't committed to version control (a git repo
    # nested inside this one causes problems), so build it fresh if it's
    # not already there.
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        subprocess.run(["bash", SETUP_SCRIPT], check=True)


def sha_of(ref: str, repo: str = REPO_DIR) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def fixture_branch(name: str, pr_number: int = 1) -> ActiveBranch:
    """An ActiveBranch pointing at a real commit in the fixture repo."""
    return ActiveBranch(branch_name=name, author="test", pr_number=pr_number, head_sha=sha_of(name))


@pytest.fixture
def github_like_remote(tmp_path):
    """
    A bare copy of the fixture repo laid out like a GitHub repository: the
    base branch under refs/heads/ and each open PR under refs/pull/<n>/head.
    Returns (remote_path, [ActiveBranch, ...]) as the GitHub API would report.
    """
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "--quiet", "--bare", REPO_DIR, str(remote)], check=True)
    branches = []
    for number, name in enumerate(FIXTURE_BRANCHES, start=1):
        sha = sha_of(name)
        subprocess.run(
            ["git", "update-ref", f"refs/pull/{number}/head", sha], cwd=remote, check=True
        )
        branches.append(ActiveBranch(name, "dev", number, sha))
    return str(remote), branches
