"""Build official Rust baselines inside the same sandboxes used for submissions."""

import argparse
import hashlib
import json
import re
import time
import uuid
from dataclasses import replace
from pathlib import Path

import docker

from .archives import pack_files
from .catalog import Catalog, load_languages
from .config import ROOT, Settings
from .db import Database
from .grading import Judge
from .sandbox import Sandbox, cleanup_job
from .scoring import OPT_LEVELS, optimization_cases, validate_baseline


def reference_files(reference: Path):
    paths = [reference / "config.mk", reference / "scripts/strip_asm_debug.py"]
    paths += [reference / "crates/rx" / name for name in ("Cargo.toml", "Cargo.lock")]
    paths += sorted((reference / "crates/rx/src").rglob("*.rs"))
    if reference / "crates/rx/src/entry.rs" not in paths:
        raise ValueError("Reference directory must contain the official crates/rx helpers.")
    return {path.relative_to(reference).as_posix(): path.read_bytes() for path in paths}


def variant_source(files, level):
    if level not in OPT_LEVELS:
        raise ValueError("Unsupported Rust optimization level")
    config, count = re.subn(
        r"-C\s+opt-level=[0123sz]\b", f"-C opt-level={level}", files["config.mk"].decode()
    )
    if count != 1:
        raise ValueError("Reference config.mk must contain exactly one -C opt-level setting.")
    config, count = re.subn(
        r"(?m)^BUILD\s*=\s*", f"BUILD = CARGO_PROFILE_RELEASE_OPT_LEVEL={level} ", config
    )
    if count != 1:
        raise ValueError("Reference config.mk must contain a BUILD command.")
    return pack_files({**files, "config.mk": config.encode()})


def choose_baselines(catalog, variants):
    cases = []
    for case_id, case in optimization_cases(catalog).items():
        valid = []
        for level, results in variants.items():
            result = results.get(case_id)
            if not result or result["verdict"] != "accepted":
                continue
            runs = result["runs"]
            if (
                len(runs) != len(case.io)
                or any(
                    r["verdict"] != "accepted" or type(r["cycles"]) is not int or r["cycles"] <= 0
                    for r in runs
                )
                or type(result["cycles"]) is not int
                or result["cycles"] != sum(r["cycles"] for r in runs)
            ):
                continue
            valid.append((result["cycles"], level))
        if not valid:
            raise ValueError(
                f"No correct Rust variant with positive cycles for {case_id}; "
                "baseline was not activated."
            )
        cycles, level = min(valid, key=lambda pair: pair[0])
        cases.append({"case_id": case_id, "cycles": cycles, "best_opt_level": level})
    if not cases:
        raise ValueError("The catalog has no optimization testcases.")
    return cases


def generate_baseline(settings, reference, client, report=print):
    catalog = Catalog(settings.tests_dir)
    files = reference_files(reference.resolve())
    source_digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        source_digest.update(name.encode() + b"\0" + content + b"\0")
    languages = load_languages(settings.languages_file)
    image = client.images.get(languages["rust"]["image"]).id
    runtime_image = client.images.get(settings.runtime_image).id
    settings = replace(settings, runtime_image=runtime_image)
    job_id = "baseline-" + uuid.uuid4().hex
    variants, builds = {}, {}
    try:
        with Sandbox(client, settings, image, job_id) as sandbox:
            execution = sandbox.execute(["rustc", "--version", "--verbose"], 10)
            if execution.code or execution.limit:
                raise ValueError("Could not identify the reference Rust compiler.")
            compiler = execution.log.strip()
        judge = Judge(
            client,
            settings,
            {"id": job_id},
            image,
            lambda: False,
            time.monotonic() + settings.job_timeout,
        )
        for level in OPT_LEVELS:
            report(f"Building Rust reference with opt-level={level}…")
            execution, snapshot = judge.build(variant_source(files, level))
            builds[level] = {"code": execution.code, "limit": execution.limit, "log": execution.log}
            variants[level] = {}
            if execution.code or execution.limit:
                report(f"  Build failed: {execution.limit or execution.code}\n{execution.log}")
                continue
            for case in optimization_cases(catalog).values():
                result = judge.case(case, snapshot)
                variants[level][case.id] = result
                report(f"  {case.id}: {result['verdict']} · {result['cycles']} cycles")
        baseline = {
            "schema_version": 1,
            "catalog_version": catalog.version,
            "created_at": time.time(),
            "compiler": compiler,
            "compiler_image": image,
            "runtime_image": runtime_image,
            "reference_sha256": source_digest.hexdigest(),
            "opt_levels": list(OPT_LEVELS),
            "cases": choose_baselines(catalog, variants),
            "builds": builds,
            "variants": variants,
        }
        # Do not publish results if the fixtures changed while measurements were running.
        validate_baseline(baseline, Catalog(settings.tests_dir))
        baseline["id"] = hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest()
        return baseline
    finally:
        cleanup_job(client, job_id)


def main():
    parser = argparse.ArgumentParser(
        description="Generate and activate an official Rust optimization baseline"
    )
    parser.add_argument("--reference-dir", type=Path, default=ROOT.parent / "rx-compiler")
    parser.add_argument(
        "--output", type=Path, help="Also save all measurements and diagnostics as JSON"
    )
    args = parser.parse_args()
    settings = Settings()
    client = docker.from_env(timeout=30)
    try:
        baseline = generate_baseline(
            settings, args.reference_dir, client, report=lambda line: print(line, flush=True)
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(baseline, indent=2) + "\n")
        Database(settings.db_path).activate_baseline(baseline)
        print(
            f"Activated baseline {baseline['id'][:12]} "
            f"for {len(baseline['cases'])} optimization testcases.",
            flush=True,
        )
    except (ValueError, OSError, docker.errors.DockerException) as exc:
        parser.exit(1, f"Baseline generation failed: {exc}\n")
    finally:
        client.close()


if __name__ == "__main__":
    main()
