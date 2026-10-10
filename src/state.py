"""
Tracks which collisions have already been flagged, so a job that runs every
15 minutes doesn't notify the same unresolved conflict over and over.

Two stores share one small interface:

  FileStateStore    a JSON file; for local runs
  DynamoStateStore  a DynamoDB table; for AWS Lambda, where the local disk
                    does not survive between runs

The file store is what the GitHub Actions version used, and it never actually
deduplicated anything there: the runner's disk is thrown away after every
job, so the state file was lost and every run re-sent every alert.
"""

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Optional, Protocol


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


class StateStore(Protocol):
    def has_been_notified(self, key: str) -> bool: ...

    def claim(self, key: str) -> bool:
        """Records the key; returns False if it was already recorded."""
        ...

    def release(self, key: str) -> None:
        """Undoes a claim, for when the notification could not be delivered."""
        ...

    def flush(self) -> None: ...


class FileStateStore:
    def __init__(self, path: str):
        self._path = path
        self._state = load_state(path)

    def has_been_notified(self, key: str) -> bool:
        return has_been_notified(self._state, key)

    def claim(self, key: str) -> bool:
        if self.has_been_notified(key):
            return False
        self._state = record_notification(self._state, key)
        return True

    def release(self, key: str) -> None:
        self._state = [entry for entry in self._state if entry.key != key]

    def flush(self) -> None:
        save_state(self._path, self._state)


class DynamoStateStore:
    """
    One item per notified collision: {"collision_key", "notified_at", "expires_at"}.

    claim() is a conditional write (attribute_not_exists), so if two runs ever
    overlap only one of them sends the alert. expires_at is a DynamoDB TTL
    attribute: a conflict that is still unresolved after ttl_days gets
    re-announced as a reminder instead of being silenced forever.
    """

    def __init__(self, table_name: str, ttl_days: int = 30, client: Optional[object] = None):
        if client is None:
            import boto3

            client = boto3.client("dynamodb")
        self._client = client
        self._table = table_name
        self._ttl_seconds = ttl_days * 24 * 60 * 60

    def has_been_notified(self, key: str) -> bool:
        response = self._client.get_item(
            TableName=self._table,
            Key={"collision_key": {"S": key}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if item is None:
            return False
        # TTL deletion runs in the background and can lag; treat expired as absent.
        return int(item.get("expires_at", {"N": "0"})["N"]) > int(time.time())

    def claim(self, key: str) -> bool:
        now = int(time.time())
        try:
            self._client.put_item(
                TableName=self._table,
                Item={
                    "collision_key": {"S": key},
                    "notified_at": {"S": datetime.now(timezone.utc).isoformat()},
                    "expires_at": {"N": str(now + self._ttl_seconds)},
                },
                ConditionExpression="attribute_not_exists(collision_key) OR expires_at < :now",
                ExpressionAttributeValues={":now": {"N": str(now)}},
            )
            return True
        except self._client.exceptions.ConditionalCheckFailedException:
            return False

    def release(self, key: str) -> None:
        self._client.delete_item(TableName=self._table, Key={"collision_key": {"S": key}})

    def flush(self) -> None:
        pass  # every write is already durable
