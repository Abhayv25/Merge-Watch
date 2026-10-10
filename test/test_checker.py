from conftest import REPO_DIR, fixture_branch
from src.checker import run_check
from src.state import FileStateStore


def _branches():
    return [
        fixture_branch("feature/oauth-login", 1),
        fixture_branch("fix/session-timeout", 2),
        fixture_branch("chore/add-comment", 3),
    ]


def test_notifies_once_per_conflict_across_runs(tmp_path):
    state_path = str(tmp_path / "state.json")
    sent = []

    first = run_check(REPO_DIR, "main", _branches(), FileStateStore(state_path), sent.append)
    second = run_check(REPO_DIR, "main", _branches(), FileStateStore(state_path), sent.append)

    assert first.pairs_checked == 3  # three branches share src/auth.js
    assert first.conflicts_found == 1
    assert first.notifications_sent == 1
    assert second.notifications_sent == 0
    assert second.skipped_already_notified == 1
    assert len(sent) == 1


def test_failed_delivery_is_retried_next_run(tmp_path):
    state_path = str(tmp_path / "state.json")

    def broken_webhook(message):
        raise RuntimeError("webhook returned 500")

    failed = run_check(REPO_DIR, "main", _branches(), FileStateStore(state_path), broken_webhook)
    assert failed.errors == 1
    assert failed.notifications_sent == 0

    sent = []
    retried = run_check(REPO_DIR, "main", _branches(), FileStateStore(state_path), sent.append)
    assert retried.notifications_sent == 1


def test_fewer_than_two_branches_does_nothing(tmp_path):
    summary = run_check(
        REPO_DIR, "main", _branches()[:1], FileStateStore(str(tmp_path / "s.json")), print
    )
    assert summary.pairs_checked == 0
