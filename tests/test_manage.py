import pytest
from fastapi.testclient import TestClient

from rx_oj.api import create_app
from rx_oj.db import Database


def submit(client, **fields):
    response = client.post(
        "/api/submissions",
        json={
            "name": "Loop optimizer",
            "language": "python",
            "repository_url": "https://github.com/course/compiler.git",
            "git_ref": "feature/speed",
            "suite": "semantic",
            **fields,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_management_requires_admin_and_csrf(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/admin/submissions").status_code == 401
        assert client.post("/api/admin/submissions/missing/void").status_code == 401
        sign_in(client)
        job = submit(client)
        path = f"/api/admin/submissions/{job['id']}/void"
        for name in ("alice", "bob"):
            sign_in(client, name)
            assert client.get("/api/admin/submissions").status_code == 403
            assert client.post(path).status_code == 403
        sign_in(client, "admin")
        csrf = client.headers.pop("X-CSRF-Token")
        assert client.post(path).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert client.post("/api/admin/submissions/missing/void").status_code == 404
        assert client.get(f"/api/submissions/{job['id']}").json()["status"] == "queued"
        assert client.post(f"/api/submissions/{job['id']}/cancel").json()["status"] == "cancelled"


def test_management_search_filters_and_pagination(settings, accounts, sign_in):
    db = Database(settings.db_path)
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        first = submit(client, name="Vectorize %_ literal", suite="optimization")
        db.claim("worker", 90)
        db.revision(first["id"], "worker", "abcdef1234567890")
        second = submit(client, name="Loop optimizer")
        sign_in(client, "bob")
        third = submit(client, name="Bob's compiler", language="rust", git_ref="main")
        sign_in(client, "admin")

        def search(**params):
            response = client.get("/api/admin/submissions", params=params)
            assert response.status_code == 200, response.text
            return response.json()

        all_runs = search()
        assert all_runs["total"] == 3
        assert [s["id"] for s in all_runs["items"]] == [third["id"], second["id"], first["id"]]
        page = search(limit=1, offset=1)
        assert page["total"] == 3 and page["items"][0]["id"] == second["id"]
        assert search(offset=3)["items"] == []
        for query, expected in (
            ("  VECTORIZE  ", [first["id"]]),
            ("%_", [first["id"]]),
            ("abcdef123", [first["id"]]),
            ("ALICE", [second["id"], first["id"]]),
            ("feature/speed", [second["id"], first["id"]]),
            ("Bob's", [third["id"]]),
            (third["id"], [third["id"]]),
            ("github.com/course", [third["id"], second["id"], first["id"]]),
            ("' OR 1=1 --", []),
        ):
            data = search(q=query)
            assert data["total"] == len(expected)
            assert [s["id"] for s in data["items"]] == expected
        assert (
            search(q="alice", status="running", suite="optimization", language="python")["items"][
                0
            ]["id"]
            == first["id"]
        )
        assert search(q="alice", language="rust")["total"] == 0
        assert search(suite="semantic", status="queued")["total"] == 2
        for params in ({"status": "invalid"}, {"suite": "all"}, {"q": "x" * 201}, {"offset": -1}):
            assert client.get("/api/admin/submissions", params=params).status_code == 422


@pytest.mark.parametrize("status", ["queued", "running", "accepted", "failed", "cancelled"])
def test_void_preserves_history_and_cannot_be_overwritten(settings, accounts, sign_in, status):
    db = Database(settings.db_path)
    result = {
        "case_id": "first@semantic",
        "stage": "semantic",
        "verdict": "accepted",
        "duration_ms": 1,
        "cycles": 0,
        "message": "",
        "log": "Test diagnostics",
        "runs": [],
    }
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        job = submit(client)
        job_id = job["id"]
        if status != "queued":
            db.claim("worker", 90)
            db.build_log(job_id, "worker", "Build diagnostics")
            db.record(job_id, "worker", result)
            if status != "running":
                db.finish(job_id, "worker", status, "Original message")
        before = db.get(job_id)
        sign_in(client, "admin")
        path = f"/api/admin/submissions/{job_id}/void"
        response = client.post(path)
        assert response.status_code == 200
        voided = response.json()
        assert voided["status"] == "voided" and voided["phase"] == "done"
        assert voided["status_before_void"] == status
        assert voided["voided_by"] == accounts["admin"] and voided["voided_by_name"] == "admin"
        assert voided["voided_at"] > 0 and voided["finished_at"] > 0
        assert voided["optimization_score"] is None
        for field in ("results", "build_log", "completed", "passed", "message"):
            assert voided[field] == before[field]
        if before["finished_at"]:
            assert voided["finished_at"] == before["finished_at"]
        assert (
            client.post(path).json() == voided
        )  # Repeated clicks preserve the first audit record.
        assert db.cancelled(job_id, "worker")
        db.progress(job_id, "worker", "testing", "semantic", "late")
        db.revision(job_id, "worker", "late-commit")
        db.build_log(job_id, "worker", "Late build diagnostics")
        db.record(job_id, "worker", {**result, "case_id": "late@semantic"})
        db.finish(job_id, "worker", "accepted")
        db.cancel(job_id)
        db.expire()
        assert client.get(f"/api/submissions/{job_id}").json() == voided
        assert db.claim("another-worker", 90) is None
        assert db.health()["queued"] == 0
        data = client.get("/api/admin/submissions?status=voided").json()
        assert data["total"] == 1 and data["items"][0]["status_before_void"] == status
        sign_in(client)
        assert client.get(f"/api/submissions/{job_id}").json() == voided
        assert client.get("/api/submissions").json()["items"][0]["status"] == "voided"
        sign_in(client, "bob")
        assert client.get(f"/api/submissions/{job_id}").status_code == 404


def test_existing_database_is_migrated_without_losing_runs(settings, accounts, sign_in):
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        job = submit(client)
    db = Database(settings.db_path)
    with db.connect() as conn:
        for column in ("voided_at", "voided_by", "status_before_void"):
            conn.execute(f"ALTER TABLE submissions DROP COLUMN {column}")
    with TestClient(create_app(settings)) as client:
        sign_in(client, "admin")
        detail = client.get(f"/api/submissions/{job['id']}").json()
        assert detail["status"] == "queued" and detail["voided_at"] is None
        assert detail["results"] == []
        assert client.post(f"/api/admin/submissions/{job['id']}/void").json()["status"] == "voided"
