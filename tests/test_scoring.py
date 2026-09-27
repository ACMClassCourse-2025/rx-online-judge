import copy
import json
import shutil
import time
import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from rx_oj.api import create_app
from rx_oj.baseline import choose_baselines, variant_source
from rx_oj.catalog import Catalog
from rx_oj.db import Database
from rx_oj.scoring import OPT_LEVELS, baseline_status, score_submission


@pytest.fixture
def scoring_setup(settings, tmp_path):
    tests = tmp_path / "suite"
    shutil.copytree(settings.tests_dir, tests)
    manifest = tests / "official/smoke/manifest.json"
    entries = json.loads(manifest.read_text())
    entries.append({**entries[2], "stage": "optimization"})
    manifest.write_text(json.dumps(entries))
    settings = replace(settings, tests_dir=tests)
    catalog = Catalog(tests)
    cases = [c for c in catalog.cases.values() if c.stage == "optimization"]
    baseline = {
        "id": "baseline-one",
        "catalog_version": catalog.version,
        "created_at": time.time(),
        "compiler": "rustc 1.95.0",
        "opt_levels": list(OPT_LEVELS),
        "cases": [{"case_id": c.id, "cycles": 100, "best_opt_level": "2"} for c in cases],
        "variants": {"private_diagnostic": "operator only"},
    }
    return settings, catalog, baseline


def submission(catalog, cycles=(25, 400)):
    values = iter(cycles)
    return {
        "status": "accepted",
        "stage": "optimization",
        "catalog_version": catalog.version,
        "total": len(catalog.cases),
        "completed": len(catalog.cases),
        "passed": len(catalog.cases),
        "results": [
            {
                "case_id": case.id,
                "stage": case.stage,
                "verdict": "accepted",
                "cycles": next(values) if case.stage == "optimization" else 0,
            }
            for case in catalog.select_suite("optimization")
        ],
    }


def store_submission(db, catalog, owner, cycles, status="accepted", version=None):
    submission_id = uuid.uuid4().hex
    db.enqueue(
        {
            "id": submission_id,
            "name": f"Compiler {submission_id[:6]}",
            "language": "rust",
            "stage": "optimization",
            "filter": "",
            "catalog_version": version or catalog.version,
            "case_ids": json.dumps(list(catalog.cases)),
            "created_at": time.time(),
            "total": len(catalog.cases),
            "owner_id": owner,
            "repository_url": "https://github.com/course/compiler.git",
            "git_ref": "main",
        },
        100,
    )
    db.claim("test-worker", 90)
    for result in submission(catalog, cycles)["results"]:
        db.record(
            submission_id,
            "test-worker",
            {
                **result,
                "duration_ms": 1,
                "message": "",
                "log": "private log",
                "runs": [],
            },
        )
    db.finish(submission_id, "test-worker", status)
    return submission_id


def test_geometric_mean_weights_testcases_equally(scoring_setup):
    _, catalog, baseline = scoring_setup
    score = score_submission(submission(catalog), baseline, catalog)
    # 0.25 and 4.0 produce 1.0; arithmetic mean and ratio of totals would both be 2.125.
    assert score["score"] == pytest.approx(1.0)
    assert [case["ratio"] for case in score["cases"]] == [0.25, 4.0]
    assert score_submission(submission(catalog, (100, 100)), baseline, catalog)["score"] == 1
    assert score_submission(submission(catalog, (1, 10**18)), baseline, catalog)[
        "score"
    ] == pytest.approx(10**7)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("status", "running"),
        ("status", "cancelled"),
        ("stage", "codegen"),
        ("catalog_version", "old"),
        ("total", 1),
        ("completed", 1),
        ("passed", 1),
    ],
)
def test_only_complete_current_optimization_submissions_score(scoring_setup, field, value):
    _, catalog, baseline = scoring_setup
    item = submission(catalog)
    item[field] = value
    assert score_submission(item, baseline, catalog) is None


