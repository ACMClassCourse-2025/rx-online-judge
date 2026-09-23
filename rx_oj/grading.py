import re
import time

from .sandbox import ArtifactError, Sandbox


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

    def sandbox(self, runtime=False):
        return Sandbox(
            self.client,
            self.settings,
            self.settings.runtime_image if runtime else self.image,
            self.submission["id"],
            self.cancelled,
            runtime,
        )

    def timeout(self, value):
        return max(0.01, min(value, self.deadline - time.monotonic()))

    def build(self, source):
        with self.sandbox() as sandbox:
            sandbox.put("/workspace", source)
            execution = sandbox.execute(
                ["python3", "/opt/rx-oj/command.py", "build"],
                self.timeout(self.settings.build_timeout),
            )
            if execution.limit or execution.code:
                return execution, None
            return execution, sandbox.snapshot()

    def case(self, case, snapshot):
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

        try:
            with self.sandbox() as sandbox:
                sandbox.put("/workspace", snapshot)
                sandbox.files("/case", {"input.rx": case.source.read_bytes()})
                stage = "semantic" if case.stage == "semantic" else "codegen"
                execution = sandbox.execute(
                    ["python3", "/opt/rx-oj/command.py", stage],
                    self.timeout(self.settings.compile_timeout),
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
                    assembly = sandbox.read_file(
                        "/output/program.s", self.settings.max_artifact_bytes
                    )
            if case.stage != "semantic" and result["verdict"] == "accepted":
                for index, (inp, expected) in enumerate(case.io, 1):
                    if self.cancelled():
                        fail("cancelled", "Submission cancelled.")
                        break
                    with self.sandbox(runtime=True) as runtime:
                        runtime.files(
                            "/case",
                            {"program.s": assembly, "stdin": inp.read_bytes() if inp else b""},
                        )
                        execution = runtime.execute(
                            [
                                "reimu",
                                "--memory=256M",
                                "--stack=1M",
                                "-f",
                                "/case/program.s",
                                "-i",
                                "/case/stdin",
                                "-o",
                                "/output/stdout",
                                "-p",
                                "/output/profile",
                            ],
                            self.timeout(self.settings.run_timeout),
                        )
                        available = max(0, self.settings.max_log_bytes - len(result["log"]))
                        result["log"] += execution.log[:available]
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
