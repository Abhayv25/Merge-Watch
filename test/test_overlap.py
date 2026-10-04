import os

from src.overlap import find_overlapping_files, get_changed_files
from src.poller import ActiveBranch

FIXTURE_REPO = os.path.join(os.path.dirname(__file__), "..", "fixtures", "conflict-repo")


def _branch(name):
    return ActiveBranch(branch_name=name, author="test", pr_number=1, head_sha="abc")


def test_get_changed_files_returns_touched_file():
    files = get_changed_files(FIXTURE_REPO, "main", "feature/oauth-login")
    assert "src/auth.js" in files


def test_get_changed_files_for_non_conflicting_branch():
    files = get_changed_files(FIXTURE_REPO, "main", "chore/add-comment")
    assert "src/auth.js" in files


def test_find_overlapping_files_flags_shared_file():
    branches = [
        _branch("feature/oauth-login"),
        _branch("fix/session-timeout"),
        _branch("chore/add-comment"),
    ]
    overlaps = find_overlapping_files(FIXTURE_REPO, "main", branches)

    matching = [o for o in overlaps if o.file == "src/auth.js"]
    assert len(matching) == 1
    assert len(matching[0].branches) == 3
