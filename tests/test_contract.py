import io
import json
import tarfile
import zipfile

import pytest

from rx_oj.archives import ArchiveError, normalize_upload, pack_files
from rx_oj.catalog import Catalog
from rx_oj.grading import read_cycles, semantic_verdict
from rx_oj.sandbox import ArtifactError


@pytest.mark.parametrize(
    "code,expected,verdict",
    [
        (0, True, "accepted"),
        (1, False, "accepted"),
        (0, False, "wrong_answer"),
        (1, True, "wrong_answer"),
        (2, False, "compile_error"),
        (137, False, "compile_error"),
        (-9, False, "compile_error"),
        (125, False, "compile_error"),
    ],
)
def test_rejection_is_not_a_crash(code, expected, verdict):
    assert semantic_verdict(code, expected)[0] == verdict


def test_cycles_require_one_exact_total():
    assert read_cycles(b"Instructions: 9\nTotal cycles: 321\n") == 321
    for data in [b"Total cycles: -1", b"", b"Total cycles: 1\nTotal cycles: 2\n"]:
        with pytest.raises(ArtifactError):
            read_cycles(data)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "a\\escape"])
def test_path_traversal_rejected(name):
    with pytest.raises(ArchiveError):
        normalize_upload(pack_files({"config.mk": b"", name: b"bad"}), 1000)


def test_archive_types_sizes_and_wrapper():
    data = pack_files({"project/config.mk": b"BUILD = true", "project/main.py": b"pass"})
    normalized = normalize_upload(data, 1000)
    with tarfile.open(fileobj=io.BytesIO(normalized)) as archive:
        assert archive.getnames() == ["config.mk", "main.py"]
    with pytest.raises(ArchiveError):
        normalize_upload(data, 4)
    with pytest.raises(ArchiveError):
        normalize_upload(pack_files({"main.py": b"pass"}), 1000)
    with pytest.raises(ArchiveError):
        normalize_upload(pack_files({"config.mk": b"", "a": b"", "a/b": b""}), 1000)


def test_links_and_zip_duplicates_rejected():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo("config.mk")
        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ArchiveError):
        normalize_upload(buffer.getvalue(), 1000)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("config.mk", "")
        with pytest.warns(UserWarning):
            archive.writestr("config.mk", "oops")
    with pytest.raises(ArchiveError):
        normalize_upload(buffer.getvalue(), 1000)


def test_catalog_cumulative_contract(settings):
    catalog = Catalog(settings.tests_dir)
    assert len(catalog.cases) == 5
    assert len(catalog.select_suite("semantic")) == 2
    assert len(catalog.select_suite("ir")) == 3
    assert len(catalog.select_suite("codegen")) == 4
    assert len(catalog.select_suite("optimization")) == 5
    ir = next(case for case in catalog.cases.values() if case.stage == "ir")
    codegen = next(case for case in catalog.cases.values() if case.stage == "codegen")
    assert ir.source == codegen.source and ir.io == codegen.io
    assert ir.id != codegen.id
    for suite in ("all", "official:smoke", "semantic,codegen"):
        with pytest.raises(ValueError):
            catalog.select_suite(suite)


def test_catalog_rejects_escaping_fixture_and_changes_fingerprint(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (tmp_path / "outside.rx").write_text("fn main() {}")
    manifest = suite / "manifest.json"
    manifest.write_text(
        json.dumps([{"source": "../outside.rx", "stage": "semantic", "compilation_success": True}])
    )
    with pytest.raises(ValueError):
        Catalog(suite)
    manifest.write_text(
        json.dumps([{"source": "inside.rx", "stage": "semantic", "compilation_success": True}])
    )
    (suite / "inside.rx").write_text("fn main() {}")
    before = Catalog(suite).version
    (suite / "inside.rx").write_text("fn main() { println_i32(42); }")
    assert Catalog(suite).version != before
