#!/usr/bin/env python3
"""Pipe-test long-jobs-guard.py: (command, run_in_background, expected).
Exits 1 when a case does not come out as expected."""
import json, os, subprocess, sys
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "long-jobs-guard.py")
CASES = [
    ('until ! pgrep -f "cargo test" >/dev/null; do sleep 5; done', False, "deny"),
    ('while pgrep -f quarz; do sleep 1; done', False, "deny"),
    ('until ! pgrep -f "cargo test"; do sleep 5; done', True, "deny"),
    ('cargo test > log 2>&1 &', False, "deny"),
    ('cargo test & echo started', False, "deny"),
    ('echo "a\'b"; cargo test & echo "c\'d"', False, "deny"),
    ('cat <<< "x"\ncargo test &', False, "deny"),
    ('pgrep -f quarz', False, "deny"),
    ('pkill -9 -f quarz-server; sleep 1', False, "deny"),
    ('sleep 1; pgrep -f quarz', False, "deny"),
    ('cargo build & cargo doc & wait; echo exit=$?', False, "pass"),
    ('# build & test\ncargo build', False, "pass"),
    ('a && b', False, "pass"),
    ('ls 2>&1 | head', False, "pass"),
    ('cmd |& tee x', False, "pass"),
    ('cmd &>/dev/null', False, "pass"),
    ('cmd >&2', False, "pass"),
    ('x=$(cmd 2>&1)', False, "pass"),
    ('echo "a & b"', False, "pass"),
    ('curl "http://x?a=1&b=2"', False, "pass"),
    ('cat <<EOF\nfoo & bar\nEOF', False, "pass"),
    ('sleep 5', False, "pass"),
    ('cargo test > log 2>&1 &', True, "pass"),
    ('cargo test & echo started', True, "pass"),
    # pgrep in a double-quoted command substitution runs.
    ('until [ "$(pgrep -fc cargo)" = 0 ]; do sleep 5; done', False, "deny"),
    ('while [ "`pgrep -f cargo`" ]; do sleep 5; done', False, "deny"),
    ('while pgrep --full cargo; do sleep 5; done', False, "deny"),
    # Only a `wait` command after the last job joins it.
    ('wait; cargo test &', False, "deny"),
    ('echo wait; cargo test &', False, "deny"),
    ('docker compose up --wait &', False, "deny"),
    ('wait-for-it.sh db:5432 &', False, "deny"),
    ('cargo build &\ncargo doc &\nwait', False, "pass"),
    ('if true; then cargo build & cargo doc & wait; fi', False, "pass"),
    # `<<` in a string or a shift opens no heredoc; a heredoc ends at its exact delimiter.
    ('git commit -m "doc: use <<EOF"\ncargo test &', False, "deny"),
    ('echo $((1<<2))\nsleep 1 &', False, "deny"),
    ("cat <<'EOF-1'\na & b\nEOF-1\nsleep 1 &", False, "deny"),
    ('cat <<EOF\na & b\n  EOF\nEOF\necho ok', False, "pass"),
    ('cat <<-EOF\n\ta & b\n\tEOF\necho ok', False, "pass"),
    ("cat <<'EOF-1'\na & b\nEOF-1", False, "pass"),
    # Escaped characters are text.
    ('echo a\\&b', False, "pass"),
    ('sed -e s/a/\\&/ f', False, "pass"),
    ("echo it\\'s; cargo test & echo it\\'s", False, "deny"),
    # A heredoc in a double-quoted $(...) is read as code: its body's quotes,
    # parentheses and backquotes are text.
    ('gh pr create --title t --body "$(cat <<\'EOF\'\nRuns "cargo test & wait" now.\nEOF\n)"', False, "pass"),
    ('git commit -m "$(cat <<\'EOF\'\nQuote " alone\nEOF\n)"\nsleep 100 &', False, "deny"),
    ('gh pr create --title t --body "$(cat <<\'EOF\'\n## Summary\n1) Run `make &` here :)\nEOF\n)"', False, "pass"),
    ('x="$(git log --format="%h & %s" -1)"', False, "pass"),
    ('x="$(echo "$(sleep 9 &)")"', False, "deny"),
    # Any pgrep -f / pkill -f, loop or not, needs a bracketed pattern;
    # options may take arguments.
    ('pkill -f quarz-server && echo done', False, "deny"),
    ('pkill -f quarz-server; cargo run -- --for x', False, "deny"),
    ('pgrep -u dev -f cargo; while true; do sleep 1; done', False, "deny"),
    ('for f in a b; do pgrep -f "$f"; done', False, "deny"),
    ('pgrep -f "[c]argo test"', False, "pass"),
    ("pkill -f '[q]uarz-server'; sleep 1", False, "pass"),
    ('pgrep -af [q]uarz', False, "pass"),
    ('until ! pgrep -f "[c]argo test" >/dev/null; do sleep 5; done', False, "pass"),
    ('pgrep -u dev -f "[c]argo"', False, "pass"),
    ('x="$(pgrep -fc "[c]argo")"', False, "pass"),
    ('x="$(pgrep -fc "cargo")"', False, "deny"),
    ('pgrep -x cargo; pidof cargo; pgrep cargo', False, "pass"),
    ('pgrep -f cargo 2>/dev/null', False, "deny"),
    ('pgrep -f "[c]argo" 2>/dev/null >x', False, "pass"),
    ('pgrep -f', False, "pass"),
    ("pgrep -f $'cargo'", False, "deny"),
    # The script of bash -c runs.
    ("timeout 300 bash -c 'until ! pgrep -f \"cargo test\"; do sleep 5; done'", False, "deny"),
    ('bash -c "while pgrep -f cargo; do sleep 1; done"', False, "deny"),
    ("sh -c 'sleep 9 &'", False, "deny"),
    ("bash -c 'echo a & b'", True, "pass"),
    ("bash -lc 'cargo build 2>&1 | tail'", False, "pass"),
    ('bash -c "cd $(pwd) && pgrep -f cargo"', False, "deny"),
    ('bash -c "sleep 9 & echo $(date)"', False, "deny"),
    ('bash -c "cd $(pwd) && cargo build 2>&1 | tail"', False, "pass"),
    ("bash -o pipefail -c 'pgrep -f cargo'", False, "deny"),
    ("bash -euo pipefail -c 'pgrep -f cargo'", False, "deny"),
    ("bash --norc -c 'pgrep -f cargo'", False, "deny"),
    ("bash -cx 'pgrep -f cargo'", False, "deny"),
    ("/bin/bash -c 'pgrep -f cargo'", False, "deny"),
    # Paths, options after the pattern, substitutions and escapes in it.
    ('/usr/bin/pgrep -f cargo', False, "deny"),
    ('/usr/bin/pkill -f "[q]uarz"', False, "pass"),
    ('pgrep -f "[c]argo" -u dev', False, "pass"),
    ('pkill -f "[q]uarz" --signal KILL', False, "pass"),
    ('pgrep -f "[c]argo" -d ,', False, "pass"),
    ('pgrep -f cargo -u \'[d]ev\'', False, "deny"),
    ('pgrep -d, -f cargo', False, "deny"),
    ('pgrep -d, -f \'[c]argo\'', False, "pass"),
    ('pgrep -f -u "$(whoami)" \'[c]argo\'', False, "pass"),
    ('pgrep -fu "$(id -un)" \'[c]argo\'', False, "pass"),
    ('pgrep -f -O 60 \'[c]argo\'', False, "pass"),
    ('pgrep -f -r R \'[c]argo\'', False, "pass"),
    ('pkill -STOP cargo -f', False, "deny"),
    ('pkill -STOP -f \'[c]argo\'', False, "pass"),
    ('python3 tools/pgrep.py -f x', False, "pass"),
    ('echo "$(pgrep -x cargo)" "$(tail -f log)"', False, "pass"),
    ('echo "pids: $(pgrep -x cargo)" ; echo "$(rm -f x)"', False, "pass"),
    ('[ -n "$(pgrep cargo)" ] || [ -n "$(pgrep -f \'[q]uarz\')" ]', False, "pass"),
    ('[ -n "$(pgrep cargo)" ] || [ -n "$(pgrep -f quarz)" ]', False, "deny"),
    ('pkill -f -LF /tmp/p \'[c]argo\'', False, "pass"),
    ('pkill -HUP -f \'[c]argo\'', False, "pass"),
    ('pkill "$(a "$(b)")" -f cargo', False, "deny"),
    ('pgrep -u "$(x "$(y)")" -f \'[c]argo\'', False, "pass"),
    ('echo "$(echo "$(pgrep -f cargo)")"', False, "deny"),
    ('bash -c "cd $(pwd) && echo \\"a & b\\""', False, "pass"),
    ('bash -c "cd $(pwd) && git commit -m \\"use pgrep -f cargo\\""', False, "pass"),
    ('bash -c "echo \\"a & b\\""', False, "pass"),
    ('bash -c "echo \\$(pgrep -f cargo)"', False, "deny"),
    ('bash -c "x=\\"$(date)\\"; pgrep -f cargo"', False, "deny"),
    ('pgrep -fu dev cargo', False, "deny"),
    ('pgrep -fu dev "[c]argo"', False, "pass"),
    ('pgrep -f "cargo $(whoami)"', False, "deny"),
    ('pgrep -f \\[c\\]argo', False, "pass"),
    ('sudo pkill -f x', False, "deny"),
    ('env LC_ALL=C pgrep -f cargo', False, "deny"),
    # A pgrep in a message is text.
    ('git commit -m "use pgrep -f cargo in a loop"', False, "pass"),
    ("echo 'pkill -f x'", False, "pass"),
    # ANSI-C quotes, arithmetic and partly quoted delimiters.
    ("echo $'it\\'s & x'", False, "pass"),
    ('echo $(( 5 & 3 ))', False, "pass"),
    ('cat <<E\'O\'F\nx\nEOF\nsleep 9 &', False, "deny"),
    # Expansions, arithmetic commands, case fall-through and `wait` in braces.
    ('echo ${x//&/and} ${x#*&}', False, "pass"),
    ('(( n & 1 )) && echo odd', False, "pass"),
    ('if (( n & 1 )); then echo odd; fi', False, "pass"),
    ('x=1; while (( x & 4 )); do break; done', False, "pass"),
    ('case $x in a) echo a ;& b) echo b ;;& c) echo c ;; esac', False, "pass"),
    ('sleep 1 & { wait; }', False, "pass"),
    ('cmd & time wait', False, "pass"),
    ('echo \\ #x &', False, "deny"),
    ('echo ${x} & echo y', False, "deny"),
]
bad = 0
# Input that is not a Bash call's object passes, silently.
RAWS = ['{"tool_name":"Bash","tool_input":{"command":"pgrep -f \\u00009\\u0000"}}', '{"tool_name":"Bash","tool_input":"x"}', '[1]', '{"tool_name":"Bash","tool_input":{"command":5}}', 'not json']
for raw in RAWS:
    run = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True)
    ok = run.returncode == 0 and not run.stdout and not run.stderr
    bad += not ok
    print(f"{'ok ' if ok else 'BAD'} pass raw {raw!r}")
for cmd, bg, want in CASES:
    inp = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd, "run_in_background": bg}})
    run = subprocess.run([sys.executable, HOOK], input=inp, capture_output=True, text=True)
    # A deny is a PreToolUse decision in JSON; a pass prints nothing. Either
    # way the hook exits 0 and writes no error.
    try:
        out = run.stdout.strip()
        got = json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "pass"
    except (ValueError, KeyError, TypeError):
        got = "bad output"
    if run.returncode != 0 or run.stderr:
        got = f"exit {run.returncode}: {run.stderr.strip()[-200:]}"
    ok = got == want
    bad += not ok
    print(f"{'ok ' if ok else 'BAD'} {want:4} bg={int(bg)} {cmd!r}" + ("" if ok else f" -> {got}"))
total = len(RAWS) + len(CASES)
print(f"{total - bad}/{total} as expected")
sys.exit(1 if bad else 0)
