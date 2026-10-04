# GitHub Merge Conflict Agent

Watches a repository's active branches and warns a team before two of them
would actually conflict on merge, instead of letting someone discover it
by trying to merge and failing. Detection is handled entirely by `git`
itself, using `git merge-tree` to simulate a real three-way merge between
two branches in memory. There's no heuristic or guesswork involved: if the
tool says two branches conflict, it's because git actually tried to merge
them and hit a real conflict.

## How it works

1. **Poll active branches.** Every open pull request on the repo is
   treated as an active branch (`src/poller.py`, via the GitHub REST API).
2. **Find overlapping files.** For every active branch, diff it against
   the base branch to see which files it touched, then narrow down to
   files touched by two or more branches at once (`src/overlap.py`). Most
   branch pairs don't touch the same files, so this cuts out a lot of
   unnecessary work before the expensive step.
3. **Check for a real conflict.** For each pair of branches that share a
   file, run `git merge-tree --write-tree` between them. This performs an
   actual in-memory three-way merge and reports whether it would conflict
   (`src/merge_check.py`).
4. **Notify once per conflict.** If a conflict is found, build a message
   and post it to a Discord or Slack webhook (`src/notifier.py`). A small
   state file keeps track of which conflicts have already been reported,
   so a job that runs every 15 minutes doesn't spam the same unresolved
   conflict over and over (`src/state.py`).

`src/main.py` ties these together and is the entry point GitHub Actions
runs on a schedule.

## Requirements

- Python 3.11+
- Git (needs a version that supports `git merge-tree --write-tree`;
  anything from the last few years works)

## Setup

```bash
git clone <this repo>
cd mergewatch
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with:

- `GITHUB_TOKEN` -- a personal access token with read access to pull
  requests on the repo you're monitoring.
- `MERGEWATCH_WEBHOOK_URL` -- a Discord or Slack incoming webhook URL.
  Leave this blank and notifications print to the console instead, which
  is useful for testing locally.

`OPENAI_API_KEY` is optional. If set and `useLlmMessages` is `true` in
the config, notification text gets rewritten into something more natural
by an LLM call. If it's not set, or the call fails for any reason, the
tool falls back to a plain template message -- it never depends on the
LLM call succeeding.

## Configuration

`mergewatch.config.json` in the root of the repo being monitored:

```json
{
  "baseBranch": "main",
  "webhookUrl": "",
  "useLlmMessages": false,
  "stateFilePath": ".mergewatch-state.json"
}
```

All fields are optional and fall back to sane defaults if the file is
missing entirely. `webhookUrl` here is meant to stay blank in version
control -- set the real value through `MERGEWATCH_WEBHOOK_URL` instead,
so it isn't committed to the repo.

## Running

```bash
export GITHUB_REPOSITORY=your-org/your-repo
python3 -m src.main
```

## Tests

```bash
pytest -v
```

Tests for the conflict-detection logic run against a real git repository
at `fixtures/conflict-repo/`, not mocked git output. It has branches that
are known, verified ahead of time to produce both a genuine conflict and
a genuine clean merge, so the tests are checking actual git behavior.

That repo isn't committed to version control -- a git repo nested inside
this one causes problems when pushed to GitHub. `fixtures/setup_fixture_repo.sh`
rebuilds it from scratch instead, and `test/conftest.py` runs that script
automatically the first time you run `pytest`, so no manual setup step is
needed.

## Deployment

`.github/workflows/mergewatch.yml` runs the tool on a 15-minute schedule
via GitHub Actions. It needs one repo secret:

- `MERGEWATCH_WEBHOOK_URL`

`GITHUB_TOKEN` is provided automatically by Actions and doesn't need to
be set up separately.

## Project structure

```
src/
  config.py      loads mergewatch.config.json, with defaults
  poller.py      fetches branches with an open pull request
  overlap.py     finds files touched by more than one active branch
  merge_check.py runs the actual git merge-tree conflict check
  state.py       tracks which conflicts have already been reported
  notifier.py    builds and sends the notification message
  main.py        orchestrates all of the above
test/            tests for the modules above, run against fixtures/conflict-repo
                 conftest.py builds that repo automatically before tests run
fixtures/
  setup_fixture_repo.sh  builds the test fixture repo (not committed itself)
```
