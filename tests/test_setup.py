import socket
import stat
import subprocess

import pytest

from scripts.setup import configure


@pytest.fixture(autouse=True)
def docker_environment(monkeypatch):
    monkeypatch.delenv("OJ_DOCKER_GID", raising=False)
    monkeypatch.delenv("OJ_DOCKER_SOCKET", raising=False)


@pytest.fixture
def docker_socket(tmp_path, monkeypatch):
    path = tmp_path / "docker.sock"
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        monkeypatch.setenv("OJ_DOCKER_SOCKET", str(path))
        yield path


def test_create_configuration_with_socket_group(tmp_path, docker_socket):
    configure(tmp_path, require_docker=True)
    env = tmp_path / ".env"
    content = env.read_text()
    assert f"OJ_DOCKER_GID={docker_socket.stat().st_gid}\n" in content
    assert f"OJ_DOCKER_SOCKET={docker_socket}\n" in content
    assert "RX_TESTS_PATH=./testcases\n" in content
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    configure(tmp_path, require_docker=True)
    assert env.read_text() == content


def test_setup_records_test_repository_commit(tmp_path, docker_socket):
    official = tmp_path / "testcases" / "official"
    official.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(official)], check=True)
    (official / "manifest.json").write_text("[]")
    subprocess.run(["git", "-C", str(official), "add", "manifest.json"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(official),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "commit",
            "-qm",
            "test",
        ],
        check=True,
    )
    sha = subprocess.check_output(["git", "-C", str(official), "rev-parse", "HEAD"], text=True)
    configure(tmp_path, require_docker=True)
    assert f"RX_TESTS_COMMIT={sha.strip()}\n" in (tmp_path / ".env").read_text()


def test_refresh_stale_group_and_preserve_settings(tmp_path, docker_socket, monkeypatch):
    monkeypatch.delenv("OJ_DOCKER_SOCKET")
    env = tmp_path / ".env"
    unchanged = (
        f"# This file was copied from another host.\nOJ_DOCKER_SOCKET='{docker_socket}'\n"
        "OJ_PORT=9000\nOJ_SECURE_COOKIES=1\nOJ_GIT_HOSTS=git.example.org\n"
        "COMPOSE_PROFILES=git-proxy,cloudflare\nOJ_CLOUDFLARE_TUNNEL_TOKEN=test-only-token\n"
        "OJ_FORWARDED_ALLOW_IPS=*\n"
        "RX_TESTS_PATH=/custom/testcases\n"
    )
    env.write_text(unchanged + f"OJ_DOCKER_GID={docker_socket.stat().st_gid + 1}\n")
    configure(tmp_path, require_docker=True)
    assert env.read_text() == unchanged + f"OJ_DOCKER_GID={docker_socket.stat().st_gid}\n"


def test_append_missing_group_and_migrate_legacy_tests(tmp_path, docker_socket):
    env = tmp_path / ".env"
    env.write_text('RX_TESTS_PATH="../rx-compiler/tests" # old default\nOJ_PORT=9000')
    configure(tmp_path, require_docker=True)
    content = env.read_text()
    assert "RX_TESTS_PATH=./testcases\nOJ_PORT=9000\n" in content
    assert f"OJ_DOCKER_GID={docker_socket.stat().st_gid}\n" in content


def test_exported_socket_overrides_saved_path(tmp_path, docker_socket):
    env = tmp_path / ".env"
    env.write_text("OJ_DOCKER_SOCKET=/old/host/docker.sock\nOJ_DOCKER_GID=12345\n")
    configure(tmp_path, require_docker=True)
    assert f"OJ_DOCKER_SOCKET={docker_socket}\n" in env.read_text()
    assert f"OJ_DOCKER_GID={docker_socket.stat().st_gid}\n" in env.read_text()


def test_explicit_group_override_is_preserved(tmp_path, docker_socket, monkeypatch):
    group = str(docker_socket.stat().st_gid + 1)
    monkeypatch.setenv("OJ_DOCKER_GID", group)
    configure(tmp_path, require_docker=True)
    assert f"OJ_DOCKER_GID={group}\n" in (tmp_path / ".env").read_text()


@pytest.mark.parametrize("existing", [False, True])
def test_missing_socket_fails_without_changing_config(tmp_path, monkeypatch, existing):
    monkeypatch.setenv("OJ_DOCKER_SOCKET", str(tmp_path / "absent.sock"))
    env = tmp_path / ".env"
    original = "OJ_DOCKER_GID=12345\nOJ_PORT=9000\n"
    if existing:
        env.write_text(original)
    with pytest.raises(ValueError, match="Cannot access Docker socket"):
        configure(tmp_path, require_docker=True)
    assert env.exists() == existing
    if existing:
        assert env.read_text() == original


def test_init_before_docker_does_not_guess_a_group(tmp_path, monkeypatch):
    path = tmp_path / "docker.sock"
    monkeypatch.setenv("OJ_DOCKER_SOCKET", str(path))
    configure(tmp_path)
    assert "OJ_DOCKER_GID=" not in (tmp_path / ".env").read_text()
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        configure(tmp_path, require_docker=True)
        assert f"OJ_DOCKER_GID={path.stat().st_gid}\n" in (tmp_path / ".env").read_text()


@pytest.mark.parametrize("directory", [False, True])
def test_reject_non_socket_mount(tmp_path, monkeypatch, directory):
    path = tmp_path / "docker.sock"
    if directory:
        path.mkdir()
    else:
        path.touch()
    monkeypatch.setenv("OJ_DOCKER_SOCKET", str(path))
    with pytest.raises(ValueError, match="must point to a Unix socket"):
        configure(tmp_path, require_docker=True)
    assert not (tmp_path / ".env").exists()
