from src.state import (
    NotifiedCollision,
    build_collision_key,
    has_been_notified,
    load_state,
    record_notification,
    save_state,
)


def test_build_collision_key_is_order_independent():
    a = build_collision_key("src/auth.js", "feature/a", "fix/b")
    b = build_collision_key("src/auth.js", "fix/b", "feature/a")
    assert a == b


def test_load_state_missing_file_returns_empty_list(tmp_path):
    assert load_state(str(tmp_path / "does-not-exist.json")) == []


def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / "state.json")
    original = [NotifiedCollision(key="a::b::c", notified_at="2026-01-01T00:00:00+00:00")]

    save_state(path, original)
    loaded = load_state(path)

    assert loaded == original


def test_has_been_notified():
    state = [NotifiedCollision(key="known-key", notified_at="2026-01-01T00:00:00+00:00")]
    assert has_been_notified(state, "known-key") is True
    assert has_been_notified(state, "other-key") is False


def test_record_notification_does_not_mutate_original():
    state = []
    new_state = record_notification(state, "a-new-key")

    assert state == []
    assert len(new_state) == 1
    assert new_state[0].key == "a-new-key"
