from dataclasses import replace
from unittest.mock import Mock

from rx_oj.sandbox import Sandbox


def test_case_log_limit_can_exceed_default_build_log_limit(settings):
    client = Mock()
    client.api.exec_create.return_value = {"Id": "exec"}
    drained = []

    def stream(*_, **__):
        yield b"x" * 80_000, None
        drained.append(True)
        yield b"tail", None

    client.api.exec_start.side_effect = stream
    client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 0}
    box = Sandbox(client, replace(settings, max_log_bytes=64_000), "image", "job")
    box.container = Mock(id="container")

    execution = box.execute(["compiler"], 5, log_limit=settings.max_case_log_bytes)
    assert execution.limit is None
    assert execution.code == 0
    assert len(execution.log) == 80_004
    assert len(drained) == 1

    execution = box.execute(["build"], 5)
    assert execution.limit is None
    assert execution.code == 0
    assert execution.log.startswith("x" * 64_000)
    assert execution.log.endswith("[Output truncated after 64000 bytes.]")
    assert len(drained) == 2

    execution = box.execute(["archive"], 5, capture=1024)
    assert execution.limit == "output_limit"
    assert len(drained) == 2
    box.container.kill.assert_called_once()
