import io
import json
import tarfile
import time

import pytest

from rx_oj.archives import ArchiveError, normalize_upload
from rx_oj.db import Database
from rx_oj.repositories import RepositoryError, validate_repository


@pytest.mark.parametrize(
    "url,ref",
    [
        ("http://github.com/course/compiler.git", "main"),
        ("file:///etc/passwd", "HEAD"),
        ("ssh://git@github.com/course/compiler.git", "main"),
        ("https://token@github.com/course/compiler.git", "main"),
        ("https://github.com/course/compiler.git?token=x", "main"),
        ("https://github.com/course/compiler.git#fragment", "main"),
        ("https://github.com.evil.test/course/compiler.git", "main"),
        ("https://localhost/course/compiler.git", "main"),
        ("https://127.0.0.1/course/compiler.git", "main"),
        ("https://github.com:8080/course/compiler.git", "main"),
        ("https://github.com/course/../compiler.git", "main"),
        ("https://github.com/course/compiler.git", "--upload-pack=bad"),
        ("https://github.com/course/compiler.git", "HEAD:somewhere"),
        ("https://github.com/course/compiler.git", "main\ncommand"),
    ],
)
def test_invalid_repositories_and_refs_rejected(url, ref):
    with pytest.raises(RepositoryError):
        validate_repository(url, ref, ("github.com",))


@pytest.mark.parametrize("ref", ["HEAD", "main", "refs/heads/topic/compiler", "v1.0", "a" * 40])
def test_public_git_refs_accepted(ref):
    url = "https://github.com/course/compiler.git"
    assert validate_repository(url, ref, ("github.com",)) == (url, ref)


def linked_archive(target):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in {"config.mk": b"BUILD = true", "README-EN.md": b"Compiler"}.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        link = tarfile.TarInfo("README.md")
        link.type = tarfile.SYMTYPE
        link.linkname = target
        archive.addfile(link)
    return buffer.getvalue()


def test_repository_file_links_are_materialized_without_host_extraction():
    archive = normalize_upload(linked_archive("README-EN.md"), 1000, allow_file_links=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as result:
        assert result.getmember("README.md").isfile()
        assert result.extractfile("README.md").read() == b"Compiler"
    for target in ("README.md", "../outside", "/etc/passwd", "missing"):
        with pytest.raises(ArchiveError):
            normalize_upload(linked_archive(target), 1000, allow_file_links=True)


def test_legacy_migration_preserves_history_for_admin_only(settings, encoded_password):
    db = Database(settings.db_path)
    db.enqueue(
        {
            "id": "legacy",
            "name": "Old submission",
            "language": "python",
            "stage": "all",
            "filter": "official:one",
            "catalog_version": "old",
            "case_ids": json.dumps([]),
            "created_at": time.time(),
            "total": 1,
        },
        100,
    )
    with db.connect() as conn:
        conn.execute("DROP INDEX submission_owner")
        for column in ("owner_id", "repository_url", "git_ref", "commit_sha"):
            conn.execute(f"ALTER TABLE submissions DROP COLUMN {column}")
    migrated = Database(settings.db_path)
    user_id = migrated.create_user("alice", encoded_password)
    assert migrated.get("legacy")["name"] == "Old submission"
    assert migrated.get("legacy", owner_id=user_id) is None
    assert migrated.listing(owner_id=user_id)["total"] == 0
