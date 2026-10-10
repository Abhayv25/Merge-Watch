"""
Fetches the branches that currently have an open pull request on a repo.
Everything downstream operates on the list this returns.
"""

from dataclasses import dataclass
from typing import List

import requests


class GitHubApiError(RuntimeError):
    pass


@dataclass
class ActiveBranch:
    branch_name: str
    author: str
    pr_number: int
    head_sha: str


def fetch_active_branches(owner: str, repo: str, github_token: str) -> List[ActiveBranch]:
    """
    Raises GitHubApiError if the API can't be reached. Returning an empty list
    instead would look exactly like "no open PRs", so an expired token or a
    GitHub outage would never be noticed.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=100"
    branches = []

    try:
        while url:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            for pr in response.json():
                branches.append(ActiveBranch(
                    branch_name=pr["head"]["ref"],
                    author=pr["user"]["login"],
                    pr_number=pr["number"],
                    head_sha=pr["head"]["sha"],
                ))

            url = response.links.get("next", {}).get("url")
    except requests.RequestException as e:
        raise GitHubApiError(f"Failed to fetch open pull requests for {owner}/{repo}: {e}") from e

    return branches
