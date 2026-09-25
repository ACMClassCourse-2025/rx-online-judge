import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from rx_oj.api import create_app
from rx_oj.db import Database
from rx_oj.worker import process


def enqueue(client):
    response = client.post(
        "/api/submissions",
        json={
            "name": "Progress test",
            "language": "python",
            "repository_url": "https://github.com/course/compiler.git",
            "suite": "optimization",
        },
    )
    assert response.status_code == 202
    return response.json()


def accepted(case):
    return {
        "case_id": case.id,
        "stage": case.stage,
        "verdict": "accepted",
        "duration_ms": 10,
        "cycles": 0,
        "message": "",
        "log": "",
        "runs": [],
    }


def test_progress_is_owned_by_active_worker_and_survives_catalog_changes(
    settings, accounts, sign_in
):
    app = create_app(settings)
    with TestClient(app) as client:
        sign_in(client)
        queued = enqueue(client)
        job_id = queued["id"]
        path = f"/api/submissions/{job_id}"
        counts = {"semantic": 2, "ir": 1, "codegen": 1, "optimization": 1}
        assert queued["phase"] == "queued"
        assert queued["stage_counts"] == counts
        db = app.state.db
        job = db.claim("worker", 90)
        assert client.get(path).json()["phase"] == "fetching"
        case = app.state.catalog.cases[json.loads(job["case_ids"])[0]]
        db.progress(job_id, "worker", "testing", case.stage, case.id)
        db.progress(job_id, "other-worker", "building")
        running = client.get(path).json()
        assert running["phase"] == "testing"
        assert running["current_stage"] == case.stage
        assert running["current_case_id"] == case.id
        db.record(job_id, "worker", accepted(case))
        recorded = client.get(path).json()
        assert recorded["completed"] == recorded["passed"] == 1
        assert recorded["current_case_id"] == ""
        assert recorded["results"][0]["case_id"] == case.id
        db.finish(job_id, "worker", "cancelled")
        db.progress(job_id, "worker", "building")
        app.state.catalog.cases.clear()
        done = client.get(path).json()
        assert done["phase"] == "done"
        assert done["current_case_id"] == ""
        assert done["current_stage"] == case.stage
        assert done["stage_counts"] == counts
        # Reopening an existing database keeps the additive migration and old runs intact.
        assert Database(settings.db_path).get(job_id)["stage_counts"] == counts


def test_worker_publishes_fetch_build_and_each_current_test(
    settings, accounts, sign_in, monkeypatch
):
    app = create_app(settings)
    with TestClient(app) as client:
        sign_in(client)
        queued = enqueue(client)
        db = app.state.db
        job = db.claim("worker", 90)
        observed = []

        def observe():
            current = db.get(job["id"])
            observed.append(
                (current["phase"], current["current_stage"], current["current_case_id"])
            )

        def fetch(*_):
            observe()
            return b"source", "a" * 40

        class Judge:
            def __init__(self, *_):
                pass

            def build(self, _):
                observe()
                return SimpleNamespace(log="Build complete", limit=None, code=0), b"snapshot"

            def case(self, case, _):
                observe()
                return accepted(case)

        monkeypatch.setattr("rx_oj.worker.fetch_repository", fetch)
        monkeypatch.setattr("rx_oj.worker.Judge", Judge)
        monkeypatch.setattr("rx_oj.worker.cleanup_job", lambda *_: None)
        docker = Mock()
        docker.images.get.return_value.id = "image-id"
        process(
            db,
            docker,
            settings,
            app.state.catalog,
            app.state.languages,
            job,
            "worker",
            threading.Event(),
        )
        assert observed[:2] == [("fetching", "", ""), ("building", "", "")]
        ids = json.loads(job["case_ids"])
        assert observed[2:] == [
            ("testing", app.state.catalog.cases[case_id].stage, case_id) for case_id in ids
        ]
        finished = client.get(f"/api/submissions/{queued['id']}").json()
        assert finished["status"] == "accepted"
        assert finished["phase"] == "done"
        assert finished["completed"] == finished["total"] == 5
        assert finished["build_log"] == "Build complete"


def test_queued_cancel_and_expired_worker_report_no_active_test(settings, accounts, sign_in):
    app = create_app(settings)
    with TestClient(app) as client:
        sign_in(client)
        queued = enqueue(client)
        cancelled = client.post(f"/api/submissions/{queued['id']}/cancel").json()
        assert cancelled["phase"] == "done" and cancelled["current_case_id"] == ""
        queued = enqueue(client)
        db = app.state.db
        job = db.claim("expired-worker", 90)
        case_id = json.loads(job["case_ids"])[0]
        db.progress(job["id"], "expired-worker", "testing", "semantic", case_id)
        with db.connect() as conn:
            conn.execute("UPDATE submissions SET lease_until=0 WHERE id=?", (job["id"],))
        db.expire()
        db.progress(job["id"], "expired-worker", "testing", "ir", "stale-case")
        result = client.get(f"/api/submissions/{queued['id']}").json()
        assert result["status"] == "system_error"
        assert result["phase"] == "done" and result["current_case_id"] == ""
        assert result["current_stage"] == "semantic"
