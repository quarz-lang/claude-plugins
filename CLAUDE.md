# Working on claude-plugins

The Claude Code plugins of the Quarz repositories: a marketplace
(`.claude-plugin/marketplace.json`) and one directory per plugin under
`plugins/`. Code, comments, commit messages and the docs are in English.

## Before committing

```sh
python3 plugins/long-jobs/hooks/long-jobs-guard-test.py
```

- A change to a hook adds a case to its test.
- Stage files by explicit path. Never print secrets (tokens).
- Do not put a `Claude-Session:` line in commit messages, nor a Claude
  session URL in pull request descriptions.
- Do not install a plugin into `~/.claude` to try it: the repositories
  enable it through their settings.

## Pull requests

- Work on a branch and open a draft pull request with the first commit.
- Review the branch's diff with a fresh subagent before the pull request
  leaves draft, and fix what it finds that needs no decision.
- The description says what was verified. quarz-manager merges.
