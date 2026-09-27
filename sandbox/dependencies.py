"""Package-manager adapter. Fetch runs behind the registry proxy; install runs offline."""

import os
import subprocess
import sys
from pathlib import Path

CACHE = Path("/workspace/.rx-oj-deps")


def main():
    phase, manager, directory = sys.argv[1:]
    os.chdir(Path("/workspace") / directory)
    CACHE.mkdir(exist_ok=True)
    if manager == "cargo":
        if phase == "install":
            return 0
        command = ["cargo", "fetch", "--locked"]
    elif manager == "pip":
        if phase == "fetch":
            command = [
                "python3",
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--dest",
                str(CACHE / "wheels"),
                "-r",
                "requirements.txt",
            ]
        else:
            subprocess.run(["python3", "-m", "venv", "/workspace/.venv"], check=True)
            command = [
                "/workspace/.venv/bin/python",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(CACHE / "wheels"),
                "--require-hashes",
                "--only-binary=:all:",
                "-r",
                "requirements.txt",
            ]
    elif manager == "npm":
        command = ["npm", "ci", "--no-audit", "--no-fund"]
        # All lifecycle scripts, including native addon builds, run only in the offline sandbox.
        command += ["--ignore-scripts"] if phase == "fetch" else ["--offline"]
    elif manager == "maven":
        if phase == "install":
            return 0
        command = [
            "mvn",
            "-B",
            "-ntp",
            "-s",
            "/opt/rx-oj/maven-settings.xml",
            "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline",
        ]
    else:
        raise ValueError("Unsupported dependency manager")
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
