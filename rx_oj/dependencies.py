"""Prepare locked dependencies before building; only registry downloads have networking."""

import hashlib
import io
import ipaddress
import json
import logging
import posixpath
import tarfile
import time
import tomllib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import docker

from .dependency_cache import DependencyCache
from .sandbox import ArtifactError, Sandbox

log = logging.getLogger(__name__)
CACHE_DIRECTORY = ".rx-oj-deps"
MANAGERS = {
    "rust": ("cargo", "Cargo.toml", "Cargo.lock"),
    "python": ("pip", "requirements.txt", "requirements.txt"),
    "node": ("npm", "package.json", "package-lock.json"),
    "java": ("maven", "pom.xml", "pom.xml"),
}


class DependencyError(ValueError):
    def __init__(self, message, cancelled=False):
        super().__init__(message)
        self.cancelled = cancelled


@dataclass(frozen=True)
class DependencyPlan:
    manager: str
    directory: str
    fingerprint: str


@dataclass(frozen=True)
class PreparedDependencies:
    plan: DependencyPlan
    archive: bytes
    log: str


def dependency_plan(source, language):
    if language not in MANAGERS:
        return None
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
        files = {member.name: member for member in archive if member.isfile()}
        config = {}
        if ".rx-oj.toml" in files:
            try:
                config = tomllib.loads(archive.extractfile(files[".rx-oj.toml"]).read().decode())
                config = config.get("dependencies", {})
                if not isinstance(config, dict) or set(config) - {"enabled", "directory"}:
                    raise ValueError("Unknown dependency settings")
                if type(config.get("enabled", True)) is not bool:
                    raise ValueError("enabled must be a boolean")
            except (ValueError, UnicodeError) as exc:
                raise DependencyError(f"Invalid .rx-oj.toml: {exc}") from exc
        if not config.get("enabled", True):
            return None
        directory = config.get("directory", ".")
        if (
            not isinstance(directory, str)
            or not directory
            or len(directory) > 200
            or PurePosixPath(directory).is_absolute()
            or ".." in PurePosixPath(directory).parts
            or "\\" in directory
            or any(ord(c) < 32 for c in directory)
        ):
            raise DependencyError(
                "Dependency directory must be a relative path inside the repository"
            )
        directory = str(PurePosixPath(directory))
        manager, manifest, lock = MANAGERS[language]
        manifest = str(PurePosixPath(directory) / manifest)
        lock = str(PurePosixPath(directory) / lock)
        if manifest not in files:
            if "directory" in config:
                raise DependencyError(f"Dependency manifest not found: {manifest}")
            return None
        if any(PurePosixPath(name).parts[0] == CACHE_DIRECTORY for name in files):
            raise DependencyError(f"{CACHE_DIRECTORY} is reserved for judge-managed dependencies")
        if lock not in files:
            raise DependencyError(
                f"Commit {lock} so dependency versions are locked before submitting"
            )
        digest = hashlib.sha256()
        for name, member in sorted(files.items()):
            path = PurePosixPath(name)
            # Maven configuration/plugins can consult arbitrary project files. Other adapters
            # reuse downloads across source-only changes, including all workspace manifests.
            if (
                manager == "maven"
                or name == ".rx-oj.toml"
                or path.name
                in {"Cargo.toml", "Cargo.lock", "package.json", "package-lock.json", ".npmrc"}
                or ".cargo" in path.parts
                or (manager == "pip" and path.suffix in {".txt", ".in", ".toml", ".cfg"})
            ):
                content = archive.extractfile(member).read()
                digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
        return DependencyPlan(manager, directory, digest.hexdigest())


def dependency_environment(manager, online=False):
    root = "/workspace/" + CACHE_DIRECTORY
    env = {
        "CARGO_HOME": root + "/cargo",
        "CARGO_NET_OFFLINE": "false" if online else "true",
        "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse",
        "PIP_CONFIG_FILE": "/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_INDEX_URL": "https://pypi.org/simple",
        "PIP_NO_INDEX": "0" if online else "1",
        "npm_config_cache": root + "/npm",
        "npm_config_offline": "false" if online else "true",
        "MAVEN_OPTS": "-Dmaven.repo.local=" + root + "/maven",
        "MAVEN_ARGS": "" if online else "-o -s /opt/rx-oj/maven-settings.xml",
    }
    if online:
        proxy = "http://dependency-proxy:3128"
        env.update(
            HTTP_PROXY=proxy,
            HTTPS_PROXY=proxy,
            http_proxy=proxy,
            https_proxy=proxy,
            CARGO_HTTP_PROXY=proxy,
        )
    return env


