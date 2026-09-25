import argparse
import json
import logging
import signal
import threading
import time
import uuid
from dataclasses import replace

import docker

from .catalog import Catalog, load_languages
from .config import Settings
from .db import Database
from .grading import Judge
from .repositories import RepositoryError, fetch_repository
from .sandbox import ArtifactError, cleanup_job

log = logging.getLogger(__name__)


def process(db, client, settings, catalog, languages, job, worker_id, stopping):
    job_id = job["id"]
    deadline = time.monotonic() + settings.job_timeout
    last_check, was_cancelled = 0.0, False

    def cancelled():
        nonlocal last_check, was_cancelled
        if stopping.is_set():
            return True
        if time.monotonic() - last_check > 0.5:
            was_cancelled = db.cancelled(job_id, worker_id)
            last_check = time.monotonic()
        return was_cancelled

    try:
        if job["catalog_version"] != catalog.version:
            raise ValueError(
                "Test suite changed since submission. Submit again against the new suite."
            )
        image = languages[job["language"]]["image"]
        # Resolve tags once per submission so builds and cases use exactly the same image.
        image = client.images.get(image).id
        runtime_image = client.images.get(settings.runtime_image).id
        ir_image = client.images.get(settings.ir_image).id
        judge = Judge(
            client,
            replace(settings, runtime_image=runtime_image, ir_image=ir_image),
            job,
            image,
            cancelled,
            deadline,
        )
        source, sha = fetch_repository(client, settings, job, cancelled, deadline)
        db.revision(job_id, worker_id, sha)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        (settings.uploads_dir / f"{job_id}.tar").write_bytes(source)
        db.progress(job_id, worker_id, "building")
        execution, snapshot = judge.build(source)
        db.build_log(job_id, worker_id, execution.log)
        if execution.limit or execution.code:
            status = "cancelled" if execution.limit == "cancelled" else "build_error"
            db.finish(
                job_id,
                worker_id,
                status,
                f"Build {execution.limit or ('exited ' + str(execution.code))}.",
            )
            return
        passed = 0
        ids = json.loads(job["case_ids"])
        for case_id in ids:
            if cancelled():
                db.finish(job_id, worker_id, "cancelled", "Submission cancelled or worker stopped.")
                return
            if time.monotonic() >= deadline:
                db.finish(job_id, worker_id, "time_limit", "Total submission time limit exceeded.")
                return
            case = catalog.cases[case_id]
            db.progress(job_id, worker_id, "testing", case.stage, case_id)
            result = judge.case(case, snapshot)
            db.record(job_id, worker_id, result)
            if result["verdict"] == "cancelled":
                db.finish(job_id, worker_id, "cancelled", "Submission cancelled or worker stopped.")
                return
            passed += result["verdict"] == "accepted"
        db.finish(job_id, worker_id, "accepted" if passed == len(ids) else "failed")
    except RepositoryError as exc:
        db.finish(job_id, worker_id, "cancelled" if exc.cancelled else "source_error", str(exc))
    except ArtifactError as exc:
        db.finish(job_id, worker_id, "build_error", str(exc))
    except Exception:
        log.exception("Submission %s failed in the worker", job_id)
        db.finish(
            job_id,
            worker_id,
            "system_error",
            "Judge infrastructure error. Ask the operator to inspect the worker log.",
        )
    finally:
        cleanup_job(client, job_id)


def run_worker(settings, once=False):
    db = Database(settings.db_path)
    catalog = Catalog(settings.tests_dir)
    languages = load_languages(settings.languages_file)
    client = docker.from_env(timeout=30)
    client.ping()
    worker_id = uuid.uuid4().hex
    stopping = threading.Event()
    heartbeat_stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())

    def heartbeat():
        while not heartbeat_stop.is_set():
            try:
                images = {}
                for key, entry in {
                    **languages,
                    "reimu": {"image": settings.runtime_image},
                    "clang": {"image": settings.ir_image},
                    "git": {"image": settings.git_image},
                }.items():
                    try:
                        images[key] = client.images.get(entry["image"]).id
                    except docker.errors.ImageNotFound:
                        images[key] = None
                db.heartbeat(worker_id, images, settings.lease_seconds)
            except Exception:
                log.exception("Worker heartbeat failed")
            heartbeat_stop.wait(10)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    log.info("Worker %s ready; %s testcases", worker_id, len(catalog.cases))
    try:
        while not stopping.is_set():
            for expired_id in db.expire():
                cleanup_job(client, expired_id)
            job = db.claim(worker_id, settings.lease_seconds)
            if job:
                process(db, client, settings, catalog, languages, job, worker_id, stopping)
            if once:
                break
            if not job:
                stopping.wait(1)
    finally:
        heartbeat_stop.set()
        thread.join(timeout=35)
        with db.connect() as conn:
            conn.execute("DELETE FROM workers WHERE id=?", (worker_id,))
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Run the Rx judge Docker worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued submission")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_worker(Settings(), once=args.once)


if __name__ == "__main__":
    main()
