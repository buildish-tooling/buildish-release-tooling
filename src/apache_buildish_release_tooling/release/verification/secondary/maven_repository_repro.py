# Copyright 2026 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Maven repository reproducibility comparison helpers."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Literal

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RepositoryFile,
)
from apache_buildish_release_tooling.release.contracts import (
    MavenRepositoryPathMode,
    MavenRepositoryPathResultReport,
    MavenRepositoryPathRuleReport,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import emit_info, update_info

_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class _NormalizedZipEntry:
    """One normalized ZIP member used by Maven reproducibility comparison."""

    is_dir: bool
    mode: int | None
    sha512: str | None


def compare_maven_repository_trees(
    *,
    artifact_id: str,
    staged_by_path: dict[str, _RepositoryFile],
    staged_cache: dict[str, bytes],
    rebuilt_repository_path: Path,
    path_rules: tuple[MavenRepositoryPathRuleReport, ...],
    require_signatures: bool,
    progress_reporter: ProgressReporter,
) -> tuple[list[MavenRepositoryPathResultReport], list[str], bool]:
    emit_info(progress_reporter, f"Reusing staged repository snapshot for local comparison: {artifact_id}")
    emit_info(
        progress_reporter,
        f"Checking rebuilt repository output under {rebuilt_repository_path}",
    )
    if require_signatures and not any(relative_path.endswith(".asc") for relative_path in staged_by_path):
        return (
            [],
            [
                f"maven-repository reproducibility policy requires staged detached signatures for {artifact_id}"
            ],
            False,
        )
    return _compare_repository_path_sets(
        staged_by_path=staged_by_path,
        staged_cache=staged_cache,
        rebuilt_repository_path=rebuilt_repository_path,
        path_rules=path_rules,
        progress_reporter=progress_reporter,
    )


def maven_reproducibility_failure_class(
    path_results: list[MavenRepositoryPathResultReport],
) -> str:
    if any(result.detail in {"missing rebuilt path", "unexpected rebuilt path"} for result in path_results):
        return "path-set-mismatch"
    return "path-comparison-failed"


def _path_mode_for_repository_entry(
    relative_path: str,
    path_rules: tuple[MavenRepositoryPathRuleReport, ...],
) -> MavenRepositoryPathMode:
    for rule in path_rules:
        if re.search(rule.pattern, relative_path):
            return rule.mode
    if _is_default_remote_only_repository_entry(relative_path):
        return "remote-only"
    return "exact-bytes"


def _compare_repository_path_sets(
    *,
    staged_by_path: dict[str, _RepositoryFile],
    staged_cache: dict[str, bytes],
    rebuilt_repository_path: Path,
    path_rules: tuple[MavenRepositoryPathRuleReport, ...],
    progress_reporter: ProgressReporter,
) -> tuple[list[MavenRepositoryPathResultReport], list[str], bool]:
    issues: list[str] = []
    path_results: list[MavenRepositoryPathResultReport] = []
    comparable_staged_paths = {
        relative_path
        for relative_path in staged_by_path
        if _path_mode_for_repository_entry(relative_path, path_rules) != "remote-only"
    }
    for relative_path in sorted(staged_by_path):
        mode = _path_mode_for_repository_entry(relative_path, path_rules)
        if mode != "remote-only":
            continue
        path_results.append(
            MavenRepositoryPathResultReport(
                path=relative_path,
                mode=mode,
                verdict="skipped",
                detail="excluded from local comparison by path rule",
            )
        )
    common_paths = sorted(comparable_staged_paths)
    for index, relative_path in enumerate(common_paths, start=1):
        mode = _path_mode_for_repository_entry(relative_path, path_rules)
        rebuilt_repository_file = _rebuilt_repository_file(
            rebuilt_repository_path,
            relative_path=relative_path,
        )
        if rebuilt_repository_file is None:
            issues.append(
                "maven-repository reproducibility is missing one comparable rebuilt path: "
                f"{relative_path}"
            )
            path_results.append(
                MavenRepositoryPathResultReport(
                    path=relative_path,
                    mode=mode,
                    verdict="failed",
                    detail="missing rebuilt path",
                )
            )
            continue
        staged_payload = _cached_staged_repository_bytes(
            staged_by_path[relative_path],
            cache=staged_cache,
        )
        raw_bytes_equal = _cached_payload_matches_local_file(staged_payload, rebuilt_repository_file.local_path)
        normalized_match: bool | None = None
        detail = "raw bytes matched exactly"
        verdict: Literal["verified", "failed", "skipped"] = "verified"
        if not raw_bytes_equal:
            if mode == "exact-bytes":
                detail = "raw bytes differ"
                verdict = "failed"
                issues.append(
                    "maven-repository reproducibility exact-bytes comparison failed: "
                    f"{relative_path}"
                )
            elif mode == "content-only":
                normalized_match, detail = _compare_zip_payloads(
                    staged_payload,
                    rebuilt_repository_file.local_path,
                    compare_permissions=False,
                )
                if not normalized_match:
                    verdict = "failed"
                    issues.append(
                        "maven-repository reproducibility content-only comparison failed: "
                        f"{relative_path}"
                    )
            elif mode == "zip-normalized":
                normalized_match, detail = _compare_zip_payloads(
                    staged_payload,
                    rebuilt_repository_file.local_path,
                    compare_permissions=True,
                )
                if not normalized_match:
                    verdict = "failed"
                    issues.append(
                        "maven-repository reproducibility zip-normalized comparison failed: "
                        f"{relative_path}"
                    )
            else:
                verdict = "failed"
                detail = f"unsupported comparison mode {mode!r}"
                issues.append(
                    "maven-repository reproducibility encountered an unsupported comparison mode: "
                    f"{relative_path} -> {mode}"
                )
        path_results.append(
            MavenRepositoryPathResultReport(
                path=relative_path,
                mode=mode,
                verdict=verdict,
                detail=detail,
                raw_bytes_equal=raw_bytes_equal,
                normalized_match=normalized_match,
                staged_sha512=hashlib.sha512(staged_payload).hexdigest(),
                rebuilt_sha512=_local_file_sha512(rebuilt_repository_file.local_path),
            )
        )
        update_info(
            progress_reporter,
            f"Compared rebuilt repository entries: {index}/{len(common_paths)}",
        )
    return path_results, issues, not issues


def _rebuilt_repository_file(
    rebuilt_repository_path: Path,
    *,
    relative_path: str,
) -> _RepositoryFile | None:
    local_path = rebuilt_repository_path / Path(relative_path)
    if not local_path.is_file():
        return None
    return _RepositoryFile(
        relative_path=relative_path,
        size_bytes=local_path.stat().st_size,
        local_path=local_path,
    )


def _cached_staged_repository_bytes(
    repository_file: _RepositoryFile,
    *,
    cache: dict[str, bytes],
) -> bytes:
    payload = cache.get(repository_file.relative_path)
    if payload is None:
        raise ValueError(
            "staged maven repository snapshot is missing cached bytes for reproducibility comparison: "
            f"{repository_file.relative_path}"
        )
    return payload


def _is_default_remote_only_repository_entry(relative_path: str) -> bool:
    lowered = relative_path.lower()
    return lowered.endswith((".asc", ".sha512", ".sha256", ".sha1", ".md5"))


def _compare_zip_payloads(
    staged_payload: bytes,
    rebuilt_path: Path | None,
    *,
    compare_permissions: bool,
) -> tuple[bool, str]:
    if rebuilt_path is None:
        return False, "rebuilt repository file has no local path"
    try:
        staged_entries = _normalized_zip_entries_from_payload(
            staged_payload,
            compare_permissions=compare_permissions,
        )
        rebuilt_entries = _normalized_zip_entries_from_path(
            rebuilt_path,
            compare_permissions=compare_permissions,
        )
    except ValueError as exc:
        return False, str(exc)
    staged_paths = set(staged_entries)
    rebuilt_paths = set(rebuilt_entries)
    missing_paths = sorted(staged_paths - rebuilt_paths)
    unexpected_paths = sorted(rebuilt_paths - staged_paths)
    if missing_paths or unexpected_paths:
        return (
            False,
            "archive members differ: "
            f"missing={missing_paths} unexpected={unexpected_paths}",
        )
    for relative_path in sorted(staged_paths):
        staged_entry = staged_entries[relative_path]
        rebuilt_entry = rebuilt_entries[relative_path]
        if staged_entry.is_dir != rebuilt_entry.is_dir:
            return False, f"archive member type differs: {relative_path}"
        if compare_permissions and staged_entry.mode != rebuilt_entry.mode:
            return False, f"archive member permissions differ: {relative_path}"
        if staged_entry.sha512 != rebuilt_entry.sha512:
            return False, f"archive member contents differ: {relative_path}"
    if compare_permissions:
        return True, "archives matched after zip-normalized comparison"
    return True, "archives matched after content-only comparison"


def _normalized_zip_entries_from_payload(
    payload: bytes,
    *,
    compare_permissions: bool,
) -> dict[str, _NormalizedZipEntry]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("comparison requires ZIP-like archives") from exc
    with archive:
        return _normalized_zip_entries_from_archive(archive, compare_permissions=compare_permissions)


def _normalized_zip_entries_from_path(
    path: Path,
    *,
    compare_permissions: bool,
) -> dict[str, _NormalizedZipEntry]:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ValueError("comparison requires ZIP-like archives") from exc
    with archive:
        return _normalized_zip_entries_from_archive(archive, compare_permissions=compare_permissions)


def _normalized_zip_entries_from_archive(
    archive: zipfile.ZipFile,
    *,
    compare_permissions: bool,
) -> dict[str, _NormalizedZipEntry]:
    entries: dict[str, _NormalizedZipEntry] = {}
    for info in archive.infolist():
        if info.filename in entries:
            raise ValueError(f"archive member is duplicated: {info.filename}")
        if info.is_dir():
            sha512 = None
        else:
            with archive.open(info) as member_file:
                sha512 = _stream_sha512(member_file)
        entries[info.filename] = _NormalizedZipEntry(
            is_dir=info.is_dir(),
            mode=((info.external_attr >> 16) & 0o777) if compare_permissions else None,
            sha512=sha512,
        )
    return entries


def _cached_payload_matches_local_file(payload: bytes, path: Path | None) -> bool:
    if path is None or len(payload) != path.stat().st_size:
        return False
    offset = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            next_offset = offset + len(chunk)
            if payload[offset:next_offset] != chunk:
                return False
            offset = next_offset
    return offset == len(payload)


def _local_file_sha512(path: Path | None) -> str:
    if path is None:
        raise ValueError("repository file has no local path")
    with path.open("rb") as handle:
        return _stream_sha512(handle)


def _stream_sha512(stream: IO[bytes]) -> str:
    digest = hashlib.sha512()
    while chunk := stream.read(_HASH_CHUNK_BYTES):
        digest.update(chunk)
    return digest.hexdigest()
