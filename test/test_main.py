import json
import subprocess

import src.main as cli
from conftest import REPO_DIR


def test_cli_finds_conflict_in_a_ci_style_checkout(tmp_path, monkeypatch, capsys, github_like_remote):
    remote, branches = github_like_remote
    # Like actions/checkout: a clone where PR branches exist only as origin/<name>.
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "clone", "--quiet", REPO_DIR, str(checkout)], check=True)
    monkeypatch.chdir(checkout)
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    monkeypatch.setenv("GITHUB_TOKEN", "")
    monkeypatch.setenv("MERGEWATCH_WEBHOOK_URL", "")
    monkeypatch.setattr(cli, "fetch_active_branches", lambda owner, repo, token: list(branches))
    monkeypatch.setattr(cli, "github_clone_url", lambda owner, repo: remote)

    assert cli.main() == 0

    out = capsys.readouterr().out.strip().splitlines()
    summary = json.loads(out[-1])
    assert summary["conflicts_found"] == 1
    assert summary["notifications_sent"] == 1
    assert any("src/auth.js" in line for line in out[:-1])


def test_cli_requires_repository(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert cli.main() == 1
