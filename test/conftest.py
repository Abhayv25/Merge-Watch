import os
import subprocess

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
REPO_DIR = os.path.join(FIXTURES_DIR, "conflict-repo")
SETUP_SCRIPT = os.path.join(FIXTURES_DIR, "setup_fixture_repo.sh")


@pytest.fixture(scope="session", autouse=True)
def fixture_repo():
    # The fixture repo isn't committed to version control (a git repo
    # nested inside this one causes problems), so build it fresh if it's
    # not already there.
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        subprocess.run(["bash", SETUP_SCRIPT], check=True)
