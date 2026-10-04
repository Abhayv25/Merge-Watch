import os

from src.merge_check import check_merge_conflict
from src.poller import ActiveBranch

FIXTURE_REPO = os.path.join(os.path.dirname(__file__), "..", "fixtures", "conflict-repo")


def _branch(name):
    return ActiveBranch(branch_name=name, author="test", pr_number=1, head_sha="abc")


def test_detects_real_conflict():
    result = check_merge_conflict(
        FIXTURE_REPO, _branch("feature/oauth-login"), _branch("fix/session-timeout")
    )
    assert result.has_conflict is True
    assert "src/auth.js" in result.conflicting_files


def test_clean_merge_has_no_conflict():
    result = check_merge_conflict(
        FIXTURE_REPO, _branch("feature/oauth-login"), _branch("chore/add-comment")
    )
    assert result.has_conflict is False
    assert result.conflicting_files == []


def test_conflict_result_is_order_independent():
    a_vs_b = check_merge_conflict(
        FIXTURE_REPO, _branch("feature/oauth-login"), _branch("fix/session-timeout")
    )
    b_vs_a = check_merge_conflict(
        FIXTURE_REPO, _branch("fix/session-timeout"), _branch("feature/oauth-login")
    )
    assert a_vs_b.has_conflict is True
    assert b_vs_a.has_conflict is True
