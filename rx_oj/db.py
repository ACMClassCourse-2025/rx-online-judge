import json
import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

TERMINAL = {
    "accepted",
    "failed",
    "build_error",
    "source_error",
    "system_error",
    "cancelled",
    "time_limit",
    "voided",
}


class QueueFull(ValueError):
    pass


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL,
                    repository_url TEXT NOT NULL DEFAULT '',
                    repository_locked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf_token TEXT NOT NULL, expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, address TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL,
                    stage TEXT NOT NULL, filter TEXT NOT NULL, catalog_version TEXT NOT NULL,
                    case_ids TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                    created_at REAL NOT NULL, started_at REAL, finished_at REAL,
                    worker_id TEXT, lease_until REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
                    passed INTEGER NOT NULL DEFAULT 0, cycles INTEGER NOT NULL DEFAULT 0,
                    build_log TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS submission_queue ON submissions(status, created_at);
                CREATE TABLE IF NOT EXISTS results (
                    submission_id TEXT NOT NULL REFERENCES submissions(id),
                    case_id TEXT NOT NULL, stage TEXT NOT NULL, verdict TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL, cycles INTEGER NOT NULL, message TEXT NOT NULL,
                    log TEXT NOT NULL, runs TEXT NOT NULL,
                    PRIMARY KEY(submission_id, case_id)
                );
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY, heartbeat REAL NOT NULL, images TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS optimization_baselines (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0
                );
                CREATE UNIQUE INDEX IF NOT EXISTS active_optimization_baseline
                    ON optimization_baselines(active) WHERE active=1;
            """)
            # Additive migration preserves histories and results from the shared-token version.
            conn.execute("BEGIN IMMEDIATE")
            user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
            for name, definition in {
                "repository_url": "TEXT NOT NULL DEFAULT ''",
                "repository_locked": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in user_columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(submissions)")}
            for name, definition in {
                "owner_id": "TEXT REFERENCES users(id)",
                "repository_url": "TEXT NOT NULL DEFAULT ''",
                "git_ref": "TEXT NOT NULL DEFAULT 'HEAD'",
                "commit_sha": "TEXT NOT NULL DEFAULT ''",
                "phase": "TEXT NOT NULL DEFAULT 'queued'",
                "current_stage": "TEXT NOT NULL DEFAULT ''",
                "current_case_id": "TEXT NOT NULL DEFAULT ''",
                "voided_at": "REAL",
                "voided_by": "TEXT REFERENCES users(id)",
                "status_before_void": "TEXT",
            }.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE submissions ADD COLUMN {name} {definition}")
            conn.execute("CREATE INDEX IF NOT EXISTS submission_owner ON submissions(owner_id)")

    def create_user(self, username, encoded_password, is_admin=False):
        user_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO users
                (id, username, password_hash, is_admin, active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)""",
                (user_id, username, encoded_password, int(is_admin), time.time()),
            )
        return user_id

    def user_by_name(self, username):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            return dict(row) if row else None

    def reset_password(self, user_id, encoded_password):
        with self.connect() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded_password, user_id))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            conn.execute(
                "DELETE FROM login_attempts WHERE username=(SELECT username FROM users WHERE id=?)",
                (user_id,),
            )

    def set_active(self, user_id, active):
        with self.connect() as conn:
            conn.execute("UPDATE users SET active=? WHERE id=?", (int(active), user_id))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))

    def set_repository(self, user_id, repository_url, locked=True):
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET repository_url=?, repository_locked=? WHERE id=?",
                (repository_url, int(locked), user_id),
            )

    def reserve_login(self, username, address):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM login_attempts WHERE created_at<?", (time.time() - 300,))
            per_user = conn.execute(
                "SELECT count(*) FROM login_attempts WHERE username=?", (username,)
            ).fetchone()[0]
            per_ip = conn.execute(
                "SELECT count(*) FROM login_attempts WHERE address=?", (address,)
            ).fetchone()[0]
            if per_user >= 10 or per_ip >= 50:
                return None
            attempt = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO login_attempts VALUES (?, ?, ?, ?)",
                (attempt, username, address, time.time()),
            )
            return attempt

    def start_session(
        self, token_hash, user_id, csrf_token, seconds, attempt, expected_password_hash
    ):
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
            conn.execute("DELETE FROM login_attempts WHERE id=?", (attempt,))
            inserted = conn.execute(
                """INSERT INTO sessions SELECT ?, id, ?, ? FROM users
                WHERE id=? AND active=1 AND password_hash=?""",
                (token_hash, csrf_token, time.time() + seconds, user_id, expected_password_hash),
            )
            return inserted.rowcount == 1

    def session(self, token_hash):
        with self.connect() as conn:
            row = conn.execute(
                """SELECT users.id, username, is_admin, repository_url, repository_locked,
                csrf_token
                FROM sessions JOIN users ON users.id=sessions.user_id
                WHERE token_hash=? AND expires_at>? AND users.active=1""",
                (token_hash, time.time()),
            ).fetchone()
            return dict(row) if row else None

    def end_session(self, token_hash):
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def enqueue(self, submission, max_pending):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute(
                "SELECT count(*) FROM submissions WHERE status IN ('queued','running')"
            ).fetchone()[0]
            if count >= max_pending:
                raise QueueFull("The judge queue is full; try again after jobs finish")
            conn.execute(
                """INSERT INTO submissions
                (id, name, language, stage, filter, catalog_version, case_ids, created_at, total,
                 owner_id, repository_url, git_ref)
                VALUES (:id, :name, :language, :stage, :filter, :catalog_version,
                        :case_ids, :created_at, :total, :owner_id, :repository_url, :git_ref)""",
                {"owner_id": None, "repository_url": "", "git_ref": "HEAD", **submission},
            )

    def claim(self, worker_id, lease_seconds):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id FROM submissions WHERE status='queued' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """UPDATE submissions SET status='running', phase='fetching', worker_id=?,
                started_at=?, lease_until=? WHERE id=?""",
                (worker_id, time.time(), time.time() + lease_seconds, row["id"]),
            )
            return dict(
                conn.execute("SELECT * FROM submissions WHERE id=?", (row["id"],)).fetchone()
            )

    def heartbeat(self, worker_id, images, lease_seconds):
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO workers VALUES (?, ?, ?)",
                (worker_id, time.time(), json.dumps(images)),
            )
            conn.execute(
                "UPDATE submissions SET lease_until=? WHERE worker_id=? AND status='running'",
                (time.time() + lease_seconds, worker_id),
            )

    def expire(self):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id FROM submissions WHERE status='running' AND lease_until<?",
                (time.time(),),
            ).fetchall()
            conn.execute(
                """UPDATE submissions SET status='system_error', finished_at=?,
                message='Worker heartbeat expired; submit again.'
                WHERE status='running' AND lease_until<?""",
                (time.time(), time.time()),
            )
            conn.execute("DELETE FROM workers WHERE heartbeat<?", (time.time() - 86400,))
            return [row["id"] for row in rows]

    def get(self, submission_id, details=True, owner_id=None):
        with self.connect() as conn:
            # Counters and testcase results must describe the same polling snapshot.
            conn.execute("BEGIN")
            row = conn.execute(
                """SELECT submissions.*, users.username AS owner,
                moderator.username AS voided_by_name
                FROM submissions LEFT JOIN users ON users.id=submissions.owner_id
                LEFT JOIN users moderator ON moderator.id=submissions.voided_by
                WHERE submissions.id=? AND (? IS NULL OR owner_id=?)""",
                (submission_id, owner_id, owner_id),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            case_ids = json.loads(result.pop("case_ids"))
            result["stage_counts"] = dict(
                Counter(case_id.rsplit("@", 1)[1] for case_id in case_ids if "@" in case_id)
            )
            if result["status"] in TERMINAL:
                result.update(phase="done", current_case_id="")
            result.pop("worker_id")
            result.pop("lease_until")
            result["suite"] = result["stage"]
            if details:
                result["results"] = [
                    dict(r)
                    for r in conn.execute(
                        """SELECT case_id, stage, verdict, duration_ms, cycles,
                        runs FROM results WHERE submission_id=? ORDER BY rowid""",
                        (submission_id,),
                    )
                ]
                for case in result["results"]:
                    case["runs"] = json.loads(case["runs"])
            return result

    def result_output(self, submission_id, case_id, owner_id=None):
        with self.connect() as conn:
            row = conn.execute(
                """SELECT results.message, results.log FROM results
                JOIN submissions ON submissions.id=results.submission_id
                WHERE results.submission_id=? AND results.case_id=?
                AND (? IS NULL OR submissions.owner_id=?)""",
                (submission_id, case_id, owner_id, owner_id),
            ).fetchone()
            return dict(row) if row else None

    def listing(self, limit=50, offset=0, owner_id=None, *, q="", status="", suite="", language=""):
        conditions = ["(? IS NULL OR owner_id=?)"]
        params = [owner_id, owner_id]
        if q:
            # Literal substring matching: %, _ and quotes have no special meaning.
            fields = (
                "s.id",
                "s.name",
                "u.username",
                "s.repository_url",
                "s.git_ref",
                "s.commit_sha",
            )
            conditions.append(
                "(" + " OR ".join(f"instr(lower({f}), lower(?))" for f in fields) + ")"
            )
            params.extend([q] * len(fields))
        for column, value in (("status", status), ("stage", suite), ("language", language)):
            if value:
                conditions.append(f"{column}=?")
                params.append(value)
        where = " AND ".join(conditions)
        source = "FROM submissions s LEFT JOIN users u ON u.id=s.owner_id"
        with self.connect() as conn:
            conn.execute("BEGIN")
            rows = conn.execute(
                f"""SELECT s.id, name, language, stage, stage AS suite, filter, status,
                s.created_at, started_at, finished_at, total, completed, passed,
                cycles, message, s.repository_url, s.git_ref, s.commit_sha,
                u.username AS owner,
                cancel_requested, voided_at, status_before_void
                {source} WHERE {where}
                ORDER BY s.created_at DESC, s.id DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute(
                f"SELECT count(*) {source} WHERE {where}",
                params,
            ).fetchone()[0]
        return {"items": [dict(row) for row in rows], "total": total}

    def revision(self, submission_id, worker_id, commit_sha):
        with self.connect() as conn:
            conn.execute(
                """UPDATE submissions SET commit_sha=?
                WHERE id=? AND worker_id=? AND status='running'""",
                (commit_sha, submission_id, worker_id),
            )

    def progress(self, submission_id, worker_id, phase, stage="", case_id=""):
        with self.connect() as conn:
            conn.execute(
                """UPDATE submissions SET phase=?, current_stage=?, current_case_id=?
                WHERE id=? AND worker_id=? AND status='running'""",
                (phase, stage, case_id, submission_id, worker_id),
            )

    def cancelled(self, submission_id, worker_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status, cancel_requested, worker_id FROM submissions WHERE id=?",
                (submission_id,),
            ).fetchone()
            return (
                not row
                or row["status"] != "running"
                or bool(row["cancel_requested"])
                or row["worker_id"] != worker_id
            )

    def cancel(self, submission_id):
        with self.connect() as conn:
            conn.execute(
                """UPDATE submissions SET cancel_requested=1,
                finished_at=CASE WHEN status='queued' THEN ? ELSE finished_at END,
                status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END
                WHERE id=? AND status IN ('queued','running')""",
                (time.time(), submission_id),
            )

    def void(self, submission_id, admin_id):
        with self.connect() as conn:
            # A terminal status stops workers and prevents late results from restoring a score.
            # Keep the original verdict, diagnostics and completion time for inspection.
            conn.execute(
                """UPDATE submissions SET status_before_void=status, status='voided',
                voided_at=?, voided_by=?, finished_at=COALESCE(finished_at, ?),
                cancel_requested=CASE WHEN status IN ('queued','running') THEN 1
                    ELSE cancel_requested END
                WHERE id=? AND status!='voided'""",
                (time.time(), admin_id, time.time(), submission_id),
            )

    def build_log(self, submission_id, worker_id, log):
        with self.connect() as conn:
            conn.execute(
                """UPDATE submissions SET build_log=?
                WHERE id=? AND worker_id=? AND status='running'""",
                (log, submission_id, worker_id),
            )

    def record(self, submission_id, worker_id, result):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, worker_id FROM submissions WHERE id=?", (submission_id,)
            ).fetchone()
            if row["status"] != "running" or row["worker_id"] != worker_id:
                return
            conn.execute(
                """INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    submission_id,
                    result["case_id"],
                    result["stage"],
                    result["verdict"],
                    result["duration_ms"],
                    result["cycles"],
                    result["message"],
                    result["log"],
                    json.dumps(result["runs"]),
                ),
            )
            conn.execute(
                """UPDATE submissions SET completed=completed+1, passed=passed+?,
                cycles=cycles+?, current_case_id='' WHERE id=?""",
                (int(result["verdict"] == "accepted"), result["cycles"], submission_id),
            )

    def finish(self, submission_id, worker_id, status, message=""):
        assert status in TERMINAL
        with self.connect() as conn:
            conn.execute(
                """UPDATE submissions SET status=?, message=?, finished_at=?
                WHERE id=? AND worker_id=? AND status='running'""",
                (status, message, time.time(), submission_id, worker_id),
            )

    def health(self):
        with self.connect() as conn:
            workers = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM workers WHERE heartbeat>?", (time.time() - 40,)
                )
            ]
            for worker in workers:
                worker["images"] = json.loads(worker["images"])
            queued = conn.execute(
                "SELECT count(*) FROM submissions WHERE status='queued'"
            ).fetchone()[0]
        return {
            "status": "ready" if workers else "waiting_for_worker",
            "workers": workers,
            "queued": queued,
        }

    def activate_baseline(self, baseline):
        # Publish a complete baseline in one transaction; readers never see a partial run.
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE optimization_baselines SET active=0 WHERE active=1")
            conn.execute(
                """INSERT INTO optimization_baselines VALUES (?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, active=1""",
                (baseline["id"], json.dumps(baseline, allow_nan=False)),
            )

    def baseline(self):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM optimization_baselines WHERE active=1"
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    def leaderboard_candidates(self, catalog_version):
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT s.id, s.owner_id, u.username, s.name, s.language, s.stage, s.status,
                s.catalog_version, s.total, s.completed, s.passed, s.finished_at,
                r.case_id, r.stage AS case_stage, r.verdict, r.cycles
                FROM submissions s JOIN users u ON u.id=s.owner_id
                JOIN results r ON r.submission_id=s.id
                WHERE u.active=1 AND s.status='accepted' AND s.stage='optimization'
                AND s.catalog_version=? AND s.completed=s.total AND s.passed=s.total
                ORDER BY s.finished_at, s.id, r.rowid""",
                (catalog_version,),
            ).fetchall()
        candidates = {}
        for row in rows:
            item = dict(row)
            result = {
                "case_id": item.pop("case_id"),
                "stage": item.pop("case_stage"),
                "verdict": item.pop("verdict"),
                "cycles": item.pop("cycles"),
            }
            candidates.setdefault(item["id"], {**item, "results": []})["results"].append(result)
        return list(candidates.values())
