import pytest

from conftest import REPO_DIR, fixture_branch
from src.gitcmd import GitError
from src.merge_check import check_merge_conflict
from src.poller import ActiveBranch


def test_detects_real_conflict():
    result = check_merge_conflict(
        REPO_DIR, fixture_branch("feature/oauth-login"), fixture_branch("fix/session-timeout")
    )
    assert result.has_conflict is True
    assert result.conflicting_files == ["src/auth.js"]


def test_clean_merge_has_no_conflict():
    result = check_merge_conflict(
        REPO_DIR, fixture_branch("feature/oauth-login"), fixture_branch("chore/add-comment")
    )
    assert result.has_conflict is False
    assert result.conflicting_files == []


def test_conflict_result_is_order_independent():
    a_vs_b = check_merge_conflict(
        REPO_DIR, fixture_branch("feature/oauth-login"), fixture_branch("fix/session-timeout")
    )
    b_vs_a = check_merge_conflict(
        REPO_DIR, fixture_branch("fix/session-timeout"), fixture_branch("feature/oauth-login")
    )
    assert a_vs_b.has_conflict is True
    assert b_vs_a.has_conflict is True


def test_unknown_commit_raises_instead_of_reporting_no_conflict():
    # Before the fix, a bad ref produced empty output, which was read as
    # "no conflict" -- real conflicts were missed with no error at all.
    missing = ActiveBranch("gone", "test", 9, "0" * 40)
    with pytest.raises(GitError):
        check_merge_conflict(REPO_DIR, fixture_branch("feature/oauth-login"), missing)
