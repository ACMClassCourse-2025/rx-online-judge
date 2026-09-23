"""Untrusted-side adapter: preserve real exit codes (Make maps rejection to 2)."""

import json
import os
import re
import shlex
import subprocess
import sys


def main():
    stage = sys.argv[1]
    resolved = subprocess.run(
        ["make", "--no-print-directory", "-s", "-f", "/opt/rx-oj/commands.mk", "rx-oj-commands"],
        capture_output=True,
        text=True,
        check=False,
    )
    if resolved.returncode:
        sys.stderr.write(resolved.stderr)
        return 125
    try:
        command = json.loads(resolved.stdout)[stage]
    except (ValueError, KeyError):
        sys.stderr.write("config.mk must not print text while resolving commands.\n")
        return 125
    if not command.strip():
        if stage == "build":
            return 0
        sys.stderr.write(f"config.mk must define {stage.upper()}.\n")
        return 125
    paths = {
        "source": "/case/input.rx",
        "output": "/output/program.ll" if stage == "ir" else "/output/program.s",
        "runtime": "/output/runtime.s",
    }
    command = re.sub(r"\{(source|output|runtime)\}", lambda m: shlex.quote(paths[m[1]]), command)
    # exec replaces this adapter so Docker sees the compiler's exit status, including 1.
    os.execv("/bin/sh", ["sh", "-c", command])


if __name__ == "__main__":
    sys.exit(main())
