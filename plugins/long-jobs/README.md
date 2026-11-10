# long-jobs

A skill and a hook for running or waiting for long commands (`cargo
test`, builds, CI, servers, benchmarks) without losing their result.
They come from mistakes that recurred across sessions: a `pgrep -f`
wait that matched its own command line reported a finished `cargo test`
as running for 40 minutes.

## The skill

`skills/long-jobs/SKILL.md`, loaded before starting a long command in
the background, writing a wait loop, or reporting that something still
runs:

1. Start long commands with `run_in_background`, never `cmd &` in a foreground call.
2. Keep the whole output and the exit status (`cmd > "$LOG" 2>&1; echo "exit=$?"`); read the status first.
3. Wait for a condition with Monitor, on success, failure and timeout alike.
4. Never use `pgrep -f`/`pkill -f` with a plain pattern (`[c]argo`, or `pgrep -x`); wait on a PID (`tail --pid`, `kill -0`).
5. Look (CPU, the log's time) before saying "still running".
6. One cargo run per target directory at a time.
7. Wait for CI with `gh pr checks --watch` or `gh run watch`, in a background call.

## The hook

`hooks/long-jobs-guard.py`, a `PreToolUse` hook on Bash, denies:

- `pgrep -f`/`pkill -f` (or `--full`) whose pattern does not start
  with a bracket (`[c]argo test`), loop or not, also inside `bash -c
  '...'`: the Bash tool's own shell holds the pattern on its command
  line, so a check always says running and `pkill -f` kills the call;
- a job sent to the background with a lone `&` (not `&&`, `>&`, `&>`,
  `<&`, `|&`) when the call is not run with `run_in_background` and no
  `wait` command follows the last job: no notice comes and the status
  is lost.

The hook reads the command as the shell does: quoted strings (but the
command substitutions inside double quotes, read with the same rules up
to their own `)`), backslash-escaped characters, comments, heredoc
bodies and arithmetic `$((...))` do not count, so a commit message, a
`gh pr create --body "$(cat <<'EOF' ... EOF)"` or a script's text
passes. On a parse problem the
call passes.

Known limits, accepted as rare:

- Missed: a pattern the hook cannot see (`echo cargo | xargs pgrep -f`,
  a script fed to a shell as a heredoc, `ssh host '...'`,
  `watch '...'`); the `$(...)` inside the body of a heredoc whose
  delimiter is unquoted; a bracketed pattern while the call mentions
  the plain name elsewhere (see the skill).
- Denied though harmless: `pgrep` as a mere argument (`echo pgrep -f
  x`); patterns that cannot match the shell for another reason
  (`pgrep -fx cargo`, `"^cargo"`): bracket them.
- A `case` pattern's `)` inside a double-quoted `$(...)` ends the
  substitution early.

## Enabling it in a repository

`.claude/settings.json` of the repository:

```json
{
  "extraKnownMarketplaces": {
    "quarz-lang": { "source": { "source": "github", "repo": "quarz-lang/claude-plugins" } }
  },
  "enabledPlugins": { "long-jobs@quarz-lang": true }
}
```

Claude Code offers to install the marketplace and the plugin when the
repository is opened. A running session loads the hook after `/hooks`
or a restart; `sleep 1 &` is then denied.

## Testing

```sh
python3 plugins/long-jobs/hooks/long-jobs-guard-test.py
```

pipes each case to the hook and exits 1 when one does not come out as
expected.
