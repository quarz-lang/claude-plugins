#!/usr/bin/env python3
"""PreToolUse guard for Bash (the long-jobs plugin; see its long-jobs skill).

Denies two waiting mistakes that recur across sessions:
1. `pgrep -f` / `pkill -f` whose pattern does not start with a bracket
   (`[c]argo test`): the Bash tool runs each call in a shell whose
   command line holds the call, so a plain pattern always matches that
   shell (a check says "running" forever, a `pkill -f` kills the call).
   Inside `bash -c '...'` (and `sh`, `zsh`, `dash`) too.
2. Backgrounding with a lone `&` when the call is not run with
   run_in_background and no `wait` command follows the last job: the
   job detaches, no completion notice comes, and its exit status is
   lost.
Anything else passes. On a parse problem the hook lets the call through.
"""
import json
import re
import sys


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{reason} See the long-jobs skill.",
        }
    }))
    sys.exit(0)


# `<<WORD`, `<<-'WORD'`, `<<E"O"F`...: the delimiter as a shell word.
HEREDOC = re.compile(r"<<(-?)[ \t]*((?:'[^'\n]*'|\"[^\"\n]*\"|\\.|[^\s;&|<>()'\"\\])+)")


class Scanner:
    """Reads a command as the shell does, keeping the code that runs and
    dropping the text that does not: quoted strings (but the command
    substitutions inside double quotes), backslash-escaped characters,
    comments, heredoc bodies and arithmetic `$((...))`. A command
    substitution is read with the same rules up to its own `)`, so that
    quotes, parentheses or a heredoc inside it do not end the string
    around it."""

    def __init__(self, cmd: str, quoted: list = None) -> None:
        self.s, self.i, self.n = cmd, 0, len(cmd)
        # The quoted strings' texts, which the code shows as `\0N\0`.
        self.quoted = [] if quoted is None else quoted

    @staticmethod
    def script_of_shell(out: list) -> bool:
        """Whether what was read so far ends with `bash -c` (`sh`, `zsh`,
        `dash`, a path to one, options before `-c`), so that the string
        that follows is a script that runs."""
        return re.search(
            r"(?:(?<![\w./-])|(?<=/))(?:ba|z|da)?sh\s+"
            r"(?:(?:[-+]\w*o\s+\S+|--[\w-]+|[-+]\w+)\s+)*-\w*c\w*\s*$",
            "".join(out[-60:]),
        ) is not None

    def mark(self, text: str, out: list, double: bool = False) -> str:
        """A quoted string's mark in the code: its text when it is the
        script of `bash -c` (which runs), else `\0N\0` for `self.quoted[N]`.
        (`double`: the text of a double-quoted string, in which the shell
        turns a backslash before a double quote, a backslash, a dollar or
        a backquote into that character.)"""
        if self.script_of_shell(out):
            script = re.sub(r'\\([\\"$`])', r"\1", text) if double else text
            return " " + Scanner(script, self.quoted).code() + " "
        self.quoted.append(text)
        return f"\0{len(self.quoted) - 1}\0"

    def at(self, text: str) -> bool:
        return self.s.startswith(text, self.i)

    def code(self, closer: bool = False) -> str:
        """Code up to the end, or (closer) up to the `)` that closes a
        `$(` or `(` already read."""
        out, pending, depth, s = [], [], 0, self.s
        while self.i < self.n:
            c = s[self.i]
            if c == "\n":
                out.append(c)
                self.i += 1
                self.bodies(pending)
                pending = []
            elif c == "\\":
                # (An escaped letter or bracket is that character; other
                # escaped characters, `\&` or `\;`, are not operators.)
                nxt = s[self.i + 1:self.i + 2]
                if nxt.isalnum() or nxt in "[]":
                    out.append(nxt)
                self.i += 2
            elif self.at("$'"):
                # ANSI-C quoting: backslash escapes inside.
                start = self.i = self.i + 2
                while self.i < self.n and s[self.i] != "'":
                    self.i += 2 if s[self.i] == "\\" else 1
                out.append(self.mark(s[start:self.i], out))
                self.i += 1
            elif c == "'":
                j = s.find("'", self.i + 1)
                j = self.n if j < 0 else j
                out.append(self.mark(s[self.i + 1:j], out))
                self.i = j + 1
            elif c == '"':
                self.i += 1
                start = self.i
                subs = self.double_quoted()
                # (A shell's script is read as code; else a string with
                # substitutions shows their code, a plain one its mark.)
                if subs and not self.script_of_shell(out):
                    # (Between \x02 and \x03, not quotes: an opening and a
                    # closing one differ.)
                    out.append("\x02" + subs + "\x03")
                else:
                    out.append(self.mark(s[start:self.i - 1], out, double=True))
            elif c == "`":
                self.i += 1
                out.append(" " + self.backquoted() + " ")
            elif self.at("$((") or (self.at("((") and self.command_position(out)):
                self.arithmetic()
                out.append("0")
            elif self.at("${"):
                self.expansion()
                out.append("$x")
            elif self.at("$("):
                self.i += 2
                out.append(" " + self.code(closer=True) + " ")
            elif c == "#" and (self.i == 0 or (s[self.i - 1] in " \t\n;&|(" and s[self.i - 2:self.i - 1] != "\\")):
                j = s.find("\n", self.i)
                self.i = self.n if j < 0 else j
            elif self.at("<<<"):
                out.append("<<<")
                self.i += 3
            elif self.at("<<"):
                m = HEREDOC.match(s, self.i)
                word = re.sub(r"\\(.)|['\"]", r"\1", m.group(2)) if m else ""
                # (A delimiter starting with a digit is a shift: `1<<2`.)
                if m and not word[:1].isdigit():
                    pending.append((word, bool(m.group(1))))
                    out.append("<< ")
                    self.i = m.end()
                else:
                    out.append("<<")
                    self.i += 2
            elif closer and c == "(":
                depth += 1
                out.append(c)
                self.i += 1
            elif closer and c == ")":
                self.i += 1
                if depth == 0:
                    break
                depth -= 1
                out.append(c)
            else:
                out.append(c)
                self.i += 1
        return "".join(out)

    def bodies(self, pending: list) -> None:
        """Skips the bodies of the heredocs a line opened, each up to its
        delimiter alone on a line (tabs stripped for `<<-`)."""
        s = self.s
        for word, dash in pending:
            while self.i < self.n:
                j = s.find("\n", self.i)
                line = s[self.i:] if j < 0 else s[self.i:j]
                self.i = self.n if j < 0 else j + 1
                if (line.lstrip("\t") if dash else line) == word:
                    break

    def double_quoted(self) -> str:
        """The command substitutions of a double-quoted string whose `"` was
        read, up to its closing `"`."""
        subs, s = [], self.s
        while self.i < self.n and s[self.i] != '"':
            if s[self.i] == "\\":
                self.i += 2
            elif self.at("$(("):
                self.arithmetic()
            elif self.at("$("):
                self.i += 2
                subs.append(self.code(closer=True))
            elif s[self.i] == "`":
                self.i += 1
                subs.append(self.backquoted())
            else:
                self.i += 1
        self.i += 1
        return "; ".join(subs)

    def backquoted(self) -> str:
        """The code of a backquoted substitution whose opening ` was read."""
        s, j = self.s, self.i
        while j < self.n and s[j] != "`":
            j += 2 if s[j] == "\\" else 1
        inner = s[self.i:j]
        self.i = j + 1
        return Scanner(inner, self.quoted).code()

    @staticmethod
    def command_position(out: list) -> bool:
        """Whether what was read so far ends where a command starts."""
        before = "".join(out[-8:]).rstrip(" \t")
        return (before == "" or before[-1] in ";&|(!{\n"
                or re.search(r"\b(?:do|then|else|if|elif|while|until)$", before) is not None)

    def expansion(self) -> None:
        """Skips `${...}` (its nested braces too)."""
        depth, self.i = 1, self.i + 2
        while self.i < self.n and depth:
            c = self.s[self.i]
            if c == "\\":
                self.i += 1
            else:
                depth += {"{": 1, "}": -1}.get(c, 0)
            self.i += 1

    def arithmetic(self) -> None:
        """Skips `$((...))` or an arithmetic command `((...))`."""
        depth = 2
        self.i += 3 if self.s[self.i] == "$" else 2
        while self.i < self.n and depth:
            depth += {"(": 1, ")": -1}.get(self.s[self.i], 0)
            self.i += 1


