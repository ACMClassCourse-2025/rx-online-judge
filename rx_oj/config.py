import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("OJ_DATA_DIR", ROOT / "data")))
    tests_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OJ_TESTS_DIR", ROOT.parent / "rx-compiler/tests"))
    )
    languages_file: Path = field(
        default_factory=lambda: Path(os.getenv("OJ_LANGUAGES_FILE", ROOT / "languages.toml"))
    )
    secure_cookies: bool = field(default_factory=lambda: os.getenv("OJ_SECURE_COOKIES") == "1")
    session_seconds: int = 12 * 60 * 60
    git_image: str = field(default_factory=lambda: os.getenv("OJ_GIT_IMAGE", "rx-oj-git:local"))
    git_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            host.strip().lower()
            for host in os.getenv(
                "OJ_GIT_HOSTS", "github.com,gitlab.com,codeberg.org,gitee.com"
            ).split(",")
            if host.strip()
        )
    )
    git_timeout: float = 120
    runtime_image: str = field(
        default_factory=lambda: os.getenv("OJ_RUNTIME_IMAGE", "rx-oj-reimu:local")
    )
    docker_runtime: str | None = field(
        default_factory=lambda: os.getenv("OJ_DOCKER_RUNTIME") or None
    )
    build_timeout: float = 120
    compile_timeout: float = 30
    run_timeout: float = 10
    job_timeout: float = 3600
    lease_seconds: int = 90
    memory_mb: int = 1024
    runtime_memory_mb: int = 512
    workspace_mb: int = 512
    max_source_bytes: int = 64 * 1024 * 1024
    max_snapshot_bytes: int = 256 * 1024 * 1024
    max_artifact_bytes: int = 8 * 1024 * 1024
    max_output_bytes: int = 1024 * 1024
    max_log_bytes: int = 64 * 1024
    max_pending: int = 100

    @property
    def db_path(self):
        return self.data_dir / "judge.sqlite3"

    @property
    def uploads_dir(self):
        return self.data_dir / "submissions"
