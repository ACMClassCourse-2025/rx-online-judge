"""Docker boundary. No submitted process, shell, or archive runs on the host."""

import io
import socket
import tarfile
import threading
import time
from dataclasses import dataclass
from pathlib import PurePosixPath

import docker

from .archives import pack_files
from .config import Settings


class SandboxError(RuntimeError):
    pass


class ArtifactError(ValueError):
    pass


@dataclass
class Execution:
    code: int
    duration_ms: int
    log: str
    limit: str | None = None
    data: bytes = b""


class Sandbox:
    def __init__(
        self,
        client,
        settings: Settings,
        image: str,
        job_id: str,
        cancelled=lambda: False,
        runtime=False,
        network=False,
        network_name=None,
        environment=None,
    ):
        self.client = client
        self.settings = settings
        self.image = image
        self.job_id = job_id
        self.cancelled = cancelled
        self.runtime = runtime
        self.network = network
        self.network_name = network_name
        self.environment = environment or {}
        self.container = None

    def __enter__(self):
        memory = self.settings.runtime_memory_mb if self.runtime else self.settings.memory_mb
        # All writes go into bounded tmpfs mounts. There are no host bind mounts or volumes.
        self.container = self.client.containers.create(
            self.image,
            command=["/bin/sleep", "infinity"],
            entrypoint=[],
            user="1000:1000",
            working_dir="/workspace",
            read_only=True,
            network_disabled=not (self.network or self.network_name),
            network_mode=self.network_name or ("bridge" if self.network else "none"),
            # Git fetch containers need their own mapping to a proxy on the Docker host.
            extra_hosts=(
                {"host.docker.internal": "host-gateway"}
                if self.network and self.settings.git_proxy
                else None
            ),
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=64,
            mem_limit=f"{memory}m",
            memswap_limit=f"{memory}m",
            nano_cpus=1_000_000_000,
            ulimits=[
                docker.types.Ulimit(name="nofile", soft=256, hard=256),
                docker.types.Ulimit(name="fsize", soft=67108864, hard=67108864),
            ],
            tmpfs={
                "/workspace": (
                    f"rw,exec,nosuid,nodev,size={self.settings.workspace_mb}m,uid=1000,gid=1000"
                ),
                "/tmp": "rw,exec,nosuid,nodev,size=64m,mode=1777",
                "/case": "rw,noexec,nosuid,nodev,size=16m,uid=1000,gid=1000",
                "/output": "rw,noexec,nosuid,nodev,size=32m,uid=1000,gid=1000",
            },
            environment={
                "HOME": "/tmp",
                "TMPDIR": "/tmp",
                "CARGO_NET_OFFLINE": "true",
                "PYTHONDONTWRITEBYTECODE": "1",
                **self.environment,
            },
            labels={"rx-oj.managed": "true", "rx-oj.submission": self.job_id},
            runtime=self.settings.docker_runtime,
            log_config=docker.types.LogConfig(type="none"),
        )
        try:
            self.container.start()
        except BaseException:
            self.container.remove(force=True)
            raise
        return self

    def __exit__(self, *_):
        if self.container:
            try:
                self.container.remove(force=True)
            except docker.errors.NotFound:
                pass

    def put(self, path, archive):
        # Docker's archive endpoint refuses read-only root filesystems, including tmpfs.
        # Extract over an exec stdin stream, as the unprivileged sandbox user.
        exec_id = self.client.api.exec_create(
            self.container.id,
            ["tar", "--extract", "--file=-", "--no-same-owner", "--directory", path],
            stdin=True,
            user="1000:1000",
        )["Id"]
        stream = self.client.api.exec_start(exec_id, socket=True)
        try:
            raw = stream._sock
            raw.settimeout(30)
            raw.sendall(archive)
            raw.shutdown(socket.SHUT_WR)
            received = 0
            while chunk := raw.recv(65536):
                received += len(chunk)
                if received > self.settings.max_log_bytes:
                    raise SandboxError("Archive extraction produced excessive diagnostics")
        finally:
            stream.close()
        info = self.client.api.exec_inspect(exec_id)
        if info["Running"] or info["ExitCode"] != 0:
            raise SandboxError("Could not unpack compiler files in sandbox")

    def files(self, path, files):
        self.put(path, pack_files(files))

    def _archive(self, path, limit):
        file = PurePosixPath(path)
        command = ["tar", "--create", "--file=-", "--directory", str(file.parent), file.name]
        execution = self.execute(command, 30, capture=limit)
        if execution.limit or execution.code:
            raise ArtifactError(f"Artifact missing, invalid, or exceeds size limit: {path}")
        return execution.data

    def snapshot(self):
        # Archive is passed straight back to Docker, never extracted onto the host.
        execution = self.execute(
            ["tar", "-cf", "-", "-C", "/workspace", "."],
            30,
            capture=self.settings.max_snapshot_bytes,
        )
        if execution.limit or execution.code:
            raise ArtifactError("Built workspace exceeds the snapshot limit or is invalid")
        return execution.data

    def read_file(self, path, limit):
        data = self._archive(path, limit + 65536)
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            members = archive.getmembers()
            if len(members) != 1 or not members[0].isfile():
                raise ArtifactError(f"Artifact must be a regular file: {path}")
            if members[0].size > limit:
                raise ArtifactError(f"Artifact exceeds the size limit: {path}")
            return archive.extractfile(members[0]).read(limit + 1)

    def execute(self, command, timeout, capture=0, log_limit=None):
        started = time.monotonic()
        exec_id = self.client.api.exec_create(
            self.container.id, command, user="1000:1000", workdir="/workspace"
        )["Id"]
        captured = bytearray()
        data = bytearray()
        log_limit = self.settings.max_log_bytes if log_limit is None else log_limit
        output_limit = threading.Event()
        truncated_log = threading.Event()
        finished = threading.Event()
        errors = []

        def collect():
            try:
                for stdout, stderr in self.client.api.exec_start(exec_id, stream=True, demux=True):
                    if capture and stdout:
                        remaining = capture - len(data)
                        data.extend(stdout[: max(0, remaining)])
                        if len(stdout) > remaining:
                            output_limit.set()
                            return
                        stdout = None
                    for chunk in (stdout, stderr):
                        if chunk:
                            remaining = max(0, log_limit - len(captured))
                            captured.extend(chunk[:remaining])
                            if len(chunk) > remaining:
                                truncated_log.set()
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        thread = threading.Thread(target=collect, daemon=True)
        thread.start()
        limit = None
        while not finished.wait(0.05):
            if self.cancelled():
                limit = "cancelled"
                break
            if time.monotonic() - started >= timeout:
                limit = "time_limit"
                break
        if output_limit.is_set():
            limit = "output_limit"
        if limit:
            self.container.kill()
            thread.join(timeout=5)
            code = -1
        else:
            if errors:
                raise SandboxError("Docker lost the sandbox output stream") from errors[0]
            info = self.client.api.exec_inspect(exec_id)
            # The stream usually closes at process exit; inspect may lag briefly.
            while info["Running"] and time.monotonic() - started < timeout:
                time.sleep(0.01)
                info = self.client.api.exec_inspect(exec_id)
            if info["Running"]:
                self.container.kill()
                limit, code = "time_limit", -1
            else:
                code = info["ExitCode"]
        log = captured.decode(errors="replace")
        if truncated_log.is_set():
            log += f"\n[Output truncated after {log_limit} bytes.]"
        return Execution(
            code,
            round((time.monotonic() - started) * 1000),
            log,
            limit,
            bytes(data),
        )


def cleanup_job(client, submission_id):
    for container in client.containers.list(
        all=True, filters={"label": ["rx-oj.managed=true", f"rx-oj.submission={submission_id}"]}
    ):
        container.remove(force=True)
    for network in client.networks.list(
        filters={"label": ["rx-oj.managed=true", f"rx-oj.submission={submission_id}"]}
    ):
        network.remove()