def strip_quoted(cmd: str) -> tuple:
    """The command without the text that does not run (see `Scanner`), so
    that a commit message or a script's text does not count, and the
    quoted strings its `\0N\0` marks stand for."""
    sc = Scanner(cmd)
    return sc.code(), sc.quoted


# The options of pgrep/pkill that take an argument (short, and long when
# written apart from it).
ARG_SHORT = set("dgGPstuUFOrq")
# The short options' letters (`-LF` is two options, `-STOP` a signal).
OPTION_LETTERS = set("acdefgilnoqrstuvwxAFGLOPU")
ARG_LONG = {"--delimiter", "--pgroup", "--group", "--parent", "--session",
            "--terminal", "--euid", "--uid", "--pidfile", "--ns", "--nslist",
            "--signal", "--runstates", "--env", "--cgroup", "--older", "--queue"}


def pattern_of(words: list) -> str:
    """The pattern operand among pgrep's arguments: the first word that is
    neither an option nor an option's argument ('' when none)."""
    i = 0
    while i < len(words):
        w = words[i]
        if w == "--":
            return words[i + 1] if i + 1 < len(words) else ""
        if w.startswith("--"):
            i += 2 if w in ARG_LONG else 1
        elif re.fullmatch(r"-(?:[A-Z]{2,}\d*|\d+)", w) and not set(w[1:]) <= OPTION_LETTERS:
            # (A signal: `-9`, `-KILL`, `-STOP`.)
            i += 1
        elif w.startswith("-") and len(w) > 1:
            # (`-u dev`; `-udev` and `-d,` carry their argument.)
            letters = w[1:]
            takes = next((k for k, ch in enumerate(letters) if ch in ARG_SHORT), None)
            i += 2 if takes is not None and takes == len(letters) - 1 else 1
        else:
            return w
    return ""


