"""
DynamoDB state store and the Lambda handler, against moto's in-memory AWS.
"""

import os
import time

import boto3
import pytest
from moto import mock_aws

import src.lambda_handler as lambda_handler
from src.state import DynamoStateStore

TABLE = "mergewatch-notified"
REGION = "us-east-1"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "collision_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "collision_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


def test_claim_is_exclusive(aws):
    store = DynamoStateStore(TABLE)
    assert store.has_been_notified("k") is False
    assert store.claim("k") is True
    assert store.claim("k") is False  # a second, overlapping run loses the race
    assert store.has_been_notified("k") is True


def test_release_allows_retry(aws):
    store = DynamoStateStore(TABLE)
    store.claim("k")
    store.release("k")
    assert store.has_been_notified("k") is False
    assert store.claim("k") is True


def test_expired_entry_is_treated_as_absent(aws):
    client = boto3.client("dynamodb")
    client.put_item(
        TableName=TABLE,
        Item={
            "collision_key": {"S": "old"},
            "notified_at": {"S": "2026-01-01T00:00:00+00:00"},
            "expires_at": {"N": str(int(time.time()) - 60)},
        },
    )
    store = DynamoStateStore(TABLE)
    assert store.has_been_notified("old") is False
    assert store.claim("old") is True  # reminder after the TTL window


def test_lambda_handler_end_to_end(aws, monkeypatch, tmp_path, github_like_remote):
    remote, branches = github_like_remote
    ssm = boto3.client("ssm")
    ssm.put_parameter(Name="/mergewatch/github-token", Value="ghp_test", Type="SecureString")

    monkeypatch.setenv("MERGEWATCH_REPOSITORY", "acme/widgets")
    monkeypatch.setenv("MERGEWATCH_TABLE", TABLE)
    monkeypatch.setenv("MERGEWATCH_GITHUB_TOKEN_PARAM", "/mergewatch/github-token")
    monkeypatch.delenv("MERGEWATCH_WEBHOOK_PARAM", raising=False)
    monkeypatch.setattr(lambda_handler, "WORK_ROOT", str(tmp_path / "lambda-tmp"))
    monkeypatch.setattr(lambda_handler, "_parameter_cache", {})
    monkeypatch.setattr(lambda_handler, "github_clone_url", lambda owner, repo: remote)

    seen_tokens = []

    def fake_fetch(owner, repo, token):
        seen_tokens.append(token)
        return list(branches)

    monkeypatch.setattr(lambda_handler, "fetch_active_branches", fake_fetch)

    first = lambda_handler.handler({}, None)
    second = lambda_handler.handler({}, None)  # warm container, same /tmp repo

    assert seen_tokens == ["ghp_test", "ghp_test"]
    assert first["conflicts_found"] == 1
    assert first["notifications_sent"] == 1
    # State lives in DynamoDB, so the next invocation does not re-alert.
    assert second["notifications_sent"] == 0
    assert second["skipped_already_notified"] == 1
    assert first["repository"] == "acme/widgets"
    assert os.path.isdir(str(tmp_path / "lambda-tmp" / "acme__widgets.git"))
