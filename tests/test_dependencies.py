import hashlib
import io
import os
import socket
import tarfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from unittest.mock import Mock

import pytest

from rx_oj.archives import pack_files
from rx_oj.dependencies import (
    DependencyError,
    dependency_plan,
    prepare_dependencies,
    validate_dependency_archive,
)
from rx_oj.dependency_cache import DependencyCache
from sandbox.dependency_proxy import Server, public_addresses


def cargo_source(**extra):
    return pack_files(
        {
            "Cargo.toml": b'[package]\nname="compiler"\nversion="0.1.0"\n',
            "Cargo.lock": b"version=4\n",
            "src/main.rs": b"fn main() {}",
            **extra,
        }
    )


def test_plans_respect_manifests_lockfiles_and_nested_projects():
    assert dependency_plan(pack_files({"config.mk": b""}), "rust") is None
    assert dependency_plan(pack_files({"Cargo.toml": b""}), "cpp") is None
    with pytest.raises(DependencyError, match="Cargo.lock"):
        dependency_plan(pack_files({"Cargo.toml": b""}), "rust")
    assert (
        dependency_plan(
            pack_files({".rx-oj.toml": b"[dependencies]\nenabled=false", "Cargo.toml": b""}), "rust"
        )
        is None
    )
    nested = pack_files(
        {
            ".rx-oj.toml": b'[dependencies]\ndirectory="compiler"',
            "compiler/Cargo.toml": b"",
            "compiler/Cargo.lock": b"",
        }
    )
    plan = dependency_plan(nested, "rust")
    assert plan.manager == "cargo" and plan.directory == "compiler"
    for config in (
        b'[dependencies]\ndirectory="../escape"',
        b'[dependencies]\ndirectory="/tmp"',
        b'[dependencies]\nenabled="yes"',
        b'[dependencies]\ncommand="curl"',
    ):
        with pytest.raises(DependencyError):
            dependency_plan(pack_files({".rx-oj.toml": config}), "rust")
    for language, manifest, lock, manager in (
        ("python", "requirements.txt", "requirements.txt", "pip"),
        ("node", "package.json", "package-lock.json", "npm"),
        ("java", "pom.xml", "pom.xml", "maven"),
    ):
        assert dependency_plan(pack_files({manifest: b"", lock: b""}), language).manager == manager


def test_fingerprints_reuse_source_changes_but_invalidate_dependency_configuration():
    original = dependency_plan(cargo_source(), "rust").fingerprint
    assert (
        dependency_plan(
            cargo_source(**{"src/main.rs": b'fn main() { println!("new"); }'}), "rust"
        ).fingerprint
        == original
    )
    for changed in (
        {"Cargo.lock": b"new"},
        {".cargo/config.toml": b"[net]\nretry=1"},
        {"member/Cargo.toml": b"new"},
    ):
        assert dependency_plan(cargo_source(**changed), "rust").fingerprint != original
    first = dependency_plan(pack_files({"pom.xml": b"pom", "Main.java": b"old"}), "java")
    second = dependency_plan(pack_files({"pom.xml": b"pom", "Main.java": b"new"}), "java")
    assert first.fingerprint != second.fingerprint


def test_cache_hit_is_scoped_to_account_repository_image_and_policy(settings, monkeypatch):
    source = cargo_source()
    plan = dependency_plan(source, "rust")
    archive = pack_files({".rx-oj-deps/cargo/a": b"downloaded crate"})
    job = {"id": "run", "owner_id": "alice", "repository_url": "https://github.com/alice/compiler"}
    cache = Mock()
    cache.get.return_value = archive
    monkeypatch.setattr("rx_oj.dependencies.DependencyCache", lambda _: cache)
    docker = Mock()
    keys = []
    for changes, image, policy in (
        ({}, "image1", settings),
        ({"id": "again"}, "image1", settings),
        ({"owner_id": "bob"}, "image1", settings),
        ({"repository_url": "another"}, "image1", settings),
        ({}, "image2", settings),
        ({}, "image1", replace(settings, dependency_hosts=("other.org",))),
    ):
        result = prepare_dependencies(
            docker,
            policy,
            {**job, **changes},
            image,
            source,
            plan,
            lambda: False,
            time.monotonic() + 10,
        )
        assert result.archive == archive and "cache hit" in result.log
        keys.append(cache.get.call_args.args[0])
    assert keys[0] == keys[1] and len(set(keys)) == 5
    assert not docker.mock_calls  # Repeated submissions don't need a network container.


