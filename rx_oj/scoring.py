"""One baseline-to-submission cycle ratio per testcase; highest geometric means rank first."""

import math

from .catalog import STAGES

OPT_LEVELS = ("0", "1", "2", "3", "s", "z")
FORMULA = "exp(mean(log(baseline_cycles / testcase_cycles)))"


def optimization_cases(catalog):
    return {key: case for key, case in catalog.cases.items() if case.stage == "optimization"}


def validate_baseline(baseline, catalog):
    if baseline.get("catalog_version") != catalog.version:
        raise ValueError("The baseline belongs to a different test catalog. Regenerate it.")
    if baseline.get("tests_commit_sha", "") != catalog.commit_sha:
        raise ValueError("The baseline belongs to a different test commit. Regenerate it.")
    expected = optimization_cases(catalog)
    cases = baseline.get("cases", [])
    if (
        not expected
        or len(cases) != len(expected)
        or {c["case_id"] for c in cases} != expected.keys()
    ):
        raise ValueError("The baseline must cover every optimization testcase exactly once.")
    for case in cases:
        if type(case.get("cycles")) is not int or case["cycles"] <= 0:
            raise ValueError("Every baseline cycle count must be a positive integer.")


def baseline_status(baseline, catalog):
    if baseline is None:
        return "missing"
    try:
        validate_baseline(baseline, catalog)
    except (ValueError, KeyError, TypeError):
        return "stale"
    return "ready"


def score_submission(submission, baseline, catalog):
    if baseline_status(baseline, catalog) != "ready":
        return None
    expected = catalog.cases
    if (
        submission["status"] != "accepted"
        or submission["stage"] != "optimization"
        or submission["catalog_version"] != catalog.version
        or submission.get("tests_commit_sha", "") != catalog.commit_sha
        or submission["total"] != len(expected)
        or submission["completed"] != len(expected)
        or submission["passed"] != len(expected)
    ):
        return None
    results = submission["results"]
    if len(results) != len(expected) or {r["case_id"] for r in results} != expected.keys():
        return None
    if any(
        r["verdict"] != "accepted" or r["stage"] != expected[r["case_id"]].stage for r in results
    ):
        return None
    cycles = {r["case_id"]: r["cycles"] for r in results if r["stage"] == "optimization"}
    if any(type(value) is not int or value <= 0 for value in cycles.values()):
        return None
    scores = [
        {
            "case_id": case["case_id"],
            "cycles": cycles[case["case_id"]],
            "baseline_cycles": case["cycles"],
            "ratio": case["cycles"] / cycles[case["case_id"]],
        }
        for case in baseline["cases"]
    ]
    score = math.exp(math.fsum(math.log(case["ratio"]) for case in scores) / len(scores))
    return {"baseline_id": baseline["id"], "score": score, "cases": scores}


def leaderboard(db, catalog, viewer):
    baseline = db.baseline()
    status = baseline_status(baseline, catalog)
    response = {
        "status": status,
        "formula": FORMULA,
        "lower_is_better": False,
        "baseline": None,
        "items": [],
    }
    if status != "ready":
        return response
    response["baseline"] = {
        key: baseline[key]
        for key in ("id", "created_at", "catalog_version", "compiler", "opt_levels", "cases")
    }
    # Baseline diagnostics stay operator-only, just like other users' build logs.
    response["baseline"]["cases"] = [
        {key: case[key] for key in ("case_id", "cycles", "best_opt_level")}
        for case in baseline["cases"]
    ]
    best = {}
    for submission in db.leaderboard_candidates(catalog.version, catalog.commit_sha):
        score = score_submission(submission, baseline, catalog)
        if score is None:
            continue
        row = {
            "username": submission["username"],
            "submission_id": submission["id"],
            "submission_name": submission["name"],
            "language": submission["language"],
            "finished_at": submission["finished_at"],
            "score": score["score"],
            "cases": score["cases"],
            "is_you": submission["owner_id"] == viewer["id"],
            "can_view_submission": bool(
                viewer["is_admin"] or submission["owner_id"] == viewer["id"]
            ),
        }
        owner = submission["owner_id"]
        if owner not in best or row["score"] > best[owner]["score"]:
            best[owner] = row
    rows = sorted(best.values(), key=lambda r: (-r["score"], r["finished_at"], r["submission_id"]))
    for index, row in enumerate(rows):
        row["rank"] = (
            rows[index - 1]["rank"]
            if index and row["score"] == rows[index - 1]["score"]
            else index + 1
        )
    response["items"] = rows
    return response


def student_progress(db, catalog, owner_id=None):
    users, runs = db.progress_rows(catalog.version, catalog.commit_sha, owner_id)
    counts = {
        stage: sum(case.stage in STAGES[: index + 1] for case in catalog.cases.values())
        for index, stage in enumerate(STAGES)
    }
    progress = {
        user["id"]: {
            "user_id": user["id"],
            "username": user["username"],
            "is_admin": bool(user["is_admin"]),
            "active": bool(user["active"]),
            "stages": {stage: None for stage in STAGES},
            "score": None,
            "score_submission_id": None,
        }
        for user in users
    }
    for run in runs:
        row = progress[run["owner_id"]]
        if (
            run["total"] != counts[run["stage"]]
            or run["completed"] != run["total"]
            or run["passed"] != run["total"]
        ):
            continue
        for stage in STAGES[: STAGES.index(run["stage"]) + 1]:
            if row["stages"][stage] is None:
                row["stages"][stage] = run["id"]
    baseline = db.baseline()
    if baseline_status(baseline, catalog) == "ready":
        for submission in db.leaderboard_candidates(
            catalog.version, catalog.commit_sha, owner_id, active_only=False
        ):
            score = score_submission(submission, baseline, catalog)
            if score is None:
                continue
            row = progress[submission["owner_id"]]
            if row["score"] is None or score["score"] > row["score"]:
                row["score"] = score["score"]
                row["score_submission_id"] = submission["id"]
    return list(progress.values())