def validate_dependency_archive(data):
    """Only cache-directory members and links within it may enter the offline workspace."""
    paths, links = set(), set()
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            for index, member in enumerate(archive):
                path = PurePosixPath(member.name)
                if (
                    index >= 100000
                    or path.is_absolute()
                    or ".." in path.parts
                    or not path.parts
                    or path.parts[0] != CACHE_DIRECTORY
                    or "\\" in member.name
                    or path in paths
                ):
                    raise ValueError("Unsafe dependency cache path")
                paths.add(path)
                if member.issym() or member.islnk():
                    target = member.linkname
                    resolved = PurePosixPath(
                        posixpath.normpath(str(path.parent / target) if member.issym() else target)
                    )
                    if (
                        PurePosixPath(target).is_absolute()
                        or "\\" in target
                        or not resolved.parts
                        or resolved.parts[0] != CACHE_DIRECTORY
                        or path == PurePosixPath(CACHE_DIRECTORY)
                    ):
                        raise ValueError("Dependency cache link escapes its directory")
                    links.add(path)
                elif not member.isfile() and not member.isdir():
                    raise ValueError("Special files are not allowed in the dependency cache")
        if any(parent in links for path in paths for parent in path.parents):
            raise ValueError("Dependency cache contains files under a link")
    except (tarfile.TarError, ValueError) as exc:
        raise DependencyError(f"Invalid dependency cache: {exc}") from exc


@contextmanager
def dependency_network(client, settings, image, job_id):
    if settings.dependency_proxy:
        proxy = urlsplit(settings.dependency_proxy)
        if proxy.scheme not in {"http", "https"} or not proxy.hostname:
            raise DependencyError("OJ_DEPENDENCY_PROXY must be an HTTP or HTTPS proxy URL")
    labels = {"rx-oj.managed": "true", "rx-oj.submission": job_id}
    network = client.networks.create(
        "rx-oj-deps-" + uuid.uuid4().hex,
        driver="bridge",
        internal=True,
        labels=labels,
        # No host address on this bridge: preparation cannot reach host services via its gateway.
        options={"com.docker.network.bridge.inhibit_ipv4": "true"},
    )
    proxy_container = None
    try:
        network.reload()
        subnet = ipaddress.ip_network(network.attrs["IPAM"]["Config"][0]["Subnet"])
        bind = str(subnet.network_address + 2)
        proxy_container = client.containers.create(
            image,
            command=["python3", "/opt/rx-oj/dependency_proxy.py"],
            entrypoint=[],
            user="1000:1000",
            read_only=True,
            network_mode="bridge",
            environment={
                "OJ_DEPENDENCY_BIND": bind,
                "OJ_DEPENDENCY_HOSTS": json.dumps(settings.dependency_hosts),
                "OJ_DEPENDENCY_PROXY": settings.dependency_proxy,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            extra_hosts={"host.docker.internal": "host-gateway"}
            if settings.dependency_proxy
            else None,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=48,
            mem_limit="96m",
            memswap_limit="96m",
            nano_cpus=500_000_000,
            ulimits=[docker.types.Ulimit(name="nofile", soft=256, hard=256)],
            labels=labels,
            log_config=docker.types.LogConfig(type="none"),
        )
        network.connect(proxy_container, ipv4_address=bind, aliases=["dependency-proxy"])
        proxy_container.start()
        yield network.name
    finally:
        if proxy_container is not None:
            proxy_container.remove(force=True)
        network.remove()


def prepare_dependencies(client, settings, job, image, source, plan, cancelled, deadline):
    if cancelled():
        raise DependencyError("Dependency preparation cancelled", cancelled=True)
    key = hashlib.sha256(
        json.dumps(
            {
                "version": 1,
                "owner": job.get("owner_id") or job["id"],
                "repository": job.get("repository_url", ""),
                "image": image,
                "manager": plan.manager,
                "directory": plan.directory,
                "files": plan.fingerprint,
                "hosts": sorted(settings.dependency_hosts),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cache = DependencyCache(settings)
    try:
        data = cache.get(key)
    except OSError:
        log.exception("Could not read dependency cache")
        data = None
    if data is not None:
        validate_dependency_archive(data)
        return PreparedDependencies(plan, data, f"Dependencies ({plan.manager}): cache hit.\n")
    deadline = min(deadline, time.monotonic() + settings.dependency_timeout)
    with dependency_network(client, settings, image, job["id"]) as network:
        with Sandbox(
            client,
            settings,
            image,
            job["id"],
            cancelled,
            network_name=network,
            environment=dependency_environment(plan.manager, online=True),
        ) as box:
            box.put("/workspace", source)
            execution = box.execute(
                ["python3", "/opt/rx-oj/dependencies.py", "fetch", plan.manager, plan.directory],
                max(0.01, deadline - time.monotonic()),
            )
            if execution.code or execution.limit:
                raise DependencyError(
                    f"Dependency preparation failed ({execution.limit or execution.code}).\n"
                    + execution.log,
                    cancelled=execution.limit == "cancelled",
                )
            try:
                data = box._archive(
                    "/workspace/" + CACHE_DIRECTORY, settings.dependency_entry_mb * 1024 * 1024
                )
            except ArtifactError as exc:
                raise DependencyError(
                    "Dependencies exceed the cache entry limit or could not be archived"
                ) from exc
    validate_dependency_archive(data)
    try:
        cache.put(key, data)
    except OSError:
        log.exception("Could not save dependency cache")
    return PreparedDependencies(
        plan, data, f"Dependencies ({plan.manager}): downloaded.\n" + execution.log
    )
