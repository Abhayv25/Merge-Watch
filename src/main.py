"""
Command-line entry point: checks the repository in the current directory.
Used for local runs and the manual GitHub Actions workflow. The scheduled
production run is the AWS Lambda in lambda_handler.py.

    export GITHUB_REPOSITORY=owner/repo
    python3 -m src.main
"""

import json
import os
import sys

from dotenv import load_dotenv

from .checker import run_check
from .config import load_config
from .gitcmd import GitError, run_git
from .notifier import post_notification
from .poller import GitHubApiError, fetch_active_branches
from .state import FileStateStore
from .workspace import github_clone_url, sync_refs


def main() -> int:
    load_dotenv()

    repo_path = os.getcwd()
    config = load_config(repo_path)

    repo_full_name = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo_full_name:
        print("GITHUB_REPOSITORY is not set (expected 'owner/repo'). Nothing to do.")
        return 1

    owner, repo = repo_full_name.split("/", 1)
    github_token = os.environ.get("GITHUB_TOKEN", "")
    webhook_url = os.environ.get("MERGEWATCH_WEBHOOK_URL") or config.webhook_url

    try:
        branches = fetch_active_branches(owner, repo, github_token)
        if len(branches) < 2:
            print("Fewer than 2 active branches -- nothing can collide.")
            return 0
        # Fetch every PR head (including forks) so the check never depends on
        # which branches happen to exist locally.
        run_git(repo_path, ["rev-parse", "--git-dir"])
        base_ref, branches = sync_refs(
            repo_path, github_clone_url(owner, repo), github_token, config.base_branch, branches
        )
    except (GitHubApiError, GitError) as e:
        print(f"Mergewatch could not run: {e}", file=sys.stderr)
        return 1

    summary = run_check(
        repo_path,
        base_ref,
        branches,
        FileStateStore(config.state_file_path),
        notify=lambda message: post_notification(webhook_url, message),
        use_llm_messages=config.use_llm_messages,
    )
    print(json.dumps(summary.to_dict()))
    return 1 if summary.errors else 0


if __name__ == "__main__":
    sys.exit(main())