def key(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cache_writer(settings, value):
    cache = DependencyCache(settings)
    cache.put(key(value), value.encode() * 100000)
    return cache.get(key(value))


def test_cache_eviction_expiration_corruption_and_concurrent_writers(settings):
    settings = replace(settings, dependency_cache_mb=1, dependency_entry_mb=1)
    cache = DependencyCache(settings)
    cache.put(key("a"), b"a" * 600000)
    cache.put(key("b"), b"b" * 600000)
    assert cache.get(key("a")) is None
    assert cache.get(key("b")) == b"b" * 600000
    cache.path(key("b")).write_bytes(b"corrupt")
    assert cache.get(key("b")) is None
    cache.put(key("a"), b"data")
    os.utime(cache.path(key("a")), (0, 0))
    assert cache.get(key("a")) is None
    cache.put(key("oversize"), b"x" * (1024 * 1024 + 1))
    assert cache.get(key("oversize")) is None
    with ProcessPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(cache_writer, [settings] * 3, ["x", "y", "z"]))
    assert results == [value.encode() * 100000 for value in ["x", "y", "z"]]
    assert sum(path.stat().st_size for path in cache.directory.glob("*.cache")) <= 1024 * 1024
    disabled = DependencyCache(replace(settings, dependency_cache_mb=0))
    assert disabled.get(key("x")) is None


@pytest.mark.parametrize(
    "path", ["../escape", "/workspace/evil", "config.mk", ".rx-oj-deps/../../config.mk"]
)
def test_cache_cannot_overwrite_submission_source(path):
    with pytest.raises(DependencyError):
        validate_dependency_archive(pack_files({path: b"bad"}))


def test_cache_links_stay_inside_cache_and_cannot_be_parents():
    def archive(target, child=False):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as tar:
            link = tarfile.TarInfo(".rx-oj-deps/link")
            link.type = tarfile.SYMTYPE
            link.linkname = target
            tar.addfile(link)
            if child:
                file = tarfile.TarInfo(".rx-oj-deps/link/child")
                tar.addfile(file, io.BytesIO())
        return stream.getvalue()

    validate_dependency_archive(archive("target"))
    for target in ("../../config.mk", "/etc/passwd"):
        with pytest.raises(DependencyError):
            validate_dependency_archive(archive(target))
    with pytest.raises(DependencyError):
        validate_dependency_archive(archive("target", child=True))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.17.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fd00::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
        "ff02::1",
    ],
)
def test_registry_proxy_rejects_private_dns_answers(address, monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kw: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (address, 443))],
    )
    with pytest.raises(ValueError, match="public"):
        public_addresses("index.crates.io")


def test_registry_proxy_rejects_unlisted_hosts_and_ports_before_dns(monkeypatch):
    resolve = Mock(side_effect=AssertionError("Must not resolve a denied destination"))
    monkeypatch.setattr("sandbox.dependency_proxy.public_addresses", resolve)
    with Server(("127.0.0.1", 0), ["index.crates.io"]) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for request in (
                b"CONNECT localhost:443 HTTP/1.1",
                b"CONNECT index.crates.io:80 HTTP/1.1",
                b"GET http://index.crates.io/ HTTP/1.1",
                b"CONNECT 169.254.169.254:443 HTTP/1.1",
            ):
                with socket.create_connection(server.server_address) as client:
                    client.sendall(request + b"\r\n\r\n")
                    assert b"403" in client.recv(4096)
            resolve.assert_not_called()
        finally:
            server.shutdown()
            thread.join(timeout=2)
