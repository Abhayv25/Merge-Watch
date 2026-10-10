"""
External failures must be loud. Each of these used to be swallowed and
reported as a successful, uneventful run.
"""

import pytest
import requests

from src.notifier import NotificationError, post_notification
from src.poller import GitHubApiError, fetch_active_branches


class _Response:
    def __init__(self, status):
        self.status_code = status
        self.links = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return []


def test_github_api_failure_raises(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(401))
    with pytest.raises(GitHubApiError):
        fetch_active_branches("acme", "widgets", "expired-token")


def test_webhook_error_status_raises(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Response(404))
    with pytest.raises(NotificationError):
        post_notification("https://discord.example/webhook", "hello")


def test_no_webhook_prints(capsys):
    post_notification("", "hello")
    assert "hello" in capsys.readouterr().out
