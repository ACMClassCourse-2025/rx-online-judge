import hashlib
import json
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STAGES = ("semantic", "ir", "codegen", "optimization")
MANIFEST_STAGES = ("semantic", "codegen", "optimization")


@dataclass(frozen=True)
class Case:
    id: str
    suite: str
    source: Path
    stage: str
    success: bool
    io: tuple[tuple[Path | None, Path], ...]
    description: str


def fixture(root: Path, directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError(f"Invalid fixture path: {name!r}")
    path = (directory / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Fixture is missing or outside test root: {name}")
    return path


class Catalog:
    def __init__(self, root: Path):
        root = root.resolve()
        self.cases: dict[str, Case] = {}
        digest = hashlib.sha256(
            b"rx-oj-catalog-v3:semantic,ir,codegen,optimization:runtime.s:clang22\0"
        )
        allowed = {"source", "stage", "compilation_success", "io", "description", "metadata"}
        for manifest in sorted(root.rglob("manifest.json")):
            entries = json.loads(manifest.read_text())
            if not isinstance(entries, list) or not entries:
                raise ValueError(f"{manifest}: manifest must be a nonempty array")
            digest.update(manifest.relative_to(root).as_posix().encode())
            digest.update(manifest.read_bytes())
            for entry in entries:
                if isinstance(entry, dict) and entry.get("stage") in ("lex", "parse"):
                    continue
                if not isinstance(entry, dict) or entry.keys() - allowed:
                    raise ValueError(f"{manifest}: invalid testcase fields")
                stage = entry.get("stage")
                success = entry.get("compilation_success")
                if stage not in MANIFEST_STAGES or type(success) is not bool:
                    raise ValueError(f"{manifest}: invalid stage or compilation_success")
                if not isinstance(entry.get("description", ""), str):
                    raise ValueError(f"{manifest}: description must be a string")
                if not isinstance(entry.get("metadata", {}), dict):
                    raise ValueError(f"{manifest}: metadata must be an object")
                pairs = entry.get("io", [])
                if not isinstance(pairs, list) or ("io" in entry and not pairs):
                    raise ValueError(f"{manifest}: io must be a nonempty array")
                if stage != "semantic" and (not success or not pairs):
                    raise ValueError(f"{manifest}: runtime cases must succeed and supply io")
                io = []
                for pair in pairs:
                    if not isinstance(pair, dict) or pair.keys() != {"input", "output"}:
                        raise ValueError(f"{manifest}: invalid io pair")
                    inp = (
                        None
                        if pair["input"] is None
                        else fixture(root, manifest.parent, pair["input"])
                    )
                    out = fixture(root, manifest.parent, pair["output"])
                    io.append((inp, out))
                source = fixture(root, manifest.parent, entry.get("source"))
                suite = ":".join(manifest.parent.relative_to(root).parts) or "root"
                case_id = f"{suite}/{entry['source']}@{stage}"
                if case_id in self.cases:
                    raise ValueError(f"Duplicate testcase: {case_id}")
                self.cases[case_id] = Case(
                    case_id, suite, source, stage, success, tuple(io), entry.get("description", "")
                )
                if stage == "codegen":
                    # One manifest supplies identical fixtures for both compiler interfaces.
                    ir_id = f"{suite}/{entry['source']}@ir"
                    self.cases[ir_id] = Case(
                        ir_id, suite, source, "ir", success, tuple(io), entry.get("description", "")
                    )
                paths = [source, *(p for pair in io for p in pair if p is not None)]
                for path in paths:
                    digest.update(path.relative_to(root).as_posix().encode())
                    digest.update(hashlib.sha256(path.read_bytes()).digest())
        if not self.cases:
            raise ValueError(f"No supported testcases found under {root}")
        self.version = digest.hexdigest()

    def select_suite(self, suite: str) -> list[Case]:
        if suite not in STAGES:
            raise ValueError("Choose semantic, ir, codegen, or optimization")
        included = STAGES[: STAGES.index(suite) + 1]
        # Order whole stages explicitly; filesystem ordering is not grading order.
        if any(not any(case.stage == stage for case in self.cases.values()) for stage in included):
            raise ValueError("The selected suite or a prerequisite suite has no testcases")
        return [case for stage in included for case in self.cases.values() if case.stage == stage]

    def public(self):
        return {
            "version": self.version,
            "total": len(self.cases),
            "stages": dict(Counter(c.stage for c in self.cases.values())),
            "suites": [
                {
                    "id": stage,
                    "count": sum(c.stage == stage for c in self.cases.values()),
                    "includes": list(STAGES[: index + 1]),
                    "total": sum(c.stage in STAGES[: index + 1] for c in self.cases.values()),
                }
                for index, stage in enumerate(STAGES)
            ],
        }


def load_languages(path: Path):
    entries = tomllib.loads(path.read_text())["languages"]
    result = {}
    for entry in entries:
        if entry["id"] in result or not all(
            isinstance(entry.get(key), str) and entry[key]
            for key in ("id", "name", "image", "description")
        ):
            raise ValueError("Invalid language allowlist")
        result[entry["id"]] = entry
    if not result:
        raise ValueError("At least one language image is required")
    return result
