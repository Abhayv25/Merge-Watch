"""
config.py
---------
Responsibility: load mergewatch.config.json from the target repo, with
sensible defaults so the tool still runs even if the file is missing or
has a typo in it.
"""

import dataclasses
import json
import os
from dataclasses import dataclass


@dataclass
class MergewatchConfig:
    base_branch: str
    webhook_url: str
    use_llm_messages: bool
    state_file_path: str


DEFAULT_CONFIG = MergewatchConfig(
    base_branch="main",
    webhook_url="",
    use_llm_messages=False,
    state_file_path=".mergewatch-state.json",
)

CONFIG_FILENAME = "mergewatch.config.json"


def load_config(repo_path: str) -> MergewatchConfig:
    """
    Loads mergewatch.config.json from repo_path, merging it over the
    defaults. Should never raise -- a missing or malformed config file
    just means you fall back to DEFAULT_CONFIG, since the tool should
    still be able to run.

    DONE. All four steps are implemented below:
    1. Build config_path by joining repo_path with CONFIG_FILENAME.
    2. If the file doesn't exist, fall back to a fresh copy of
       DEFAULT_CONFIG.
    3. Otherwise, try to open and json.load() it -- on any OSError or
       json.JSONDecodeError (missing/unreadable file, corrupt JSON),
       fall back to DEFAULT_CONFIG the same way.
    4. Otherwise, build a new MergewatchConfig from DEFAULT_CONFIG's
       values, overridden by whatever camelCase keys were actually
       present in the parsed JSON (a config file that only sets one
       field still gets sane defaults for the rest).
    """
    config_path = os.path.join(repo_path, CONFIG_FILENAME)

    if not os.path.exists(config_path):
        return dataclasses.replace(DEFAULT_CONFIG)

    try:
        with open(config_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Invalid JSON")
        return dataclasses.replace(DEFAULT_CONFIG)

    return MergewatchConfig(
        base_branch=data.get("baseBranch", DEFAULT_CONFIG.base_branch),
        webhook_url=data.get("webhookUrl", DEFAULT_CONFIG.webhook_url),
        use_llm_messages=data.get("useLlmMessages", DEFAULT_CONFIG.use_llm_messages),
        state_file_path=data.get("stateFilePath", DEFAULT_CONFIG.state_file_path),
    )