@pytest.mark.parametrize(
    "invalid", ["missing", "duplicate", "failure", "wrong_stage", "zero", "negative", "float"]
)
def test_partial_and_invalid_results_cannot_earn_a_score(scoring_setup, invalid):
    _, catalog, baseline = scoring_setup
    item = submission(catalog)
    if invalid == "missing":
        item["results"].pop()
    elif invalid == "duplicate":
        item["results"][-1] = item["results"][-2]
    elif invalid == "failure":
        item["results"][0]["verdict"] = "wrong_answer"  # Earlier suites must pass too.
    elif invalid == "wrong_stage":
        item["results"][-1]["stage"] = "semantic"
    else:
        item["results"][-1]["cycles"] = {"zero": 0, "negative": -1, "float": 2.5}[invalid]
    assert score_submission(item, baseline, catalog) is None


def test_missing_stale_incomplete_and_invalid_baselines(scoring_setup):
    _, catalog, baseline = scoring_setup
    assert baseline_status(None, catalog) == "missing"
    for changes in ({"catalog_version": "old"}, {"cases": []}):
        assert baseline_status({**baseline, **changes}, catalog) == "stale"
        assert score_submission(submission(catalog), {**baseline, **changes}, catalog) is None
    for value in (0, -1, float("nan"), True):
        invalid = copy.deepcopy(baseline)
        invalid["cases"][0]["cycles"] = value
        assert baseline_status(invalid, catalog) == "stale"


def test_choose_best_correct_variant_for_each_whole_testcase(scoring_setup):
    _, catalog, _ = scoring_setup
    cases = [c for c in catalog.cases.values() if c.stage == "optimization"]
    variants = {}
    for level, values in (
        ("0", ((10,), (1, 1))),
        ("2", ((50,), (10, 90))),
        ("3", ((40,), (60, 20))),
    ):
        variants[level] = {
            case.id: {
                "verdict": "runtime_error" if level == "0" else "accepted",
                "cycles": sum(cycles),
                "runs": [{"verdict": "accepted", "cycles": c} for c in cycles],
            }
            for case, cycles in zip(cases, values, strict=True)
        }
    result = choose_baselines(catalog, variants)
    # Min of whole testcase sums is 80, not min(10, 60) + min(90, 20) = 30.
    assert [c["cycles"] for c in result] == [40, 80]
    assert [c["best_opt_level"] for c in result] == ["3", "3"]
    variants["3"][cases[1].id]["runs"].pop()
    assert choose_baselines(catalog, variants)[1]["cycles"] == 100
    variants["2"][cases[1].id]["cycles"] = 1  # Incorrect total cannot supply a baseline.
    with pytest.raises(ValueError, match="No correct Rust variant"):
        choose_baselines(catalog, variants)


def test_variants_change_both_runtime_and_testcase_optimization():
    import io
    import tarfile

    files = {
        "config.mk": (
            b"BUILD = cargo build\nIR = rustc -C opt-level=2 input.rs\n"
            b"CODEGEN = rustc -C opt-level=2 input.rs\n"
        )
    }
    for level in OPT_LEVELS:
        with tarfile.open(fileobj=io.BytesIO(variant_source(files, level))) as archive:
            config = archive.extractfile("config.mk").read().decode()
        assert f"CARGO_PROFILE_RELEASE_OPT_LEVEL={level}" in config
        assert f"CODEGEN = rustc -C opt-level={level}" in config
        assert "IR = rustc -C opt-level=2" in config
    assert files["config.mk"].startswith(b"BUILD = cargo build")
    with pytest.raises(ValueError, match="exactly one"):
        variant_source({"config.mk": b"BUILD = cargo build\nCODEGEN = rustc input.rs"}, "2")
    with pytest.raises(ValueError, match="Unsupported"):
        variant_source(files, "untrusted-flag")


