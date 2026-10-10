import pytest

from conftest import REPO_DIR, fixture_branch, sha_of
from src.gitcmd import GitError
from src.overlap import find_overlapping_files, get_changed_files


def test_get_changed_files_returns_touched_file():
    files = get_changed_files(REPO_DIR, "main", sha_of("feature/oauth-login"))
    assert "src/auth.js" in files


def test_get_changed_files_for_non_conflicting_branch():
    files = get_changed_files(REPO_DIR, "main", sha_of("chore/add-comment"))
    assert "src/auth.js" in files


def test_get_changed_files_raises_on_unknown_ref():
    with pytest.raises(GitError):
        get_changed_files(REPO_DIR, "main", "0" * 40)


def test_find_overlapping_files_flags_shared_file():
    branches = [
        fixture_branch("feature/oauth-login", 1),
        fixture_branch("fix/session-timeout", 2),
        fixture_branch("chore/add-comment", 3),
    ]
    overlaps = find_overlapping_files(REPO_DIR, "main", branches)

    matching = [o for o in overlaps if o.file == "src/auth.js"]
    assert len(matching) == 1
    assert len(matching[0].branches) == 3
