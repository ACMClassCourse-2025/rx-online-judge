#!/usr/bin/env python3
"""Create local Compose configuration, preserving any existing configuration."""

import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
socket = Path(os.getenv("OJ_DOCKER_SOCKET", "/var/run/docker.sock"))
destination = root / ".env"
if destination.exists():
    print(".env already exists; keeping its settings.")
else:
    group = socket.stat().st_gid if socket.exists() else 0
    with open(destination, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        stream.write(
            f"OJ_DOCKER_GID={group}\nOJ_DOCKER_SOCKET={socket}\nOJ_PORT=8000\n"
            "RX_TESTS_PATH=../rx-compiler/tests\nOJ_SECURE_COOKIES=0\n"
            "OJ_GIT_HOSTS=github.com,gitlab.com,codeberg.org,gitee.com\n"
        )
    print("Created .env (mode 0600). Provision accounts with python -m rx_oj.admin.")
