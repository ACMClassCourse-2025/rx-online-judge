#!/usr/bin/env python3
"""Build the operator-owned images. Never builds an uploaded Dockerfile."""

import argparse
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument(
    "--languages",
    nargs="+",
    default=["cpp", "rust", "python", "java", "node"],
    choices=["cpp", "rust", "python", "java", "node"],
)
args = parser.parse_args()
subprocess.run(
    ["docker", "build", "-f", "docker/git.Dockerfile", "-t", "rx-oj-git:local", "."],
    cwd=root,
    check=True,
)
if not (root.parent / "rx-compiler/vendor/REIMU/src/main.cpp").exists():
    parser.error("Initialize rx-compiler's REIMU submodule first (see README.md)")
for language in args.languages:
    subprocess.run(
        [
            "docker",
            "build",
            "-f",
            "docker/languages.Dockerfile",
            "--target",
            language,
            "-t",
            f"rx-oj-{language}:local",
            ".",
        ],
        cwd=root,
        check=True,
    )
subprocess.run(
    [
        "docker",
        "build",
        "-f",
        "rx-online-judge/docker/reimu.Dockerfile",
        "-t",
        "rx-oj-reimu:local",
        ".",
    ],
    cwd=root.parent,
    check=True,
)
