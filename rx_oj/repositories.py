"""Fetch public Git source in a separate networked container, without executing it."""

import re
import time
from urllib.parse import urlsplit

from .archives import ArchiveError, normalize_upload
from .sandbox import Sandbox


class RepositoryError(ValueError):
    def __init__(self, message, cancelled=False):
        super().__init__(message)
        self.cancelled = cancelled


def validate_repository(url, ref, allowed_hosts):
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in allowed_hosts
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and re.fullmatch(r"/[A-Za-z0-9_.~/-]+", parsed.path)
            and len(parsed.path.strip("/").split("/")) >= 2
            and all(part not in (".", "..") for part in parsed.path.split("/"))
        )
    except ValueError:
        valid = False
    if not valid or any(ord(c) < 33 or ord(c) > 126 for c in url):
        raise RepositoryError(
            "Use a public HTTPS repository URL on an allowed Git host, "
            "without credentials, query parameters, or a custom port"
        )
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,199}", ref)
        or ".." in ref
        or "//" in ref
        or ref.endswith(("/", ".", ".lock"))
    ):
        raise RepositoryError("Use HEAD, a branch, a tag, or a full commit SHA as the Git ref")
    return url, ref


def fetch_repository(client, settings, job, cancelled, deadline):
    url, ref = validate_repository(job["repository_url"], job["git_ref"], settings.git_hosts)
    deadline = min(deadline, time.monotonic() + settings.git_timeout)
    with Sandbox(client, settings, settings.git_image, job["id"], cancelled, network=True) as box:
        prefix = [
            "env",
            "GIT_TERMINAL_PROMPT=0",
            "GIT_CONFIG_NOSYSTEM=1",
            "GIT_CONFIG_GLOBAL=/dev/null",
            "GIT_LFS_SKIP_SMUDGE=1",
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
            "-c",
            "http.followRedirects=false",
            "-c",
            "fetch.fsckObjects=true",
        ]
        if settings.git_proxy:
            prefix.extend(["-c", f"http.proxy={settings.git_proxy}"])

        def run(args, capture=0):
            if cancelled():
                raise RepositoryError("Submission cancelled during Git fetch", cancelled=True)
            result = box.execute(prefix + args, max(0.01, deadline - time.monotonic()), capture)
            if result.limit or result.code:
                raise RepositoryError(
                    "Git fetch failed. Check that the repository and ref are public and valid; "
                    "the repository must fit within the source size and fetch time limits.",
                    cancelled=result.limit == "cancelled",
                )
            return result

        run(["init", "--quiet", "/workspace/repo"])
        run(
            [
                "-C",
                "/workspace/repo",
                "fetch",
                "--quiet",
                "--depth=1",
                "--no-tags",
                "--no-recurse-submodules",
                "--",
                url,
                ref,
            ]
        )
        revision = run(["-C", "/workspace/repo", "rev-parse", "--verify", "FETCH_HEAD^{commit}"])
        sha = revision.log.strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise RepositoryError("Git did not return a valid commit ID")
        archive = run(
            ["-C", "/workspace/repo", "archive", "--format=tar", sha],
            capture=settings.max_source_bytes + 10 * 1024 * 1024,
        ).data
        try:
            source = normalize_upload(archive, settings.max_source_bytes, allow_file_links=True)
        except ArchiveError as exc:
            raise RepositoryError(str(exc)) from exc
        return source, sha
