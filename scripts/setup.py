#!/usr/bin/env python3
"""Configure Compose for this host while preserving unrelated settings."""

import argparse
import os
import shlex
import stat
from pathlib import Path


def assignment(line):
    key, separator, value = line.partition("=")
    key = key.strip().removeprefix("export ").strip()
    if not separator or key not in {"OJ_DOCKER_SOCKET", "OJ_DOCKER_GID", "RX_TESTS_PATH"}:
        return None, None
    return key, " ".join(shlex.split(value, comments=True))


def configure(root, *, require_docker=False):
    destination = root / ".env"
    exists = destination.exists()
    previous = destination.read_text() if exists else ""
    lines = previous.splitlines(keepends=True)
    settings = dict(assignment(line) for line in lines)
    socket_value = (
        os.getenv("OJ_DOCKER_SOCKET") or settings.get("OJ_DOCKER_SOCKET") or "/var/run/docker.sock"
    )
    socket = Path(os.path.expandvars(socket_value)).expanduser()
    if not socket.is_absolute():
        socket = root / socket
    updates = {"OJ_DOCKER_SOCKET": str(socket)}
    try:
        info = socket.stat()
    except OSError as exc:
        if require_docker:
            raise ValueError(
                f"Cannot access Docker socket {socket}: {exc.strerror}. "
                "Start Docker or set OJ_DOCKER_SOCKET to its Unix socket path."
            ) from exc
        print(
            f"Docker socket {socket} unavailable; "
            "make up will detect its group when Docker is ready."
        )
    else:
        if not stat.S_ISSOCK(info.st_mode):
            raise ValueError(f"OJ_DOCKER_SOCKET must point to a Unix socket: {socket}")
        # An exported override is explicit; a saved .env GID may belong to another host.
        updates["OJ_DOCKER_GID"] = os.getenv("OJ_DOCKER_GID") or str(info.st_gid)

    if not exists:
        updates.update(
            OJ_PORT="8000",
            RX_TESTS_PATH="./testcases",
            OJ_SECURE_COOKIES="0",
            OJ_GIT_HOSTS="github.com,gitlab.com,codeberg.org,gitee.com",
        )
    elif settings.get("RX_TESTS_PATH") == "../rx-compiler/tests":
        updates["RX_TESTS_PATH"] = "./testcases"

    seen = set()
    for index, line in enumerate(lines):
        key, value = assignment(line)
        if key in updates:
            seen.add(key)
            if value != updates[key]:
                lines[index] = f"{key}={updates[key]}\n"
    for key, value in updates.items():
        if key not in seen:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"{key}={value}\n")
    updated = "".join(lines)
    if not exists:
        with open(
            destination, "x", opener=lambda path, flags: os.open(path, flags, 0o600)
        ) as stream:
            stream.write(updated)
        print("Created .env (mode 0600). Provision accounts with python -m rx_oj.admin.")
    elif updated != previous:
        destination.write_text(updated)
        print("Updated .env for this host; kept unrelated settings and custom testcase paths.")
    else:
        print(".env settings already match this host.")
    if "OJ_DOCKER_GID" in updates:
        print(f"Docker socket: {socket}; worker supplementary GID: {updates['OJ_DOCKER_GID']}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-docker", action="store_true", help="Fail if the Docker socket is unavailable"
    )
    args = parser.parse_args()
    try:
        configure(Path(__file__).resolve().parent.parent, require_docker=args.require_docker)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Setup failed: {exc}\n")


if __name__ == "__main__":
    main()
