import json
from dataclasses import replace

from fastapi.testclient import TestClient

from rx_oj.api import create_app
from rx_oj.db import Database

OLD_COMMIT = "a" * 40
NEW_COMMIT = "b" * 40
SOURCE_A = "1" * 40
SOURCE_B = "2" * 40


def accepted_run(client, db, name, source_sha):
    response = client.post(
        "/api/submissions",
        json={
            "name": name,
            "language": "python",
            "repository_url": "https://github.com/course/compiler.git",
            "git_ref": "main",
            "suite": "semantic",
        },
    )
    assert response.status_code == 202
    item = response.json()
    claimed = db.claim("worker", 90)
    assert claimed["id"] == item["id"]
    db.revision(item["id"], "worker", source_sha)
    for case_id in json.loads(claimed["case_ids"]):
        db.record(
            item["id"],
            "worker",
            {
                "case_id": case_id,
                "stage": "semantic",
                "verdict": "accepted",
                "duration_ms": 1,
                "cycles": 0,
                "message": "",
                "log": "",
                "runs": [],
            },
        )
    db.finish(item["id"], "worker", "accepted")
    return item["id"]


def test_rejudge_pins_source_and_current_test_commit(settings, accounts, sign_in):
    settings = replace(settings, tests_commit_sha=OLD_COMMIT)
    db = Database(settings.db_path)
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        old = accepted_run(client, db, "First pass", SOURCE_A)
        assert client.get("/api/progress").json()["stages"]["semantic"] == old

    current = replace(settings, tests_commit_sha=NEW_COMMIT)
    with TestClient(create_app(current)) as client:
        sign_in(client)
        assert client.get("/api/progress").json()["stages"]["semantic"] is None
        assert client.get("/api/catalog/summary").json()["commit_sha"] == NEW_COMMIT
        assert client.post(f"/api/admin/submissions/{old}/rejudge").status_code == 403
        sign_in(client, "admin")
        response = client.post(f"/api/admin/submissions/{old}/rejudge")
        assert response.status_code == 202
        item = response.json()
        assert item["rejudge_of"] == old
        assert item["git_ref"] == SOURCE_A
        assert item["tests_commit_sha"] == NEW_COMMIT
        assert item["catalog_version"] == db.get(old)["catalog_version"]
        assert item["owner_id"] == accounts["alice"]
        assert item["status"] == "queued"
        assert client.post(f"/api/admin/submissions/{item['id']}/rejudge").status_code == 409


def test_bulk_rejudge_latest_pass_per_student_is_atomic(settings, accounts, sign_in):
    old_settings = replace(settings, tests_commit_sha=OLD_COMMIT)
    db = Database(settings.db_path)
    with TestClient(create_app(old_settings)) as client:
        sign_in(client)
        earlier = accepted_run(client, db, "Earlier pass", SOURCE_A)
        latest = accepted_run(client, db, "Latest pass", SOURCE_B)
        sign_in(client, "bob")
        bob = accepted_run(client, db, "Bob pass", SOURCE_A)

    current = replace(settings, tests_commit_sha=NEW_COMMIT, max_pending=1)
    with TestClient(create_app(current)) as client:
        sign_in(client, "admin")
        assert client.post("/api/admin/rejudge-latest").status_code == 429
        assert db.health()["queued"] == 0

    current = replace(current, max_pending=10)
    with TestClient(create_app(current)) as client:
        sign_in(client, "admin")
        response = client.post("/api/admin/rejudge-latest")
        assert response.status_code == 202
        queued = response.json()["queued"]
        assert len(queued) == 2
        assert {db.get(item)["rejudge_of"] for item in queued} == {latest, bob}
        assert earlier not in {db.get(item)["rejudge_of"] for item in queued}
        assert client.post("/api/admin/rejudge-latest").json()["queued"] == []
        progress = client.get("/api/admin/progress").json()["items"]
        assert {row["username"] for row in progress} == {"alice", "bob", "admin"}
        assert all(row["stages"]["semantic"] is None for row in progress)
