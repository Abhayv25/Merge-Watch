"""
Orchestrates one full run: find active branches, narrow to the files more
than one of them touched, check each contested pair for a real conflict,
and notify on anything new. This is the entry point GitHub Actions runs.
"""

import itertools
import os

from dotenv import load_dotenv

from .config import load_config
from .merge_check import check_merge_conflict
from .notifier import CollisionNotification, build_message, post_notification
from .overlap import find_overlapping_files
from .poller import fetch_active_branches
from .state import (
    build_collision_key,
    has_been_notified,
    load_state,
    record_notification,
    save_state,
)


def main() -> None:
    load_dotenv()

    repo_path = os.getcwd()
    config = load_config(repo_path)

    repo_full_name = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo_full_name:
        print("GITHUB_REPOSITORY is not set (expected 'owner/repo'). Nothing to do.")
        return

    owner, repo = repo_full_name.split("/", 1)
    github_token = os.environ.get("GITHUB_TOKEN", "")

    branches = fetch_active_branches(owner, repo, github_token)
    if len(branches) < 2:
        print("Fewer than 2 active branches -- nothing can collide.")
        return

    overlaps = find_overlapping_files(repo_path, config.base_branch, branches)
    state = load_state(config.state_file_path)

    for overlap in overlaps:
        for branch_a, branch_b in itertools.combinations(overlap.branches, 2):
            try:
                key = build_collision_key(
                    overlap.file, branch_a.branch_name, branch_b.branch_name
                )
                if has_been_notified(state, key):
                    continue

                result = check_merge_conflict(repo_path, branch_a, branch_b)
                if not result.has_conflict:
                    continue

                notification = CollisionNotification(
                    file=overlap.file,
                    branch_a=branch_a,
                    branch_b=branch_b,
                    conflict=result,
                )
                message = build_message(notification, config.use_llm_messages)
                post_notification(config.webhook_url, message)

                state = record_notification(state, key)
            except Exception as e:
                print(f"Skipping {branch_a.branch_name} <-> {branch_b.branch_name}: {e}")

    save_state(config.state_file_path, state)


if __name__ == "__main__":
    main()
