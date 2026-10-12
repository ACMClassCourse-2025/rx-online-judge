"""Normalize uploads without ever extracting user paths on the host."""

import io
import posixpath
import stat
import tarfile
import zipfile
from pathlib import PurePosixPath


class ArchiveError(ValueError):
    pass


def pack_files(files: dict[str, bytes], executable: bool = False) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o755 if executable else 0o644
            info.uid = info.gid = 1000
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def normalize_upload(
    data: bytes, max_bytes: int, max_files: int = 10000, allow_file_links: bool = False
) -> bytes:
    files = {}
    links = {}
    total = 0

    def add(name, size, stream, regular=True, directory=False, link=None):
        nonlocal total
        path = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or "\x00" in name
            or path.is_absolute()
            or ".." in path.parts
            or len(name) > 512
        ):
            raise ArchiveError("Archive contains an unsafe path")
        if directory:
            return
        name = path.as_posix()
        if name in files or name in links:
            raise ArchiveError("Archive contains duplicate paths")
        if link is not None and allow_file_links:
            links[path.as_posix()] = link
            return
        if not regular:
            raise ArchiveError("Links, devices, and special files are not allowed")
        name = path.as_posix()
        if name in files or name in links:
            raise ArchiveError("Archive contains duplicate paths")
        total += size
        if total > max_bytes or len(files) >= max_files:
            raise ArchiveError("Expanded archive exceeds the source size or file count limit")
        content = stream.read(min(size + 1, max_bytes + 1))
        if len(content) != size:
            raise ArchiveError("Archive member size is invalid")
        files[name] = content

    try:
        # A tar archive may contain a ZIP file. zipfile.is_zipfile() scans for a
        # central directory anywhere near the end of the input, so checking it
        # first can mistake a Git archive with vendored ZIP data for the ZIP
        # itself. Prefer tar when both format detectors accept the input.
        if tarfile.is_tarfile(io.BytesIO(data)):
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                for index, item in enumerate(archive):
                    if index >= max_files:
                        raise ArchiveError("Too many archive entries")
                    if not item.isfile():
                        add(
                            item.name,
                            0,
                            None,
                            False,
                            item.isdir(),
                            item.linkname if item.issym() else None,
                        )
                        continue
                    with archive.extractfile(item) as stream:
                        add(item.name, item.size, stream)
        elif zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if len(archive.infolist()) > max_files:
                    raise ArchiveError("Too many archive entries")
                for item in archive.infolist():
                    mode = item.external_attr >> 16
                    regular = not stat.S_IFMT(mode) or stat.S_ISREG(mode)
                    with archive.open(item) as stream:
                        add(item.filename, item.file_size, stream, regular, item.is_dir())
        else:
            raise ArchiveError("Upload must be a valid ZIP or tar archive")
    except (tarfile.TarError, zipfile.BadZipFile, OSError, EOFError, RuntimeError) as exc:
        raise ArchiveError("Upload must be a valid ZIP or tar archive") from exc

    def resolve_link(name, visited):
        if name in visited or len(visited) >= 64:
            raise ArchiveError("Repository contains cyclic or excessively nested symbolic links")
        if name in files:
            return files[name]
        target = links.get(name)
        if target is None or target.startswith("/") or "\\" in target or "\x00" in target:
            raise ArchiveError("Repository links must resolve to a file inside the repository")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
        if resolved == ".." or resolved.startswith("../"):
            raise ArchiveError("Repository link escapes the repository")
        return resolve_link(resolved, visited | {name})

    for name in links:
        content = resolve_link(name, set())
        total += len(content)
        if total > max_bytes:
            raise ArchiveError("Expanded repository exceeds the source size limit")
        files[name] = content

    if "config.mk" not in files:
        # Accept GitHub-style archives with one enclosing project directory.
        roots = {PurePosixPath(name).parts[0] for name in files}
        if len(roots) == 1:
            root = next(iter(roots)) + "/"
            files = {name.removeprefix(root): content for name, content in files.items()}
    if "config.mk" not in files:
        raise ArchiveError("Archive must contain config.mk at the project root")
    for name in files:
        if any(parent.as_posix() in files for parent in PurePosixPath(name).parents):
            raise ArchiveError("An archive path is both a file and a directory")
    return pack_files(files, executable=True)