def arguments(code: str, i: int) -> str:
    """The arguments of the command whose name ends at `i`: up to the
    end of the command or the first redirection, with each double-quoted
    string holding substitutions (`\x02...\x03`, nested or not) as one
    unknown word, `\x01`."""
    out, depth = [], 0
    while i < len(code):
        c = code[i]
        if c == "\x02":
            if depth == 0:
                out.append("\x01")
            depth += 1
        elif c == "\x03":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0:
            if c in ";&|\n)<>":
                break
            out.append(c)
        i += 1
    return "".join(out)


def unbracketed_full_match(code: str, quoted: list) -> bool:
    """Whether a `pgrep`/`pkill` matches full command lines (`-f`,
    `--full`) with a pattern that does not start with `[x]`."""
    for m in re.finditer(r"(?:(?<![\w./-])|(?<=/))p(?:grep|kill)(?![\w.-])", code):
        # (Without the file descriptor of a redirection: `2>`.)
        words = re.sub(r"(?<=\s)\d+$", "", arguments(code, m.end())).split()
        if not any(re.match(r"-[A-Za-z]*f", w) or w == "--full" for w in words):
            continue
        operand = pattern_of(words)
        if not operand:
            continue
        pattern = re.sub(r"\0(\d+)\0", lambda q: quoted[int(q.group(1))], operand)
        if not re.match(r"\[[^\]]+\]", pattern):
            return True
    return False


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(data, dict) or data.get("tool_name") != "Bash":
        return
    ti = data.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str):
        return
    try:
        code, quoted = strip_quoted(cmd)
        plain_full_match = unbracketed_full_match(code, quoted)
    except Exception:
        return

    if plain_full_match:
        deny(
            "This command runs `pgrep -f`/`pkill -f` with a plain pattern. The Bash "
            "tool runs each call in a shell whose command line holds the call, so "
            "the pattern always matches that shell: a check always says running, "
            "a `pkill -f` kills this call. Put the first letter of the "
            "pattern in brackets (`pgrep -f \"[c]argo test\"`), with no plain "
            "mention of the name elsewhere in the call, or use `pgrep -x NAME` / "
            "`pidof`; to wait, start the job with run_in_background or wait on its "
            "PID (`tail --pid=PID -f /dev/null`)."
        )

    if not ti.get("run_in_background"):
        # A lone `&` (not `&&`, `>&`, `&>`, `<&`, `|&`): a job sent to the
        # background, whatever follows it.
        jobs = [m.start() for m in re.finditer(r"(?<![&>|<;])&(?![&>])", code)]
        # (Parallel jobs joined by a `wait` command after the last of them
        # block the call, and their status is known: not the detached case.)
        waits = [m.end() for m in re.finditer(
            r"(?:^|[;&|({\n]|\b(?:then|do|else|if|time))[ \t!]*wait(?=[ \t;&|)}\n]|$)", code)]
        if jobs and not (waits and waits[-1] > jobs[-1]):
            deny(
                "This command backgrounds a job with `&` outside run_in_background: "
                "no completion notice comes and the exit status is lost. Run the "
                "long command itself with run_in_background: true and record "
                '`echo "exit=$?"` after it.'
            )


if __name__ == "__main__":
    main()
