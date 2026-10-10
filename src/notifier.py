"""
Turns a confirmed conflict into a message and sends it somewhere a human
will see it. Kept separate from merge_check.py on purpose: this module
never decides whether something is a conflict, only how to describe one
that's already been confirmed.
"""

import os
from dataclasses import dataclass
from typing import Optional

import requests

from .merge_check import ConflictResult
from .poller import ActiveBranch


@dataclass
class CollisionNotification:
    file: str
    branch_a: ActiveBranch
    branch_b: ActiveBranch
    conflict: ConflictResult


def _template_message(notification: CollisionNotification) -> str:
    return (
        f"Possible collision on {notification.file}: "
        f"@{notification.branch_a.author} ({notification.branch_a.branch_name}) and "
        f"@{notification.branch_b.author} ({notification.branch_b.branch_name}) "
        f"both changed this file, and merging both right now would conflict."
    )


def _llm_message(notification: CollisionNotification) -> Optional[str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    prompt = (
        "Rewrite this as one short, friendly message for a team chat, no more "
        "than two sentences. Don't invent any details beyond what's given.\n\n"
        f"File: {notification.file}\n"
        f"Branch A: {notification.branch_a.branch_name} (by {notification.branch_a.author})\n"
        f"Branch B: {notification.branch_b.branch_name} (by {notification.branch_b.author})\n"
        "These two branches would conflict if merged right now."
    )

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"LLM message generation failed, falling back to template: {e}")
        return None


def build_message(notification: CollisionNotification, use_llm: bool) -> str:
    if use_llm:
        polished = _llm_message(notification)
        if polished:
            return polished
    return _template_message(notification)


class NotificationError(RuntimeError):
    pass


def post_notification(webhook_url: str, message: str) -> None:
    """
    Sends the message to a Discord or Slack webhook, or prints it when no
    webhook is configured. Raises NotificationError if delivery fails, so the
    caller does not record the conflict as notified when nobody was told.
    """
    if not webhook_url:
        print(message)
        return

    # Discord reads "content", Slack reads "text"; sending both works for either.
    payload = {"content": message, "text": message}
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise NotificationError(f"Webhook delivery failed: {e}") from e
