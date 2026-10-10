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
   file, run `git merge-tree --write-tree` between the two head commits.
   This performs an actual in-memory three-way merge and reports whether it
   would conflict (`src/merge_check.py`).
4. **Notify once per conflict.** If a conflict is found, build a message
   and post it to a Discord or Slack webhook (`src/notifier.py`). A state
   store keeps track of which conflicts have already been reported, so a
   job that runs every 15 minutes doesn't spam the same unresolved
   conflict over and over (`src/state.py`).

`src/checker.py` ties these together. It has two entry points: an AWS
Lambda function that runs every 15 minutes (`src/lambda_handler.py`), and
a command-line version for local and manual runs (`src/main.py`).

## Architecture on AWS

```
EventBridge Scheduler --every 15 min--> Lambda (container image from ECR)
                                          |-- SSM Parameter Store: GitHub token, webhook URL
                                          |-- GitHub API: list open pull requests
                                          |-- git fetch into /tmp: base branch + each PR head
                                          |-- DynamoDB: which conflicts were already announced
                                          |-- Discord / Slack webhook
                                          '-- CloudWatch Logs + alarm on repeated failures
```

- **EventBridge Scheduler** invokes the function on a fixed rate.
- **Lambda** runs the same Python code as the CLI, packaged as a Docker
  image (the stock Lambda Python images don't include git).
- **DynamoDB** stores one item per announced conflict. Writes are
  conditional, so two overlapping runs can never both send the same alert,
  and items expire after 30 days so an unresolved conflict gets a reminder.
- **SSM Parameter Store** holds the GitHub token and webhook URL as
  encrypted parameters; nothing secret is in the code, the image, or
  Terraform state.
- **CloudWatch** keeps 14 days of logs (each run writes one JSON summary
  line) and alarms if the function fails twice in a row.

### Why it moved off GitHub Actions

The first version ran as a GitHub Actions cron job. Running it, then
reproducing its CI environment in tests, showed three problems:

1. **The schedule was not reliable.** GitHub runs scheduled workflows on a
   best-effort basis. A 15-minute schedule on this repo fired 5 times in
   about 18 hours on October 4, 2026, roughly 7% of the expected runs, with
   gaps of 2.6 to 5.8 hours between them.
2. **Conflicts were missed silently in CI.** The checks used branch names,
   but in a fresh clone a pull request's branch exists only as
   `origin/<name>` (and not at all for PRs from forks). Every git command
   failed, the failure was read as "no conflict", and nothing reported an
   error. Checks now use commit SHAs fetched from GitHub's
   `refs/pull/<n>/head`, and any git failure raises.
3. **Duplicate alerts were never suppressed.** The "already notified"
   state file lived on the Actions runner, which is discarded after every
   job, so every run started with empty state. State now lives in DynamoDB.

The same review also made two other silent failures loud: a GitHub API
error used to look like "no open pull requests", and a webhook that
returned an error status counted as delivered.

## Requirements

- Python 3.12+
- Git (needs a version that supports `git merge-tree --write-tree`;
  anything from the last few years works)

## Setup

```bash
git clone <this repo>
cd mergewatch
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
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
`test/test_workspace.py` copies it into a GitHub-shaped remote (with
`refs/pull/<n>/head` refs) to check the fresh-clone path, and
`test/test_aws.py` runs the DynamoDB store and the Lambda handler against
moto's in-memory AWS.

That repo isn't committed to version control -- a git repo nested inside
this one causes problems when pushed to GitHub. `fixtures/setup_fixture_repo.sh`
rebuilds it from scratch instead, and `test/conftest.py` runs that script
automatically the first time you run `pytest`, so no manual setup step is
needed.

## Deployment

Infrastructure is defined with Terraform in `infra/`. Everything fits in
the AWS free tier or costs cents per month at this volume.

1. Store the secrets (a GitHub token that can read pull requests and
   contents, and the webhook URL):

   ```bash
   aws ssm put-parameter --name /mergewatch/github-token --type SecureString --value <token>
   aws ssm put-parameter --name /mergewatch/webhook-url  --type SecureString --value <url>
   ```

2. Create the image repository, then build and push the image. Lambda needs
   the image to exist before the function can be created.

   ```bash
   cd infra
   terraform init
   terraform apply -target=aws_ecr_repository.mergewatch -var repository=owner/repo

   REPO_URL=$(terraform output -raw ecr_repository_url)
   aws ecr get-login-password | docker login --username AWS --password-stdin ${REPO_URL%%/*}
   docker build --platform linux/arm64 -t $REPO_URL:latest ..
   docker push $REPO_URL:latest
   ```

3. Create everything else:

   ```bash
   terraform apply -var repository=owner/repo -var alert_email=you@example.com
   ```

4. Check it is running: `aws logs tail /aws/lambda/mergewatch --follow`.
   Each run logs a line like
   `{"mergewatch_run": {"active_branches": 4, "pairs_checked": 3, "conflicts_found": 1, ...}}`.

To pause it without deleting anything: `terraform apply -var enabled=false`.
To remove it: `terraform destroy`.

After pushing a new image, update the function with
`aws lambda update-function-code --function-name mergewatch --image-uri $REPO_URL:latest`.

`.github/workflows/mergewatch.yml` can still run a one-off check from the
Actions tab, and `.github/workflows/ci.yml` runs the tests, builds the
image, and validates the Terraform on every push.

## Project structure

```
src/
  config.py          loads mergewatch.config.json, with defaults
  poller.py          fetches branches with an open pull request
  workspace.py       fetches the base branch and every PR head into a local repo
  overlap.py         finds files touched by more than one active branch
  merge_check.py     runs the actual git merge-tree conflict check
  state.py           tracks announced conflicts (JSON file or DynamoDB)
  notifier.py        builds and sends the notification message
  checker.py         one full pass over a repository
  main.py            command-line entry point
  lambda_handler.py  AWS Lambda entry point
  gitcmd.py          runs git and raises on failure
test/                tests, run against fixtures/conflict-repo and moto
fixtures/
  setup_fixture_repo.sh  builds the test fixture repo (not committed itself)
infra/               Terraform: ECR, Lambda, EventBridge Scheduler, DynamoDB, alarms
Dockerfile           Lambda container image
```
