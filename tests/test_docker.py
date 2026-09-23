import os
import threading
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import docker
from rx_oj.api import create_app
from rx_oj.archives import pack_files
from rx_oj.catalog import Catalog, load_languages
from rx_oj.config import ROOT
from rx_oj.db import Database
from rx_oj.grading import Judge
from rx_oj.sandbox import Sandbox
from rx_oj.worker import process

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


@pytest.mark.parametrize("language", ["python", "cpp"])
def test_full_submission_through_api_worker_and_reimu(
    settings, client, language, accounts, sign_in, monkeypatch
):
    try:
        client.images.get(f"rx-oj-{language}:local")
    except docker.errors.ImageNotFound:
        pytest.fail(f"Build the {language} image before running Docker tests")
    source = pack_files(
        {p.name: p.read_bytes() for p in (ROOT / "examples" / language).iterdir() if p.is_file()}
    )
    monkeypatch.setattr("rx_oj.worker.fetch_repository", lambda *_: (source, "a" * 40))
    with TestClient(create_app(settings)) as api:
        sign_in(api)
        response = api.post(
            "/api/submissions",
            json={
                "name": "Smoke",
                "language": language,
                "repository_url": "https://github.com/course/compiler.git",
                "suite": "optimization",
            },
        )
        assert response.status_code == 202, response.text
        db = Database(settings.db_path)
        job = db.claim("integration", 90)
        process(
            db,
            client,
            settings,
            Catalog(settings.tests_dir),
            load_languages(settings.languages_file),
            job,
            "integration",
            threading.Event(),
        )
        result = api.get(f"/api/submissions/{job['id']}").json()
        assert result["status"] == "accepted", result
        assert result["passed"] == 4 and result["cycles"] > 0
        codegen = next(r for r in result["results"] if r["stage"] == "codegen")
        assert len(codegen["runs"]) == 2
        assert not client.containers.list(
            all=True, filters={"label": f"rx-oj.submission={job['id']}"}
        )


def test_hardening_limits_and_exit_status(settings, client):
    settings = replace(settings, max_log_bytes=1024)
    with Sandbox(client, settings, "rx-oj-python:local", "test-hardening") as box:
        result = box.execute(
            [
                "sh",
                "-c",
                "id -u; test ! -e /var/run/docker.sock; test ! -e /tests; test ! -w /etc/passwd",
            ],
            5,
        )
        assert result.code == 0 and result.log.strip() == "1000"
        box.container.reload()
        config = box.container.attrs["HostConfig"]
        assert config["ReadonlyRootfs"] and config["NetworkMode"] == "none"
        assert config["PidsLimit"] == 64 and config["CapDrop"] == ["ALL"]
        box.files("/workspace", {"config.mk": b"SEMANTIC = exit 1\n"})
        assert box.execute(["python3", "/opt/rx-oj/command.py", "semantic"], 5).code == 1
    with Sandbox(client, settings, "rx-oj-python:local", "test-timeout") as box:
        result = box.execute(["sh", "-c", "sleep 100 & wait"], 0.2)
        assert result.limit == "time_limit"
    with Sandbox(client, settings, "rx-oj-python:local", "test-output") as box:
        assert box.execute(["python3", "-c", "print('x'*10000)"], 5).limit == "output_limit"
    with Sandbox(
        client, settings, "rx-oj-python:local", "test-cancel", cancelled=lambda: True
    ) as box:
        assert box.execute(["sleep", "100"], 5).limit == "cancelled"


@pytest.mark.parametrize(
    "command,stage,verdict",
    [
        ("exit 2", "semantic", "compile_error"),
        ("true", "codegen", "artifact_error"),
        ("cp /workspace/wrong.s {output}", "codegen", "wrong_answer"),
        ("cp /workspace/broken.s {output}", "codegen", "runtime_error"),
        ("sleep 100", "semantic", "time_limit"),
    ],
)
def test_failure_verdicts(settings, client, command, stage, verdict):
    settings = replace(settings, compile_timeout=0.25)
    judge = Judge(
        client,
        settings,
        {"id": "test-failures"},
        "rx-oj-python:local",
        lambda: False,
        time.monotonic() + 60,
    )
    config = f"SEMANTIC = {command}\nCODEGEN = {command}\n".encode()
    execution, snapshot = judge.build(
        pack_files(
            {
                "config.mk": config,
                "wrong.s": b".text\n.globl main\nmain:\nli a0, 0\nret\n",
                "broken.s": b"not valid assembly\n",
            }
        )
    )
    assert execution.code == 0
    case = next(c for c in Catalog(settings.tests_dir).cases.values() if c.stage == stage)
    assert judge.case(case, snapshot)["verdict"] == verdict


@pytest.mark.skipif(
    os.getenv("OJ_TEST_GIT_NETWORK") != "1", reason="Public Git network test is opt-in"
)
def test_public_git_reference_end_to_end(settings, client, accounts, sign_in):
    with TestClient(create_app(settings)) as api:
        sign_in(api)
        response = api.post(
            "/api/submissions",
            json={
                "name": "Public reference",
                "language": "rust",
                "suite": "optimization",
                "repository_url": "https://github.com/ACMClassCourse-2025/rx-compiler.git",
                "git_ref": "HEAD",
            },
        )
        assert response.status_code == 202, response.text
        db = Database(settings.db_path)
        job = db.claim("git-integration", 90)
        process(
            db,
            client,
            settings,
            Catalog(settings.tests_dir),
            load_languages(settings.languages_file),
            job,
            "git-integration",
            threading.Event(),
        )
        result = api.get(f"/api/submissions/{job['id']}").json()
        assert result["status"] == "accepted", result
        assert result["passed"] == 4 and len(result["commit_sha"]) == 40
        assert [r["stage"] for r in result["results"]] == [
            "semantic",
            "semantic",
            "codegen",
            "optimization",
        ]
