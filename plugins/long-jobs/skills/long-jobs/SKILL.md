---
name: long-jobs
description: Run or wait for a long command (cargo test, a build, CI, a server, a benchmark), or check whether one is still running. Load before starting one in the background, before writing any wait loop, and before reporting that something "still runs".
---

# Long commands and waits

A wait that never notices its job ended, or a job whose result is lost,
costs more than the job. These rules come from mistakes that recurred
across sessions (a `pgrep -f` wait matched its own command line and
reported a finished `cargo test` as running for 40 minutes).

## 1. Start long commands with `run_in_background`

Run the long command itself as a Bash call with `run_in_background:
true`. The harness sends one notice when it exits; do not poll its
output file while waiting.

Never write `cmd &` inside a foreground call: the job detaches, no
notice comes, and its exit status is lost (a hook refuses it).

## 2. Keep the whole output and the exit status

```sh
cargo test > "$LOG" 2>&1; echo "exit=$?"
```

A summary grep is not a result: `cargo test` stops at the first failing
test binary, and a filtered log can look clean when the run aborted.
Read the exit status first, then the log.

## 3. Wait for a condition with Monitor, matching every terminal state

For "tell me when X happens" use the Monitor tool (or a background
Bash `until` loop for a single notice). Its filter must end on success,
failure and timeout alike, so that silence never stands for "still
running":

```sh
until grep -qE '^exit=|error:|panicked' "$LOG"; do sleep 2; done; tail -3 "$LOG"
```

## 4. Never use `pgrep -f`/`pkill -f` with a plain pattern

The Bash tool runs each call in a shell whose command line holds the
whole call, so `pgrep -f PATTERN` always matches that shell: a check
says "running" forever, a wait loop never ends (a `pgrep -f` wait once
reported a finished `cargo test` as running for 40 minutes), and
`pkill -f PATTERN` kills the call itself. A hook refuses `pgrep -f`/
`pkill -f` unless the pattern starts with a bracket, loop or not, and
inside `bash -c '...'` too.

- Where the process name is enough, use `pgrep -x NAME` or `pidof NAME`.
- Otherwise put the pattern's first letter in brackets, which cannot
  match its own text: `pgrep -af "[c]argo test"`. The bracketed pattern
  must be the only mention of the name in the call: in
  `pgrep -af cargo; pgrep -af "[c]argo"`, both list the tool's shell,
  whose command line holds the plain `cargo`.

To wait for a process you did not start in the background, take its PID
once (`pgrep -x NAME`, `pgrep -f "[c]argo test"` or `ps`, checked by
hand) and wait on it:

```sh
tail --pid="$PID" -f /dev/null      # or: while kill -0 "$PID" 2>/dev/null; do sleep 5; done
```

## 5. Check before saying "still running"

When a job runs longer than expected, look before reporting:

```sh
ps -eo pid,etimes,pcpu,args --sort=-pcpu | head
ls -l --time-style=+%H:%M "$LOG"; date +%H:%M
```

Idle CPU and a log untouched for minutes mean it ended (or hangs):
find out which.

## 6. One cargo run per target directory at a time

A background `cargo test` holds the target directory's lock: a second
cargo command on it (a build, clippy, another test) waits, or rebuilds
binaries the first run is using. Start the next cargo command after the
first one's notice, or give it its own `CARGO_TARGET_DIR` (another
worktree's).

## 7. CI

Wait with the tools that know the run, in a background call:

```sh
gh pr checks N --watch --fail-fast; echo "exit=$?"
gh run watch RUN_ID --exit-status; echo "exit=$?"
```

not a hand-written poll of `gh pr checks`.
