import ipaddress
import os
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import docker
from rx_oj.archives import pack_files
from rx_oj.dependencies import (
    dependency_environment,
    dependency_network,
    dependency_plan,
    prepare_dependencies,
)
from rx_oj.grading import Judge
from rx_oj.sandbox import Sandbox, cleanup_job

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(os.getenv("OJ_TEST_DOCKER") != "1", reason="Set OJ_TEST_DOCKER=1"),
]


@pytest.fixture
def client():
    client = docker.from_env(timeout=30)
    client.ping()
    yield client
    client.close()


def test_dependency_network_cannot_bypass_proxy_or_reach_host(settings, client):
    job_id = "test-dependency-isolation"
    try:
        with HTTPServer(("0.0.0.0", 0), BaseHTTPRequestHandler) as host:
            thread = threading.Thread(target=host.serve_forever, daemon=True)
            thread.start()
            try:
                with dependency_network(client, settings, "rx-oj-python:local", job_id) as network:
                    isolated = client.networks.get(network)
                    subnet = ipaddress.ip_network(isolated.attrs["IPAM"]["Config"][0]["Subnet"])
                    private_gateway = str(subnet.network_address + 1)
                    host_gateway = client.networks.get("bridge").attrs["IPAM"]["Config"][0][
                        "Gateway"
                    ]
                    with Sandbox(
                        client,
                        settings,
                        "rx-oj-python:local",
                        job_id,
                        network_name=network,
                        environment=dependency_environment("pip", online=True),
                    ) as box:
                        targets = [
                            (private_gateway, host.server_port),
                            (host_gateway, host.server_port),
                            ("1.1.1.1", 443),
                        ]
                        program = f"""
import socket
for address, port in {targets!r}:
    try:
        s = socket.create_connection((address, port), timeout=0.3)
    except OSError:
        continue
    s.close()
    raise AssertionError('Unrestricted network access: ' + address)
with socket.create_connection(('dependency-proxy', 3128), timeout=5) as s:
    s.sendall(b'CONNECT 169.254.169.254:443 HTTP/1.1\\r\\n\\r\\n')
    assert b'403' in s.recv(4096)
print('isolated')
"""
                        result = box.execute(["python3", "-c", program], 10)
                        assert result.code == 0, result.log
                        assert result.log.strip() == "isolated"
            finally:
                host.shutdown()
                thread.join(timeout=2)
    finally:
        cleanup_job(client, job_id)
    assert not client.networks.list(filters={"label": "rx-oj.submission=" + job_id})


@pytest.mark.skipif(
    os.getenv("OJ_TEST_DEPENDENCY_NETWORK") != "1",
    reason="Public dependency registry test is opt-in",
)
@pytest.mark.parametrize("language", ["python", "node", "rust", "java"])
def test_fetch_then_build_offline_and_reuse_cache(settings, client, language, monkeypatch):
    settings = replace(settings, dependency_timeout=240, build_timeout=120)
    folder = Path(__file__).parent / "fixtures/dependencies" / language
    source = pack_files(
        {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    )
    job = {
        "id": "test-dependency-" + language,
        "owner_id": "alice",
        "repository_url": "https://github.com/alice/compiler",
    }
    image = client.images.get("rx-oj-" + language + ":local").id
    plan = dependency_plan(source, language)
    try:
        first = prepare_dependencies(
            client, settings, job, image, source, plan, lambda: False, time.monotonic() + 300
        )
        assert "downloaded" in first.log
        judge = Judge(client, settings, job, image, lambda: False, time.monotonic() + 180)
        result, build = judge.build(source, first)
        assert result.code == 0 and result.limit is None, result.log
        assert build and "downloaded" in result.log
        with Sandbox(client, settings, image, job["id"], environment=build.environment) as box:
            box.put("/workspace", build.workspace)
            box.container.reload()
            assert box.container.attrs["HostConfig"]["NetworkMode"] == "none"
            if language == "python":
                check = box.execute(["python3", "/opt/rx-oj/command.py", "semantic"], 5)
                assert check.code == 0 and "25.0" in check.log

        def no_network(*_):
            pytest.fail("A dependency cache hit must not start another networked container")

        monkeypatch.setattr("rx_oj.dependencies.dependency_network", no_network)
        repeated = prepare_dependencies(
            client,
            settings,
            {**job, "id": job["id"] + "-again"},
            image,
            source,
            plan,
            lambda: False,
            time.monotonic() + 30,
        )
        assert repeated.archive == first.archive and "cache hit" in repeated.log
    finally:
        cleanup_job(client, job["id"])


def test_dependency_proxy_uses_upstream_without_exposing_it_to_preparation(settings, client):
    requests = []

    class Upstream(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            requests.append(self.path)
            self.send_error(502, "Upstream reached")

        def log_message(self, *_):
            pass

    job_id = "test-dependency-upstream"
    with HTTPServer(("0.0.0.0", 0), Upstream) as upstream:
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        settings = replace(
            settings,
            dependency_hosts=("93.184.216.34",),
            dependency_proxy=f"http://host.docker.internal:{upstream.server_port}",
        )
        try:
            with dependency_network(client, settings, "rx-oj-python:local", job_id) as network:
                with Sandbox(
                    client,
                    settings,
                    "rx-oj-python:local",
                    job_id,
                    network_name=network,
                    environment=dependency_environment("pip", online=True),
                ) as box:
                    result = box.execute(
                        [
                            "python3",
                            "-c",
                            "import socket; "
                            "s=socket.create_connection(('dependency-proxy',3128),timeout=5); "
                            "s.sendall(b'CONNECT 93.184.216.34:443 HTTP/1.1\\r\\n\\r\\n'); "
                            "print(s.recv(4096).decode())",
                        ],
                        10,
                    )
                    assert result.code == 0 and "502" in result.log
                    box.container.reload()
                    assert not box.container.attrs["HostConfig"].get("ExtraHosts")
                    assert all(
                        settings.dependency_proxy not in value
                        for value in box.container.attrs["Config"]["Env"]
                    )
            assert requests == ["93.184.216.34:443"]
        finally:
            upstream.shutdown()
            thread.join(timeout=2)
            cleanup_job(client, job_id)
