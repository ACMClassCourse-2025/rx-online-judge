import re
import time
from dataclasses import dataclass, field

from .dependencies import dependency_environment
from .ir import clang_command, strip_debug
from .sandbox import ArtifactError, Sandbox


@dataclass(frozen=True)
class BuildArtifacts:
    workspace: bytes
    runtime: bytes
    environment: dict = field(default_factory=dict)


def semantic_verdict(code: int, should_accept: bool):
    expected = 0 if should_accept else 1
    if code == expected:
        return "accepted", ""
    if code in (0, 1):
        return "wrong_answer", f"Compiler exited {code}; expected {expected}."
    return (
        "compile_error",
        f"Compiler exited {code}; expected {expected} (a normal diagnostic exit).",
    )


def read_cycles(data: bytes):
    matches = re.findall(rb"^Total cycles:[ \t]*([0-9]+)[ \t]*\r?$", data, re.MULTILINE)
    if len(matches) != 1 or len(matches[0]) > 18:
        raise ArtifactError("REIMU must produce exactly one valid 'Total cycles: N' line")
    return int(matches[0])


class Judge:
    def __init__(self, client, settings, submission, image, cancelled, deadline):
        self.client, self.settings = client, settings
        self.submission, self.image = submission, image
        self.cancelled, self.deadline = cancelled, deadline

    def sandbox(self, runtime=False, image=None, environment=None):
        return Sandbox(
            self.client,
            self.settings,
            image or (self.settings.runtime_image if runtime else self.image),
            self.submission["id"],
            self.cancelled,
            runtime,
            environment=environment,
        )

    def timeout(self, value):
        return max(0.01, min(value, self.deadline - time.monotonic()))

    def build(self, source, dependencies=None):
        environment = dependency_environment(dependencies.plan.manager) if dependencies else {}
        build_deadline = min(self.deadline, time.monotonic() + self.settings.build_timeout)
        with self.sandbox(environment=environment) as sandbox:
            sandbox.put("/workspace", source)
            log = dependencies.log if dependencies else ""
            if dependencies:
                sandbox.put("/workspace", dependencies.archive)
                install = sandbox.execute(
                    [
                        "python3",
                        "/opt/rx-oj/dependencies.py",
                        "install",
                        dependencies.plan.manager,
                        dependencies.plan.directory,
                    ],
                    max(0.01, build_deadline - time.monotonic()),
                )
                log += install.log
                if install.code or install.limit:
                    install.log = log[-self.settings.max_log_bytes :]
                    return install, None
            sandbox.files("/output", {"runtime.s": b""})
            execution = sandbox.execute(
                ["python3", "/opt/rx-oj/command.py", "build"],
                max(0.01, build_deadline - time.monotonic()),
            )
            execution.log = (log + execution.log)[-self.settings.max_log_bytes :]
            if execution.limit or execution.code:
                return execution, None
            runtime = sandbox.read_file("/output/runtime.s", self.settings.max_artifact_bytes)
            return execution, BuildArtifacts(sandbox.snapshot(), runtime, environment)

    def case(self, case, build):
        start = time.monotonic()
        result = {
            "case_id": case.id,
            "stage": case.stage,
            "verdict": "accepted",
            "duration_ms": 0,
            "cycles": 0,
            "message": "",
            "log": "",
            "runs": [],
        }

        def fail(verdict, message):
            result.update(verdict=verdict, message=message)

        def append_log(text):
            if not text or result["log"].endswith("[Further testcase output truncated.]"):
                return
            available = max(0, self.settings.max_case_log_bytes - len(result["log"]))
            result["log"] += text[:available]
            if len(text) > available:
                result["log"] += "\n[Further testcase output truncated.]"

        try:
            with self.sandbox(environment=build.environment) as sandbox:
                sandbox.put("/workspace", build.workspace)
                sandbox.files("/case", {"input.rx": case.source.read_bytes()})
                stage = "codegen" if case.stage == "optimization" else case.stage
                execution = sandbox.execute(
                    ["python3", "/opt/rx-oj/command.py", stage],
                    self.timeout(self.settings.compile_timeout),
                    log_limit=self.settings.max_case_log_bytes,
                )
                result["log"] = execution.log
                if execution.limit:
                    fail(execution.limit, f"Compiler: {execution.limit.replace('_', ' ')}.")
                elif case.stage == "semantic":
                    verdict, message = semantic_verdict(execution.code, case.success)
                    fail(verdict, message)
                elif execution.code:
                    fail("compile_error", f"Compiler exited {execution.code}.")
                else:
                    artifact = sandbox.read_file(
                        "/output/program.ll" if case.stage == "ir" else "/output/program.s",
                        self.settings.max_artifact_bytes,
                    )
            if case.stage == "ir" and result["verdict"] == "accepted":
                # Only the emitted IR crosses this boundary; repository files and tools do not.
                with self.sandbox(image=self.settings.ir_image) as clang:
                    clang.files("/case", {"program.ll": artifact})
                    execution = clang.execute(
                        clang_command(),
                        self.timeout(self.settings.compile_timeout),
                        log_limit=self.settings.max_case_log_bytes,
                    )
                    append_log("\nClang IR lowering:\n" + execution.log)
                    if execution.limit:
                        fail(execution.limit, f"Clang: {execution.limit.replace('_', ' ')}.")
                    elif execution.code:
                        fail(
                            "compile_error",
                            f"Clang could not compile LLVM IR (exit {execution.code}).",
                        )
                    else:
                        artifact = strip_debug(
                            clang.read_file("/output/program.s", self.settings.max_artifact_bytes)
                        )
            if case.stage != "semantic" and result["verdict"] == "accepted":
                for index, (inp, expected) in enumerate(case.io, 1):
                    if self.cancelled():
                        fail("cancelled", "Submission cancelled.")
                        break
                    with self.sandbox(runtime=True) as runtime:
                        runtime.files(
                            "/case",
                            {
                                "program.s": artifact,
                                "runtime.s": build.runtime,
                                "stdin": inp.read_bytes() if inp else b"",
                            },
                        )
                        execution = runtime.execute(
                            [
                                "reimu",
                                "--memory=256M",
                                "--stack=1M",
                                "-f",
                                "/case/program.s,/case/runtime.s",
                                "-i",
                                "/case/stdin",
                                "-o",
                                "/output/stdout",
                                "-p",
                                "/output/profile",
                            ],
                            self.timeout(self.settings.run_timeout),
                            log_limit=self.settings.max_case_log_bytes,
                        )
                        append_log(execution.log)
                        cycles = 0
                        if execution.limit:
                            fail(execution.limit, f"Execution {index}: {execution.limit}.")
                        elif execution.code:
                            fail(
                                "runtime_error",
                                f"Execution {index}: REIMU exited {execution.code}.",
                            )
                        else:
                            actual = runtime.read_file(
                                "/output/stdout", self.settings.max_output_bytes
                            )
                            if actual != expected.read_bytes():
                                # Keep hidden expected output outside browser and compiler.
                                fail(
                                    "wrong_answer",
                                    f"Execution {index}: stdout differs from expected "
                                    "output (comparison is byte-for-byte).",
                                )
                            elif case.stage == "optimization":
                                cycles = read_cycles(runtime.read_file("/output/profile", 65536))
                        result["runs"].append(
                            {
                                "index": index,
                                "verdict": result["verdict"],
                                "duration_ms": execution.duration_ms,
                                "cycles": cycles,
                            }
                        )
                        result["cycles"] += cycles
                    if result["verdict"] != "accepted":
                        break
        except ArtifactError as exc:
            fail("artifact_error", str(exc))
        if result["verdict"] != "accepted":
            result["cycles"] = 0
        result["duration_ms"] = round((time.monotonic() - start) * 1000)
        return result
