"""
Tracks which collisions have already been flagged, so a job that runs every
15 minutes doesn't notify the same unresolved conflict over and over.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List


@dataclass
class NotifiedCollision:
    key: str
    notified_at: str


def build_collision_key(file: str, branch_name_a: str, branch_name_b: str) -> str:
    # Sort the branch names so (A, B) and (B, A) produce the same key --
    # otherwise the same collision could get notified twice.
    first, second = sorted([branch_name_a, branch_name_b])
    return f"{file}::{first}::{second}"


def load_state(state_file_path: str) -> List[NotifiedCollision]:
    if not os.path.exists(state_file_path):
        return []

    try:
        with open(state_file_path) as f:
            data = json.load(f)
        return [NotifiedCollision(**entry) for entry in data]
    except (OSError, json.JSONDecodeError, TypeError) as e:
        print(f"Failed to read state file {state_file_path}, starting fresh: {e}")
        return []


def save_state(state_file_path: str, state: List[NotifiedCollision]) -> None:
    with open(state_file_path, "w") as f:
        json.dump([asdict(entry) for entry in state], f, indent=2)


def has_been_notified(state: List[NotifiedCollision], key: str) -> bool:
    return any(entry.key == key for entry in state)


def record_notification(
    state: List[NotifiedCollision], key: str
) -> List[NotifiedCollision]:
    new_entry = NotifiedCollision(
        key=key,
        notified_at=datetime.now(timezone.utc).isoformat(),
    )
    return state + [new_entry]