def test_accounts_share_scores_but_not_private_submission_details(scoring_setup, accounts, sign_in):
    settings, catalog, baseline = scoring_setup
    db = Database(settings.db_path)
    db.activate_baseline(baseline)
    alice_first = store_submission(db, catalog, accounts["alice"], (25, 100))  # 0.5
    store_submission(db, catalog, accounts["alice"], (400, 400))  # Later but worse.
    bob_best = store_submission(db, catalog, accounts["bob"], (100, 100))
    store_submission(db, catalog, accounts["bob"], (1, 1), status="failed")
    store_submission(db, catalog, accounts["bob"], (1, 1), version="old")
    store_submission(db, catalog, None, (1, 1))  # Legacy ownerless submissions are not accounts.
    with TestClient(create_app(settings)) as api:
        assert api.get("/api/leaderboard").status_code == 401
        sign_in(api, "bob")
        response = api.get("/api/leaderboard")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready" and data["lower_is_better"]
        assert "no-store" in response.headers["cache-control"]
        rows = data["items"]
        assert [(r["username"], r["rank"], r["score"]) for r in rows] == [
            ("alice", 1, 0.5),
            ("bob", 2, 1),
        ]
        assert rows[0]["submission_id"] == alice_first
        assert rows[1]["submission_id"] == bob_best
        assert not rows[0]["can_view_submission"] and not rows[0]["is_you"]
        assert rows[1]["can_view_submission"] and rows[1]["is_you"]
        assert "private log" not in response.text and "operator only" not in response.text
        assert "repository_url" not in response.text and "owner_id" not in response.text
        assert api.get(f"/api/submissions/{alice_first}").status_code == 404
        detail = api.get(f"/api/submissions/{bob_best}").json()
        assert detail["optimization_score"]["score"] == 1
        assert detail["optimization_baseline_status"] == "ready"
        sign_in(api, "admin")
        assert all(r["can_view_submission"] for r in api.get("/api/leaderboard").json()["items"])
        db.set_active(accounts["alice"], False)
        assert [r["username"] for r in api.get("/api/leaderboard").json()["items"]] == ["bob"]
        # Activation immediately rescales existing accepted submissions without a rejudge.
        updated = copy.deepcopy(baseline)
        updated["id"] = "baseline-two"
        for case in updated["cases"]:
            case["cycles"] *= 2
        db.activate_baseline(updated)
        assert api.get("/api/leaderboard").json()["items"][0]["score"] == 0.5
        assert api.get(f"/api/submissions/{bob_best}").json()["optimization_score"]["score"] == 0.5
        with db.connect() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM optimization_baselines WHERE active=1"
                ).fetchone()[0]
                == 1
            )
        updated["catalog_version"] = "old"
        db.activate_baseline(updated)
        data = api.get("/api/leaderboard").json()
        assert data["status"] == "stale" and data["items"] == []
        detail = api.get(f"/api/submissions/{bob_best}").json()
        assert detail["optimization_score"] is None
        assert detail["optimization_baseline_status"] == "stale"


def test_ties_share_rank_and_keep_earliest_best_submission(scoring_setup, accounts, sign_in):
    settings, catalog, baseline = scoring_setup
    db = Database(settings.db_path)
    db.activate_baseline(baseline)
    alice = store_submission(db, catalog, accounts["alice"], (100, 100))
    store_submission(db, catalog, accounts["alice"], (100, 100))
    store_submission(db, catalog, accounts["bob"], (100, 100))
    store_submission(db, catalog, accounts["admin"], (200, 200))
    with TestClient(create_app(settings)) as api:
        sign_in(api)
        rows = api.get("/api/leaderboard").json()["items"]
        assert [r["rank"] for r in rows] == [1, 1, 3]
        assert rows[0]["submission_id"] == alice


def test_missing_baseline_returns_helpful_empty_state(scoring_setup, accounts, sign_in):
    settings, catalog, _ = scoring_setup
    submission_id = store_submission(
        Database(settings.db_path), catalog, accounts["alice"], (100, 100)
    )
    with TestClient(create_app(settings)) as api:
        sign_in(api)
        data = api.get("/api/leaderboard").json()
        assert data["status"] == "missing" and data["items"] == [] and data["baseline"] is None
        detail = api.get(f"/api/submissions/{submission_id}").json()
        assert detail["optimization_score"] is None
        assert detail["optimization_baseline_status"] == "missing"
