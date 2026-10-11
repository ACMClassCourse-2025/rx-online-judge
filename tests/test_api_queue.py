import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from rx_oj.api import create_app
from rx_oj.db import Database


def submit(client, **data):
    return client.post(
        "/api/submissions",
        json={
            "language": "python",
            "name": "Demo",
            "repository_url": "https://github.com/course/compiler.git",
            "git_ref": "main",
            "suite": "semantic",
            **data,
        },
    )


def test_catalog_summary_is_public_before_and_after_logout(settings, accounts, sign_in):
    expected = {
        "total": 5,
        "stages": {"semantic": 2, "ir": 1, "codegen": 1, "optimization": 1},
    }
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/catalog/summary")
        assert response.status_code == 200
        assert response.json() == expected
        assert "set-cookie" not in response.headers
        for path in ("catalog", "submissions", "leaderboard", "health", "languages", "auth/me"):
            assert client.get(f"/api/{path}").status_code == 401
        sign_in(client)
        catalog = client.get("/api/catalog").json()
        assert {key: catalog[key] for key in expected} == expected
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/catalog/summary").json() == expected
        assert client.get("/api/catalog").status_code == 401


def test_api_submission_validation_and_cancel(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/catalog").status_code == 401
        sign_in(client)
        assert client.get("/api/catalog").json()["total"] == 5
        assert submit(client, language="untrusted/image").status_code == 422
        assert submit(client, filter="official:smoke").status_code == 422
        assert submit(client, stage="semantic").status_code == 422
        assert submit(client, case_ids=["one"]).status_code == 422
        assert submit(client, name="x" * 81).status_code == 422
        response = submit(client, name="  Demo  ")
        assert response.status_code == 202
        job = response.json()
        assert job["name"] == "Demo"
        assert job["total"] == 2 and job["status"] == "queued"
        assert job["owner"] == "alice" and job["git_ref"] == "main"
        assert "case_ids" not in job and "worker_id" not in job
        assert client.post(f"/api/submissions/{job['id']}/cancel").json()["status"] == "cancelled"
        assert client.get("/api/submissions/nope").status_code == 404
        assert client.get("/api/submissions?limit=101").status_code == 422
        assert client.get("/api/submissions").json()["total"] == 1


def test_locked_repository_is_prefilled_and_enforced(settings, accounts, sign_in):
    repository = "https://github.com/course/locked-compiler.git"
    Database(settings.db_path).set_repository(accounts["alice"], repository)
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        user = client.get("/api/auth/me").json()["user"]
        assert user["repository_url"] == repository
        assert user["repository_locked"] is True
        assert submit(client, repository_url=repository).status_code == 202
        response = submit(client, repository_url="https://github.com/course/other.git")
        assert response.status_code == 422
        assert response.json()["detail"] == "Repository URL is locked for this account"

        sign_in(client, "bob")
        user = client.get("/api/auth/me").json()["user"]
        assert user["repository_url"] == "" and user["repository_locked"] is False


@pytest.mark.parametrize("name_fields", [{}, {"name": None}, {"name": ""}, {"name": " \t "}])
def test_submission_without_name_gets_a_persisted_label(settings, accounts, sign_in, name_fields):
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        response = client.post(
            "/api/submissions",
            json={
                "language": "python",
                "repository_url": "https://github.com/course/compiler.git",
                "suite": "semantic",
                **name_fields,
            },
        )
        assert response.status_code == 202
        job = response.json()
        assert job["name"] == f"Run {job['id'][:8]}"
        assert client.get(f"/api/submissions/{job['id']}").json()["name"] == job["name"]
        assert client.get("/api/submissions").json()["items"][0]["name"] == job["name"]


def test_later_suites_always_include_whole_prerequisites(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        expected = {
            "semantic": ["semantic", "semantic"],
            "ir": ["semantic", "semantic", "ir"],
            "codegen": ["semantic", "semantic", "ir", "codegen"],
            "optimization": ["semantic", "semantic", "ir", "codegen", "optimization"],
        }
        for suite, stages in expected.items():
            job = submit(client, suite=suite).json()
            assert job["total"] == len(stages)
            with Database(settings.db_path).connect() as conn:
                raw = conn.execute(
                    "SELECT case_ids FROM submissions WHERE id=?", (job["id"],)
                ).fetchone()
            assert [case.split("@")[1] for case in json.loads(raw[0])] == stages
        assert submit(client, suite="all").status_code == 422
        assert submit(client, suite="official:smoke").status_code == 422


def test_ownership_and_administrator_access(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as client:
        sign_in(client, "alice")
        job = submit(client).json()
        sign_in(client, "bob")
        assert client.get("/api/submissions").json()["total"] == 0
        assert client.get(f"/api/submissions/{job['id']}").status_code == 404
        assert client.post(f"/api/submissions/{job['id']}/cancel").status_code == 404
        sign_in(client, "admin")
        assert client.get("/api/submissions").json()["total"] == 1
        assert client.get(f"/api/submissions/{job['id']}").json()["owner"] == "alice"
        assert client.post(f"/api/submissions/{job['id']}/cancel").status_code == 200


def test_auth_and_queue_limits(settings, accounts, sign_in):
    with TestClient(create_app(replace(settings, max_pending=1))) as client:
        assert client.get("/api/submissions").status_code == 401
        assert submit(client).status_code == 401
        client.headers["Authorization"] = "Bearer old-shared-token"
        assert submit(client).status_code == 401
        sign_in(client)
        assert submit(client).status_code == 202
        assert submit(client).status_code == 429
        assert not list(settings.uploads_dir.glob("*.tar"))  # Fetch happens in the worker.


def test_oversized_body_rejected(settings):
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/auth/login", content=b"x" * 9000).status_code == 413
        assert (
            client.post("/api/auth/login", content=iter([b"x" * 4500, b"y" * 4500])).status_code
            == 413
        )


def test_claim_is_atomic_and_expired_worker_cannot_overwrite(settings):
    db = Database(settings.db_path)
    for i in range(12):
        db.enqueue(
            {
                "id": str(i),
                "name": "test",
                "language": "python",
                "stage": "semantic",
                "filter": "",
                "catalog_version": "abc",
                "case_ids": json.dumps(["one"]),
                "created_at": time.time(),
                "total": 1,
            },
            100,
        )
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = list(pool.map(lambda i: db.claim(str(i), 90), range(12)))
    assert len({job["id"] for job in jobs}) == 12
    assert db.claim("empty", 90) is None
    job = jobs[0]
    with db.connect() as conn:
        conn.execute("UPDATE submissions SET lease_until=0 WHERE id=?", (job["id"],))
    assert db.expire() == [job["id"]]
    db.finish(job["id"], job["worker_id"], "accepted")
    assert db.get(job["id"])["status"] == "system_error"
    assert db.cancelled(job["id"], job["worker_id"])
