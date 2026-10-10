"""
AWS Lambda entry point. EventBridge Scheduler invokes handler() every 15
minutes.

Each invocation:
  1. reads the GitHub token and webhook URL from SSM Parameter Store
     (cached for the life of a warm Lambda container)
  2. lists open pull requests through the GitHub API
  3. fetches the base branch and every PR head into a bare repository under
     /tmp, the only writable path in Lambda; a warm container reuses it, so
     only new commits are downloaded
  4. runs the conflict check, recording notified collisions in DynamoDB
  5. logs one JSON summary line for CloudWatch Logs Insights

Environment:
  MERGEWATCH_REPOSITORY            owner/repo to watch
  MERGEWATCH_BASE_BRANCH           default "main"
  MERGEWATCH_TABLE                 DynamoDB table for notified collisions
  MERGEWATCH_GITHUB_TOKEN_PARAM    SSM SecureString holding a GitHub token
  MERGEWATCH_WEBHOOK_PARAM         SSM SecureString holding the webhook URL (optional)
"""

import json
import os
import time
from typing import Dict

from .checker import RunSummary, run_check
from .notifier import post_notification
from .poller import fetch_active_branches
from .state import DynamoStateStore
from .workspace import ensure_repository, github_clone_url, sync_refs

WORK_ROOT = "/tmp/mergewatch"

_parameter_cache: Dict[str, str] = {}


def _get_parameter(name: str) -> str:
    if name not in _parameter_cache:
        import boto3

        response = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
        _parameter_cache[name] = response["Parameter"]["Value"]
    return _parameter_cache[name]


def _repo_path(owner: str, repo: str) -> str:
    return os.path.join(WORK_ROOT, f"{owner}__{repo}.git")


def handler(event, context) -> dict:
    started = time.monotonic()
    repository = os.environ["MERGEWATCH_REPOSITORY"]
    owner, repo = repository.split("/", 1)
    base_branch = os.environ.get("MERGEWATCH_BASE_BRANCH", "main")

    token = _get_parameter(os.environ["MERGEWATCH_GITHUB_TOKEN_PARAM"])
    webhook_param = os.environ.get("MERGEWATCH_WEBHOOK_PARAM", "")
    webhook_url = _get_parameter(webhook_param) if webhook_param else ""

    # Failures here raise, which marks the invocation as failed in CloudWatch
    # and trips the error alarm. A silent "0 branches" would hide an outage.
    branches = fetch_active_branches(owner, repo, token)

    if len(branches) < 2:
        summary = RunSummary(active_branches=len(branches))
    else:
        repo_path = _repo_path(owner, repo)
        ensure_repository(repo_path)
        base_ref, branches = sync_refs(
            repo_path, github_clone_url(owner, repo), token, base_branch, branches
        )
        summary = run_check(
            repo_path,
            base_ref,
            branches,
            DynamoStateStore(os.environ["MERGEWATCH_TABLE"]),
            notify=lambda message: post_notification(webhook_url, message),
        )

    result = summary.to_dict()
    result["repository"] = repository
    result["total_ms"] = int((time.monotonic() - started) * 1000)
    print(json.dumps({"mergewatch_run": result}))
    return result
